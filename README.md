# toscrape_daily_rank

Small Python project with a 3-step pipeline:
1. Step 1 (`step_1_rank.py`): scrape ranking/listing entries into JSON and generate normalized codes using `--code-prefix`.
2. Step 2 (`step_2_extract_codes.py`): extract normalized codes from a URL.
3. Step 3 (`step_3_common_torrents.py`): intersect codes and download matching torrents.

Canonical code format across all steps is:
- Split `code_prefix` by whitespace, underscore, or hyphen.
- Uppercase tokens and join with `-`.
- Final code shape: `<CANON_PREFIX>-<digits>` (example: `fc2 ppv` + `1234567` => `FC2-PPV-1234567`).

`run.py` is the recommended entrypoint for running Step 1 -> Step 2 -> Step 3 reliably.

## Quickstart (recommended)

First run: provide all required values once.

```bash
python3 run.py \
  --step1-url "https://example.com/ranking" \
  --step2-url "https://example.com/source" \
  --code-prefix "item" \
  --seed-source "https://books.toscrape.com"
```

What `run.py` does:
1. Validates required inputs (`step1_url`, `step2_url`, `code_prefix`, `seed_source`) from CLI + config.
2. Creates `.venv/` if missing.
3. Installs dependencies from `requirements.txt`.
4. Installs Playwright Chromium under `.pw-browsers/`.
5. Runs Step 1 -> Step 2 -> Step 3 with the venv Python.

When you provide any required value via CLI, `run.py` writes/updates `toscrape_local.json` with final resolved values.

Subsequent runs can use saved config:

```bash
python3 run.py
```

## Local config (`toscrape_local.json`)

`toscrape_local.json` lives at repo root and is gitignored (safe for personal URLs).

Schema:

```json
{
  "step1_url": "https://....",
  "step2_url": "https://....",
  "code_prefix": "item",
  "seed_source": "https://books.toscrape.com"
}
```

A tracked template is provided as `toscrape_local.example.json`.

CLI flags override config values.

## Wrapper flags

### Required (from CLI and/or config)
- `--step1-url`
- `--step2-url`
- `--code-prefix`
- `--seed-source`

`--code-prefix` must not contain numeric-only tokens (for example, `FC2-123456` is rejected).
This prevents false canonical-code matches in Step 3.

If any required value is missing, `run.py` exits non-zero and prints:
- missing keys,
- an exact example command,
- config path + JSON example.

### Optional forwarded flags

Step 1 forwards:
- wrapper-required `--code-prefix <text>` (resolved from CLI/config and passed to Step 1 + Step 2 + Step 3)
- `--limit <int>`
- `--mode <auto|requests|playwright>`
- `--headless` / `--headful`
- `--profile-dir <path>`
- `--save-debug`

Step 2 forwards:
- `--step2-limit <int>` (forwards as `--limit`)
- `--step2-mode <all|unique>` (forwards as `--mode`)
- `--include-context` / `--no-include-context`

Step 3 runs with wrapper args:
- `--code-prefix <text>` (resolved from CLI/config; used for canonical matching in Step 3)
- `--seed-source <url>` (forms torrent URLs as `<seed_source>/download/<id>.torrent`)

## Running steps individually

The step scripts are unchanged and still runnable directly:

```bash
python3 step_1_rank.py --input-url "https://example.com/ranking" --code-prefix "item"
python3 step_2_extract_codes.py --input-url "https://example.com/source" --code-prefix "item"
python3 step_3_common_torrents.py --code-prefix "fc2 ppv"
```

## Output locations

- Primary outputs are under `artifacts/`.
- Torrent files are under `artifacts/seed/`.
