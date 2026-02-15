#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

DEFAULT_URL = "https://adult.contents.fc2.com/ranking/article/weekly"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
ID_PATTERNS = [
    re.compile(r"/article/(\d+)/"),
    re.compile(r"article_search\.php\?id=(\d+)"),
]
GATE_HINTS = (
    "age",
    "verification",
    "adult",
    "confirm",
    "認証",
    "年齢",
    "captcha",
)


@dataclass
class Entry:
    rank: int
    code: str
    title: str
    metric_label: Optional[str]
    metric_value: Optional[str]
    item_id: str
    link: str


class ScrapeError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape FC2 weekly ranking into JSON")
    parser.add_argument("--url", default=DEFAULT_URL, help="Ranking URL")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of entries")
    parser.add_argument("--out", default="out/fc2_weekly_top.json", help="Output JSON path")
    parser.add_argument(
        "--mode",
        choices=("auto", "requests", "playwright"),
        default="auto",
        help="Fetch mode",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in headful mode (needed for manual age verification)",
    )
    parser.add_argument(
        "--profile-dir",
        default=".fc2_profile",
        help="Persistent Playwright profile directory",
    )
    parser.add_argument(
        "--save-debug",
        action="store_true",
        help="Save fetched HTML to debug_requests.html/debug_rendered.html",
    )
    return parser.parse_args()


def is_gate_page(html: str, url: str) -> bool:
    lowered = html.lower()
    if any(hint in lowered for hint in GATE_HINTS):
        return True
    return "verify" in url.lower() or "age" in url.lower()


def extract_id(href: str) -> Optional[str]:
    for pattern in ID_PATTERNS:
        match = pattern.search(href)
        if match:
            return match.group(1)
    return None


def parse_entries(html: str, source_url: str, limit: int) -> list[Entry]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    entries: list[Entry] = []
    seen_ids: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href"))
        item_id = extract_id(href)
        if not item_id or item_id in seen_ids:
            continue

        seen_ids.add(item_id)
        title = " ".join(anchor.stripped_strings).strip()
        if not title:
            title = f"FC2 PPV {item_id}"

        entries.append(
            Entry(
                rank=len(entries) + 1,
                code=f"FC2-PPV-{item_id}",
                title=title,
                metric_label=None,
                metric_value=None,
                item_id=item_id,
                link=urljoin(source_url, href),
            )
        )
        if len(entries) >= limit:
            break

    return entries


def fetch_with_requests(url: str, save_debug: bool) -> tuple[str, bool]:
    import requests

    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    )
    response.raise_for_status()
    html = response.text
    if save_debug:
        Path("debug_requests.html").write_text(html, encoding="utf-8")
    return html, is_gate_page(html, str(response.url))


def fetch_with_playwright(
    url: str,
    profile_dir: str,
    headful: bool,
    save_debug: bool,
) -> tuple[str, bool]:
    from playwright.sync_api import sync_playwright

    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=not headful,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(3_000)
        html = page.content()
        current_url = page.url
        context.close()

    if save_debug:
        Path("debug_rendered.html").write_text(html, encoding="utf-8")
    return html, is_gate_page(html, current_url)


def write_output(source_url: str, entries: list[Entry], warnings: list[str], out_path: Path) -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "source_url": source_url,
        "scraped_at_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
        "window_start_utc": (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
        "window_end_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
        "top_entries": [entry.__dict__ for entry in entries],
        "warnings": warnings,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run() -> int:
    args = parse_args()
    warnings: list[str] = []

    if args.limit <= 0:
        raise ScrapeError("--limit must be greater than 0")

    gated = False
    entries: list[Entry] = []

    if args.mode in ("auto", "requests"):
        html, gated = fetch_with_requests(args.url, args.save_debug)
        entries = parse_entries(html, args.url, args.limit)
        if args.mode == "requests":
            if gated:
                warnings.append("Possible gate detected in requests response.")
            if not entries:
                warnings.append("Parsed 0 entries in requests mode.")

    if args.mode == "playwright" or (args.mode == "auto" and (gated or not entries)):
        if args.mode == "auto":
            reason = "gate detected" if gated else "parsed 0 entries"
            warnings.append(f"Auto mode fallback to Playwright because {reason}.")

        html, gated = fetch_with_playwright(
            args.url,
            profile_dir=args.profile_dir,
            headful=args.headful,
            save_debug=args.save_debug,
        )
        entries = parse_entries(html, args.url, args.limit)

        if gated and not args.headful:
            raise ScrapeError(
                "Page still appears gated in headless Playwright. "
                "Re-run with --headful and complete any verification manually."
            )

    if not entries:
        raise ScrapeError(
            "Parsed 0 entries. Re-run with --save-debug to inspect HTML. "
            "If gating is present, re-run with --headful."
        )

    write_output(args.url, entries, warnings, Path(args.out))
    print(f"Wrote {len(entries)} entries to {args.out}")
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except ImportError as exc:
        raise SystemExit(
            f"Missing dependency: {exc}. Install dependencies via 'python3 run.py'."
        ) from exc
    except Exception as exc:
        try:
            import requests  # type: ignore

            request_error: Any = requests.HTTPError
        except Exception:
            request_error = tuple()

        if request_error and isinstance(exc, request_error):
            raise SystemExit(f"HTTP error while fetching ranking page: {exc}") from exc
        if isinstance(exc, ScrapeError):
            raise SystemExit(str(exc)) from exc
        raise


if __name__ == "__main__":
    main()
