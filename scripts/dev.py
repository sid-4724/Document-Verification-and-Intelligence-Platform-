"""Run migrations, FastAPI, worker, and Next together using a persistent local SQLite DB."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", f"sqlite:///{ROOT}/var/docverify.db")
    env.setdefault("STORAGE_DIR", str(ROOT / "var/uploads"))
    env.setdefault("DEMO_MODE", "true")
    env.setdefault("BACKEND_URL", f"http://127.0.0.1:{args.api_port}")
    env.setdefault("APP_ORIGIN", f"http://localhost:{args.web_port}")
    env.setdefault("NEXT_TELEMETRY_DISABLED", "1")
    env["PYTHONPATH"] = str(ROOT / "backend")
    (ROOT / "var/uploads").mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "scripts/generate_samples.py"], cwd=ROOT, env=env, check=True)
    if not (ROOT / "evaluation/models/classifier.joblib").exists():
        subprocess.run(
            [sys.executable, "scripts/train_classifier.py"], cwd=ROOT, env=env, check=True
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            ROOT,
        ),
        ([sys.executable, "-m", "app.worker"], ROOT),
        (
            ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(args.web_port)],
            ROOT / "frontend",
        ),
    ]
    children = []

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        for command, cwd in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True))
        print(
            f"DocVerify: http://localhost:{args.web_port} — Ctrl+C stops all services", flush=True
        )
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A service exited; see its logs above")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)


if __name__ == "__main__":
    main()
