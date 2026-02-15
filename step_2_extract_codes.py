#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import requests

CODE_PATTERN = re.compile(r"fc2[\s_-]*ppv[\s_-]*(\d{5,10})", re.IGNORECASE)
HTML_HINT_PATTERN = re.compile(r"<\s*(html|body|div|span|p|a|script|style|noscript)\b", re.IGNORECASE)


class UniqueCode(TypedDict, total=False):
    rank: int
    code: str
    count: int
    context: str


class Occurrence(TypedDict, total=False):
    rank: int
    code: str
    context: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract FC2 PPV codes from a specific URL and output JSON. "
            "Only the URL provided via --in is fetched."
        )
    )
    parser.add_argument("--in", dest="source_url", required=True, help="Specific source URL to fetch")
    parser.add_argument("--out", default="out/fc2_codes_from_file.json", help="Output JSON path")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum unique codes to output")
    parser.add_argument(
        "--include-context",
        action="store_true",
        help="Include a short surrounding text snippet for occurrences",
    )
    parser.add_argument(
        "--mode",
        choices=("unique", "all"),
        default="unique",
        help="unique: first-seen unique codes; all: every occurrence plus summary",
    )
    return parser.parse_args()


def looks_like_html(content: str, content_type: str | None) -> bool:
    if content_type and "html" in content_type.lower():
        return True
    snippet = content[:5000]
    return bool(HTML_HINT_PATTERN.search(snippet))


def extract_visible_text(content: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content, "lxml")
    for tag_name in ("script", "style", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()
    return soup.get_text(" ", strip=True)


def context_snippet(text: str, start: int, end: int, window: int = 40) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right]
    return re.sub(r"\s+", " ", snippet).strip()


def normalize_code(digits: str) -> str:
    return f"FC2-PPV-{digits}"


def fetch_source(url: str) -> tuple[str, str]:
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        raise SystemExit("--in must be an http/https URL")

    response = requests.get(url, timeout=30, headers={"User-Agent": "fc2-weekly-rank-step2/1.0"})
    response.raise_for_status()
    return response.text, response.headers.get("content-type", "")


def run() -> int:
    args = parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit must be greater than 0")

    raw_content, content_type = fetch_source(args.source_url)
    text = extract_visible_text(raw_content) if looks_like_html(raw_content, content_type) else raw_content

    warnings: list[str] = []

    occurrences_raw: list[tuple[str, int, int]] = []
    for match in CODE_PATTERN.finditer(text):
        code = normalize_code(match.group(1))
        occurrences_raw.append((code, match.start(), match.end()))

    counts = Counter(code for code, _, _ in occurrences_raw)

    occurrences: list[Occurrence] = []
    unique_codes: list[UniqueCode] = []

    first_seen: dict[str, int] = {}
    all_unique_seen: set[str] = set()
    for code, start, end in occurrences_raw:
        all_unique_seen.add(code)
        if args.mode == "all":
            row: Occurrence = {"rank": len(occurrences) + 1, "code": code}
            if args.include_context:
                row["context"] = context_snippet(text, start, end)
            occurrences.append(row)

        if code in first_seen:
            continue

        if len(unique_codes) >= args.limit:
            continue

        first_seen[code] = len(unique_codes) + 1
        row_u: UniqueCode = {
            "rank": first_seen[code],
            "code": code,
            "count": counts[code],
        }
        if args.include_context:
            row_u["context"] = context_snippet(text, start, end)
        unique_codes.append(row_u)

    if len(all_unique_seen) > args.limit:
        warnings.append(f"Unique code output truncated to --limit={args.limit}.")

    payload: dict[str, object] = {
        "source_url": args.source_url,
        "scraped_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "limit": args.limit,
        "mode": args.mode,
        "unique_codes": unique_codes,
        "occurrences": occurrences,
        "warnings": warnings,
    }

    if args.mode == "all":
        payload["summary"] = {
            "total_occurrences": len(occurrences_raw),
            "unique_total": len(all_unique_seen),
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Success: wrote {len(unique_codes)} unique codes "
        f"({len(occurrences_raw)} occurrences) from {args.source_url} to {out_path.resolve()}"
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except requests.HTTPError as exc:
        raise SystemExit(f"HTTP error while fetching URL: {exc}") from exc
    except requests.RequestException as exc:
        raise SystemExit(f"Request failed while fetching URL: {exc}") from exc


if __name__ == "__main__":
    main()
