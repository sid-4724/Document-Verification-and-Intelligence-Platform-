"""Portable verification entrypoint; live models/providers are deliberately optional."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--browser", action="store_true", help="Requires a running local app and installed Chromium"
    )
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "NEXT_TELEMETRY_DISABLED": "1"}
    commands = [
        [sys.executable, "scripts/generate_samples.py"],
        [sys.executable, "scripts/train_classifier.py"],
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "backend", "scripts"],
        [sys.executable, "-m", "ruff", "format", "--check", "backend", "scripts"],
        ["npm", "--prefix", "frontend", "run", "typecheck"],
    ]
    if not args.skip_build:
        commands.append(["npm", "--prefix", "frontend", "run", "build"])
    commands.append([sys.executable, "scripts/evaluate.py"])
    for command in commands:
        print(
            "Running: " + " ".join(command[1:] if command[0] == sys.executable else command),
            flush=True,
        )
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    if args.browser:
        subprocess.run(["npm", "run", "test:e2e"], cwd=ROOT / "frontend", env=env, check=True)


if __name__ == "__main__":
    main()
