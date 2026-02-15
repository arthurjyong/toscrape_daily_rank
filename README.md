# toscrape_daily_rank

Small Python project with a 3-step demo pipeline:
1. Scrape a ranking/listing page into normalized JSON.
2. Extract normalized identifiers from a user-supplied URL.
3. Intersect both code sets and optionally download matching `.torrent` files.

## Quickstart

Run Step 1 through the bootstrap wrapper:

```bash
python3 run.py --input-url "https://books.toscrape.com/"
```

`run.py` will:
1. Create `.venv/` if missing.
2. Install dependencies from `requirements.txt`.
3. Install Playwright Chromium into `.pw-browsers/`.
4. Run `step_1_rank.py` with any args you pass through.

By default, Step 1 writes JSON to `artifacts/step_1_entries.json`.

## Step 1: scrape ranking/listing entries -> JSON

```bash
python3 step_1_rank.py --input-url "https://books.toscrape.com/"
```

Required input URL flag aliases:
- `--input-url` (canonical)
- `--input_url`
- `--url`

Useful options:
- `--limit` (default: `100`)
- `--out` (default: `artifacts/step_1_entries.json`)
- `--mode auto|requests|playwright` (default: `auto`)
- `--save-debug` (save fetched HTML for troubleshooting)
- `--profile-dir` (default: `.pw_profile`)
- `--headful` (opt in to visible browser)

Playwright behavior:
- Headless is the default (`--headless` is already implied).
- Use `--headful` if you need to complete verification manually.
- Profile data in `.pw_profile/` persists cookies/session data across runs.
- `--save-debug` writes HTML files under a `debug/` folder next to `--out`:
  - `requests.html`
  - `rendered.html`

Examples:

```bash
python3 step_1_rank.py --input-url "https://books.toscrape.com/" --limit 50
python3 step_1_rank.py --input-url "https://books.toscrape.com/" --mode requests --save-debug
python3 step_1_rank.py --input-url "https://books.toscrape.com/" --mode playwright --headful
python3 step_1_rank.py --input-url "https://books.toscrape.com/" --out artifacts/my_entries.json
```

## Step 2: extract identifiers from a URL -> JSON

Step 2 fetches one URL that you provide and extracts identifiers based on a configurable literal prefix before digits.

```bash
python3 step_2_extract_codes.py --input-url "https://books.toscrape.com/"
```

Required input URL flag aliases:
- `--input-url` (canonical)
- `--input_url`
- `--in`
- `--url`

Useful options:
- `--code-prefix` (default: `item`)
- `--mode unique|all` (default: `all`)
- `--include-context` / `--no-include-context` (default: include context)
- `--limit` (default: `1000`, caps unique output)
- `--out` (default: `artifacts/step_2_codes_from_url.json`)

Code normalization:
- Prefix tokens are normalized to uppercase and joined with `-`, then digits are appended.
- Example with `--code-prefix "item"`: `ITEM-12345`
- Example with `--code-prefix "video code"`: `VIDEO-CODE-12345`
- Separators around the prefix and digits can be spaces, `_`, or `-`.

`link_url` behavior:
- If a matched code appears inside an anchor (`<a>...</a>`), the output record includes `link_url` for that match.

Examples:

```bash
python3 step_2_extract_codes.py --input-url "https://books.toscrape.com/" --code-prefix "item"
python3 step_2_extract_codes.py --input-url "https://books.toscrape.com/" --code-prefix "video code" --mode unique --no-include-context
python3 step_2_extract_codes.py --input-url "https://books.toscrape.com/" --mode all --include-context --out artifacts/custom_codes.json
```

## Step 3: intersect codes + download torrents

Step 3 reads Step 1 + Step 2 JSON, intersects normalized codes, derives a numeric ID from each matched `link_url`, builds a demo torrent URL, and downloads `.torrent` files.

```bash
python3 step_3_common_torrents.py
```

Default inputs:
- `--weekly-json artifacts/step_1_entries.json`
- `--codes-json artifacts/step_2_codes_from_url.json`

Default outputs under `artifacts/`:
- `artifacts/common_codes.json`
- `artifacts/download_report.json`
- `artifacts/seed/*.torrent`

Useful options:
- `--out-dir` (default: `artifacts`)
- `--no-download` (plan only, do not fetch files)
- `--force` (re-download even if file exists)
- `--verbose` (print per-item details)

Examples:

```bash
python3 step_3_common_torrents.py --no-download
python3 step_3_common_torrents.py --force --verbose
python3 step_3_common_torrents.py --codes-json artifacts/step_2_codes_from_url.json --weekly-json artifacts/step_1_entries.json --out-dir artifacts
```

## Troubleshooting

- **Parsed 0 entries (Step 1)**
  - Re-run with `--save-debug` and inspect:
    - `artifacts/debug/requests.html`
    - `artifacts/debug/rendered.html`
  - If you changed `--out`, debug files are written to `<dirname(--out)>/debug/`.

- **Verification/gating page detected (Step 1)**
  - Headless is default.
  - Re-run with `--headful`, complete verification manually, then re-run scraping.

## Notes

- This project does not attempt to bypass authentication or verification.
- Output schemas include timestamp metadata for downstream processing.
