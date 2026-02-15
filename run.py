#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
PLAYWRIGHT_BROWSERS = ROOT / ".pw-browsers"
CONFIG_PATH = ROOT / "toscrape_local.json"


@dataclass(frozen=True)
class ResolvedConfig:
    step1_url: str
    step2_url: str
    code_prefix: str
    seed_source: str


@dataclass(frozen=True)
class Step:
    name: str
    script: str
    args: list[str]
    needs_playwright_env: bool = False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Step 1 -> Step 2 -> Step 3 pipeline with bootstrap support. "
            "Required values can come from CLI flags and/or toscrape_local.json."
        )
    )

    parser.add_argument("--step1-url", help="Input URL for step_1_rank.py")
    parser.add_argument("--step2-url", help="Input URL for step_2_extract_codes.py")
    parser.add_argument("--code-prefix", help="Code prefix for step_2_extract_codes.py")
    parser.add_argument(
        "--seed-source",
        help="Base URL for Step 3 torrent downloads (e.g. https://books.toscrape.com)",
    )

    parser.add_argument("--limit", type=int, help="Forward to step_1_rank.py --limit")
    parser.add_argument(
        "--mode",
        choices=("auto", "requests", "playwright"),
        help="Forward to step_1_rank.py --mode",
    )
    head_group = parser.add_mutually_exclusive_group()
    head_group.add_argument("--headless", action="store_true", help="Forward --headless to Step 1")
    head_group.add_argument("--headful", action="store_true", help="Forward --headful to Step 1")
    parser.add_argument("--profile-dir", help="Forward to step_1_rank.py --profile-dir")
    parser.add_argument("--save-debug", action="store_true", help="Forward --save-debug to Step 1")

    parser.add_argument("--step2-limit", type=int, help="Forward to step_2_extract_codes.py --limit")
    parser.add_argument(
        "--step2-mode",
        choices=("all", "unique"),
        help="Forward to step_2_extract_codes.py --mode",
    )
    ctx_group = parser.add_mutually_exclusive_group()
    ctx_group.add_argument(
        "--include-context",
        dest="include_context",
        action="store_true",
        help="Forward --include-context to Step 2",
    )
    ctx_group.add_argument(
        "--no-include-context",
        dest="include_context",
        action="store_false",
        help="Forward --no-include-context to Step 2",
    )
    parser.set_defaults(include_context=None)

    return parser.parse_args(list(argv))


