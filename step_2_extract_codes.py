#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from urllib.parse import urljoin

import requests

HTML_HINT_PATTERN = re.compile(r"<\s*(html|body|div|span|p|a|script|style|noscript)\b", re.IGNORECASE)


class UniqueCode(TypedDict, total=False):
    rank: int
    code: str
    count: int
    context: str
    link_url: str


class Occurrence(TypedDict, total=False):
    rank: int
    code: str
    context: str
    link_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract item identifiers from a specific URL and output JSON. "
            "Only the URL provided via input URL flags is fetched."
        )
    )
    parser.add_argument(
        "--input-url",
        "--input_url",
        "--in",
        "--url",
        dest="input_url",
        required=True,
        help="Specific source URL to fetch",
    )
    parser.add_argument("--out", default="artifacts/step_2_codes_from_url.json", help="Output JSON path")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum unique identifiers to output")
    parser.add_argument(
        "--code-prefix",
        type=str,
        default="item",
        help=(
            "Literal text immediately preceding the digits; may contain spaces; "
            "case-insensitive; separators may be space/_/-."
        ),
    )
    parser.add_argument(
        "--include-context",
        dest="include_context",
        action="store_true",
        help="Include a short surrounding text snippet for occurrences",
    )
    parser.add_argument(
        "--no-include-context",
        dest="include_context",
        action="store_false",
        help="Do not include context snippets",
    )
    parser.set_defaults(include_context=True)
    parser.add_argument(
        "--mode",
        choices=("unique", "all"),
        default="all",
        help="unique: first-seen unique identifiers; all: every occurrence plus summary",
    )
    return parser.parse_args()


def looks_like_html(content: str, content_type: str | None) -> bool:
    if content_type and "html" in content_type.lower():
        return True
    snippet = content[:5000]
    return bool(HTML_HINT_PATTERN.search(snippet))


def extract_visible_text_and_links(content: str, base_url: str) -> tuple[str, list[tuple[int, int, str]]]:
    from bs4 import BeautifulSoup
    from bs4 import Tag

    soup = BeautifulSoup(content, "lxml")
    for tag_name in ("script", "style", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    pieces: list[str] = []
    links: list[tuple[int, int, str]] = []
    cursor = 0

    for node in soup.find_all(string=True):
        text = str(node)
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            continue

        if pieces:
            pieces.append(" ")
            cursor += 1

        start = cursor
        pieces.append(normalized)
        cursor += len(normalized)
        end = cursor

        anchor = node.find_parent("a")
        if isinstance(anchor, Tag):
            href = anchor.get("href")
            if href:
                links.append((start, end, urljoin(base_url, href)))

    return "".join(pieces), links


def context_snippet(text: str, start: int, end: int, window: int = 40) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right]
    return re.sub(r"\s+", " ", snippet).strip()


def normalize_code(digits: str, prefix: str) -> str:
    tokens = prefix.strip().split()
    canon = "-".join(t.upper() for t in tokens)
    return f"{canon}-{digits}"


def build_code_pattern(prefix: str) -> re.Pattern:
    """
    Build a safe regex that matches:
      <prefix tokens separated by [\s_-]*> then [\s_-]* then (\d{5,10})
    Prefix is treated as literal text tokens (escaped), not raw regex.
    """
    if not prefix.strip():
        raise SystemExit("--code-prefix must be non-empty")

    tokens = prefix.strip().split()
    joined = r"[\s_-]*".join(re.escape(t) for t in tokens)
    return re.compile(rf"{joined}[\s_-]*(\d{{5,10}})", re.IGNORECASE)


def fetch_source(url: str) -> tuple[str, str]:
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        raise SystemExit("Input URL must be an http/https URL")

    response = requests.get(url, timeout=30, headers={"User-Agent": "toscrape-step2/1.0"})
    response.raise_for_status()
    return response.text, response.headers.get("content-type", "")


def run() -> int:
    args = parse_args()
    code_pattern = build_code_pattern(args.code_prefix)

    if args.limit <= 0:
        raise SystemExit("--limit must be greater than 0")

    raw_content, content_type = fetch_source(args.input_url)
    if looks_like_html(raw_content, content_type):
        text, link_spans = extract_visible_text_and_links(raw_content, args.input_url)
    else:
        text, link_spans = raw_content, []

    warnings: list[str] = []

    occurrences_raw: list[tuple[str, int, int, str | None]] = []
    for match in code_pattern.finditer(text):
        code = normalize_code(match.group(1), args.code_prefix)
        link_url = next(
            (href for start, end, href in link_spans if start <= match.start() and match.end() <= end),
            None,
        )
        occurrences_raw.append((code, match.start(), match.end(), link_url))

    counts = Counter(code for code, _, _, _ in occurrences_raw)

    occurrences: list[Occurrence] = []
    unique_codes: list[UniqueCode] = []

    first_seen: dict[str, int] = {}
    all_unique_seen: set[str] = set()
    for code, start, end, link_url in occurrences_raw:
        all_unique_seen.add(code)
        if args.mode == "all":
            row: Occurrence = {"rank": len(occurrences) + 1, "code": code}
            if args.include_context:
                row["context"] = context_snippet(text, start, end)
            if link_url:
                row["link_url"] = link_url
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
        if link_url:
            row_u["link_url"] = link_url
        unique_codes.append(row_u)

    if len(all_unique_seen) > args.limit:
        warnings.append(f"Unique identifier output truncated to --limit={args.limit}.")

    payload: dict[str, object] = {
        "source_url": args.input_url,
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
        f"Success: wrote {len(unique_codes)} unique identifiers "
        f"({len(occurrences_raw)} occurrences) from {args.input_url} to {out_path.resolve()} "
        f"(prefix={args.code_prefix!r})"
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
