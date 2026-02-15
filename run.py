#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
PLAYWRIGHT_BROWSERS = ROOT / ".pw-browsers"
REQUIREMENTS = ROOT / "requirements.txt"
SCRAPER = ROOT / "step_1_rank.py"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> None:
    py = venv_python()
    if py.exists():
        return
    print(f"Creating virtual environment at {VENV_DIR}...")
    venv.EnvBuilder(with_pip=True).create(VENV_DIR)


def run_checked(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)


def ensure_dependencies(py: Path) -> None:
    run_checked([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    run_checked([str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)])


def ensure_playwright_chromium(py: Path) -> None:
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    PLAYWRIGHT_BROWSERS.mkdir(parents=True, exist_ok=True)
    run_checked([str(py), "-m", "playwright", "install", "chromium"], env=env)


def run_scraper(py: Path, args: list[str]) -> int:
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    cmd = [str(py), str(SCRAPER), *args]
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def main() -> None:
    ensure_venv()
    py = venv_python()

    help_only = any(arg in {"-h", "--help"} for arg in sys.argv[1:])
    if not help_only:
        ensure_dependencies(py)
        ensure_playwright_chromium(py)

    raise SystemExit(run_scraper(py, sys.argv[1:]))


if __name__ == "__main__":
    main()