def load_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {CONFIG_PATH}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"Config at {CONFIG_PATH} must be a JSON object.")

    result: dict[str, str] = {}
    for key in ("step1_url", "step2_url", "code_prefix", "seed_source"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def resolve_config(args: argparse.Namespace, file_cfg: dict[str, str]) -> tuple[ResolvedConfig | None, list[str], dict[str, str]]:
    merged = {
        "step1_url": (args.step1_url or file_cfg.get("step1_url", "")).strip(),
        "step2_url": (args.step2_url or file_cfg.get("step2_url", "")).strip(),
        "code_prefix": (args.code_prefix or file_cfg.get("code_prefix", "")).strip(),
        "seed_source": (args.seed_source or file_cfg.get("seed_source", "")).strip(),
    }
    missing = [key for key, value in merged.items() if not value]

    if missing:
        return None, missing, merged

    cfg = ResolvedConfig(
        step1_url=merged["step1_url"],
        step2_url=merged["step2_url"],
        code_prefix=merged["code_prefix"],
        seed_source=merged["seed_source"],
    )
    return cfg, [], merged


def print_missing_inputs_and_exit(missing: list[str]) -> None:
    print("ERROR: missing required values after merging CLI flags + local config:", file=sys.stderr)
    for key in missing:
        print(f"  - {key}", file=sys.stderr)

    print("\nRun with required flags (example):", file=sys.stderr)
    print(
        "  python3 run.py --step1-url \"https://example.com/ranking\" "
        "--step2-url \"https://example.com/source\" --code-prefix \"item\" "
        "--seed-source \"https://example.com\"",
        file=sys.stderr,
    )

    print(f"\nOr create/update config at: {CONFIG_PATH}", file=sys.stderr)
    print(
        '{\n'
        '  "step1_url": "https://example.com/ranking",\n'
        '  "step2_url": "https://example.com/source",\n'
        '  "code_prefix": "item",\n'
        '  "seed_source": "https://example.com"\n'
        '}',
        file=sys.stderr,
    )
    raise SystemExit(2)


def maybe_write_config(args: argparse.Namespace, cfg: ResolvedConfig) -> None:
    provided_required_cli = any([args.step1_url, args.step2_url, args.code_prefix, args.seed_source])
    if not provided_required_cli:
        return

    payload = {
        "step1_url": cfg.step1_url,
        "step2_url": cfg.step2_url,
        "code_prefix": cfg.code_prefix,
        "seed_source": cfg.seed_source,
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated local config: {CONFIG_PATH}")


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists():
        return py

    print(f"Creating virtual environment at {VENV_DIR} ...")
    venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    return py


def run_checked(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def bootstrap(py: Path) -> None:
    run_checked([str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)])

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    PLAYWRIGHT_BROWSERS.mkdir(parents=True, exist_ok=True)
    run_checked([str(py), "-m", "playwright", "install", "chromium"], env=env)


def build_steps(cfg: ResolvedConfig, args: argparse.Namespace) -> list[Step]:
    step1_args = ["--input-url", cfg.step1_url]
    if args.limit is not None:
        step1_args += ["--limit", str(args.limit)]
    if args.mode:
        step1_args += ["--mode", args.mode]
    if args.headless:
        step1_args.append("--headless")
    if args.headful:
        step1_args.append("--headful")
    if args.profile_dir:
        step1_args += ["--profile-dir", args.profile_dir]
    if args.save_debug:
        step1_args.append("--save-debug")

    step2_args = ["--input-url", cfg.step2_url, "--code-prefix", cfg.code_prefix]
    if args.step2_limit is not None:
        step2_args += ["--limit", str(args.step2_limit)]
    if args.step2_mode:
        step2_args += ["--mode", args.step2_mode]
    if args.include_context is True:
        step2_args.append("--include-context")
    if args.include_context is False:
        step2_args.append("--no-include-context")

    return [
        Step(name="Step 1", script="step_1_rank.py", args=step1_args, needs_playwright_env=True),
        Step(name="Step 2", script="step_2_extract_codes.py", args=step2_args),
        Step(
            name="Step 3",
            script="step_3_common_torrents.py",
            args=["--seed-source", cfg.seed_source],
        ),
        # Step 4 (future): torrent download via qBittorrent, etc.
    ]


def print_plan(cfg: ResolvedConfig) -> None:
    print("Execution plan")
    print(f"- Step 1 URL: {cfg.step1_url}")
    print(f"- Step 2 URL: {cfg.step2_url}")
    print(f"- Code prefix: {cfg.code_prefix}")
    print(f"- Seed source: {cfg.seed_source}")
    print("- Steps: 1 -> 2 -> 3")
    print("- Outputs: artifacts/ (torrents under artifacts/seed)")


def run_steps(py: Path, steps: list[Step]) -> int:
    base_env = os.environ.copy()
    playwright_env = base_env.copy()
    playwright_env["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)

    for step in steps:
        cmd = [str(py), str(ROOT / step.script), *step.args]
        env = playwright_env if step.needs_playwright_env else base_env
        print(f"\nRunning {step.name} ...")
        print("+", " ".join(cmd))
        result = subprocess.run(cmd, cwd=ROOT, env=env)
        if result.returncode != 0:
            return result.returncode
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    file_cfg = load_config()
    resolved, missing, _ = resolve_config(args, file_cfg)
    if missing:
        print_missing_inputs_and_exit(missing)

    assert resolved is not None
    maybe_write_config(args, resolved)

    py = ensure_venv()
    bootstrap(py)

    print_plan(resolved)
    steps = build_steps(resolved, args)
    return run_steps(py, steps)


if __name__ == "__main__":
    raise SystemExit(main())
