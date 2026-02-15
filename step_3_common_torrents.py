#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Part 3: intersect codes and download matching torrent files"
    )
    parser.add_argument("--codes-json", default="artifacts/step_2_codes_from_url.json", help="Step 2 JSON path")
    parser.add_argument("--weekly-json", default="artifacts/step_1_entries.json", help="Step 1 JSON path")
    parser.add_argument("--out-dir", default="artifacts", help="Output directory for step 3 JSON and torrents")
    parser.add_argument("--verbose", action="store_true", help="Print per-item details")
    parser.add_argument(
        "--no-download",
        dest="download",
        action="store_false",
        help="Only plan downloads; do not fetch torrent files",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even when torrent already exists")
    parser.set_defaults(download=True)
    return parser.parse_args()


def script_root() -> Path:
    return Path(__file__).resolve().parent


def resolve_input_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute() or path.exists():
        return path

    root_candidate = script_root() / path
    if root_candidate.exists():
        return root_candidate

    return path


def resolve_out_dir(raw_path: str) -> Path:
    out_dir = Path(raw_path).expanduser()
    if out_dir.is_absolute():
        return out_dir

    cwd_candidate = Path.cwd() / out_dir
    if cwd_candidate.exists() or Path.cwd() == script_root():
        return cwd_candidate

    return script_root() / out_dir


def canonicalize_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    explicit = re.search(r"item[\s_-]*(\d+)", value, flags=re.IGNORECASE)
    if explicit:
        return f"ITEM-{explicit.group(1)}"

    groups = re.findall(r"\d+", value)
    if not groups:
        return None

    fallback_digits = max(enumerate(groups), key=lambda item: (len(item[1]), item[0]))[1]
    return f"ITEM-{fallback_digits}"


def extract_link_url_code(link_url: Any) -> str | None:
    if not isinstance(link_url, str):
        return None

    groups = re.findall(r"\d+", link_url)
    if not groups:
        return None

    # Choose the longest numeric token; on ties, use the last one.
    return max(enumerate(groups), key=lambda item: (len(item[1]), item[0]))[1]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def planned_item(code: str, link_url: str, link_code: str, out_dir: Path, repo_root: Path) -> dict[str, str]:
    torrent_file = out_dir / "seed" / f"{code}.torrent"
    try:
        torrent_path_str = torrent_file.relative_to(repo_root).as_posix()
    except ValueError:
        torrent_path_str = torrent_file.as_posix()
    return {
        "code": code,
        "link_url": link_url,
        "link_url_code": link_code,
        "torrent_url": f"https://books.toscrape.com/download/{link_code}.torrent",
        "torrent_path": torrent_path_str,
    }


def resolve_torrent_destination(item: dict[str, str], repo_root: Path) -> Path:
    raw_path = Path(item["torrent_path"])
    if raw_path.is_absolute():
        return raw_path

    # planned_item stores repo-relative torrent_path when possible.
    return repo_root / raw_path


def download_torrent(torrent_url: str, destination: Path) -> None:
    request = Request(torrent_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response, destination.open("wb") as fp:
        shutil.copyfileobj(response, fp)


def run() -> int:
    args = parse_args()
    codes_path = resolve_input_path(args.codes_json)
    weekly_path = resolve_input_path(args.weekly_json)
    out_dir = resolve_out_dir(args.out_dir)

    if not codes_path.exists():
        raise SystemExit(f"codes JSON not found: {codes_path}")
    if not weekly_path.exists():
        raise SystemExit(f"weekly JSON not found: {weekly_path}")

    codes_payload = read_json(codes_path)
    weekly_payload = read_json(weekly_path)

    weekly_entries = weekly_payload.get("top_entries", [])
    weekly_codes: set[str] = set()
    for entry in weekly_entries:
        canonical = canonicalize_code(entry.get("code") if isinstance(entry, dict) else None)
        if canonical:
            weekly_codes.add(canonical)

    file_codes_map: dict[str, dict[str, Any]] = {}
    for record in codes_payload.get("unique_codes", []):
        if not isinstance(record, dict):
            continue
        canonical = canonicalize_code(record.get("code"))
        if canonical:
            file_codes_map[canonical] = record

    common_codes = sorted(weekly_codes.intersection(file_codes_map))

    seed_dir = out_dir / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)

    common_output: list[dict[str, str]] = []
    report_output: list[dict[str, Any]] = []

    skipped_no_link_code = 0
    downloaded_count = 0
    skipped_exists_count = 0
    failed_count = 0

    for code in common_codes:
        record = file_codes_map[code]
        link_url = record.get("link_url")
        link_code = extract_link_url_code(link_url)

        if not isinstance(link_url, str) or not link_code:
            skipped_no_link_code += 1
            report_output.append(
                {
                    "code": code,
                    "link_url": link_url if isinstance(link_url, str) else "",
                    "link_url_code": "",
                    "torrent_url": "",
                    "torrent_path": "",
                    "status": "skipped",
                    "error": "No numeric link_url_code found in link_url",
                }
            )
            if args.verbose:
                print(f"[warn] {code}: no numeric ID found in link_url={link_url!r}")
            continue

        item = planned_item(code, link_url, link_code, out_dir, script_root())
        common_output.append(item)

        destination = resolve_torrent_destination(item, script_root())
        report_row: dict[str, Any] = {**item, "status": "planned", "error": None}

        if not args.download:
            report_output.append(report_row)
            if args.verbose:
                print(f"[plan] {code} -> {item['torrent_url']}")
            continue

        if destination.exists() and not args.force:
            report_row["status"] = "skipped"
            report_row["error"] = "Already exists"
            skipped_exists_count += 1
            report_output.append(report_row)
            if args.verbose:
                print(f"[skip] {code}: exists {destination}")
            continue

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            download_torrent(item["torrent_url"], destination)
            report_row["status"] = "downloaded"
            downloaded_count += 1
            if args.verbose:
                print(f"[ok] {code}: downloaded {destination}")
        except Exception as exc:
            report_row["status"] = "failed"
            report_row["error"] = str(exc)
            failed_count += 1
            if args.verbose:
                print(f"[fail] {code}: {exc}")
        report_output.append(report_row)

    common_path = out_dir / "common_codes.json"
    report_path = out_dir / "download_report.json"
    write_json(common_path, common_output)
    write_json(report_path, report_output)

    print("Summary")
    print(f"- total step1 codes: {len(weekly_codes)}")
    print(f"- total step2 codes: {len(file_codes_map)}")
    print(f"- intersection count: {len(common_codes)}")
    print(f"- skipped (no link_url_code): {skipped_no_link_code}")
    print(f"- downloaded: {downloaded_count}")
    print(f"- skipped (already exists): {skipped_exists_count}")
    print(f"- failed: {failed_count}")
    print(f"- common output: {common_path}")
    print(f"- download report: {report_path}")

    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
