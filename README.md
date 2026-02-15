# fc2_weekly_rank

Small Python project that exports FC2 weekly ranking entries to machine-friendly JSON.

## Quickstart

```bash
python3 run.py
```

`run.py` will:
1. Create `.venv/` if missing.
2. Install dependencies from `requirements.txt`.
3. Install Playwright Chromium into `.pw-browsers/`.
4. Run the scraper (`step_1_rank.py`).
5. Write output JSON to `out/fc2_weekly_top.json` by default.

## Common options

```bash
python3 run.py --help
python3 run.py --limit 50
python3 run.py --mode requests --save-debug
python3 run.py --mode playwright
python3 run.py --mode playwright --headless
```

- Default Playwright behavior is **headful**.
- Use `--headless` for unattended runs.
- `--headful` is optional and kept for explicitness; `--headful`/`--headless` are mutually exclusive.
- Cookies/session data are stored in `.fc2_profile/`.
- Playwright browser binaries are stored in `.pw-browsers/`.
- JSON output goes to `out/`.

Quick sanity check:

```bash
python3 step_1_rank.py --help
```

## Step 2: extract FC2 codes from a specific URL

Step 2 fetches one specific URL provided by `--in` and extracts FC2 PPV codes.

```bash
.venv/bin/python step_2_extract_codes.py --in https://placeholder.com --out out/fc2_codes_from_file.json
```

More examples:

```bash
.venv/bin/python step_2_extract_codes.py --in https://placeholder.com --mode unique
.venv/bin/python step_2_extract_codes.py --in https://placeholder.com --mode all --include-context
```

- Step 2 normalizes matches to `FC2-PPV-<digits>`.
- `rank` means **order of first appearance** for `unique_codes`.

## Troubleshooting

- **Parsed 0 entries**
  - Re-run with `--save-debug` to write `debug_requests.html` / `debug_rendered.html` and inspect the fetched page.
- **Possible age gate / verification page**
  - Re-run without `--headless` (or with `--headful`), complete verification manually in the launched browser, then run again.

## Notes

- The scraper does not attempt to bypass age verification or authentication.
- Output schema is stable for downstream pipelines and includes timestamp metadata plus `top_entries`.
