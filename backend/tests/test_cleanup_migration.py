"""Upgrade a populated isolated v2 schema without dropping records or reviews."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cleanup_upgrade_preserves_populated_v2_and_supports_durable_tasks(tmp_path):
    path = tmp_path / "cleanup_migration_test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}", "PYTHONPATH": str(ROOT / "backend")}
    command = [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade"]
    subprocess.run([*command, "0002"], cwd=ROOT, env=env, check=True, capture_output=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            ("user", "migration@example.test", "fictional-hash", 1),
        )
        db.execute(
            "INSERT INTO cases (id,user_id,name,tolerance,revision,verified_revision,created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("case", "user", "Fictional existing case", "0.01", 4, 4, 1),
        )
    subprocess.run([*command, "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT email,password_hash FROM users").fetchone() == (
            "migration@example.test",
            "fictional-hash",
        )
        assert db.execute("SELECT name,revision,finding_reviews FROM cases").fetchone() == (
            "Fictional existing case",
            4,
            "{}",
        )
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
        db.execute(
            "INSERT INTO file_deletions (storage_name,attempts,available_at,user_id,case_id,reason) VALUES (?, ?, ?, ?, ?, ?)",
            ("server-id.pdf", 1, 0, "user", "case", "logical_removal"),
        )
        db.execute("DELETE FROM cases WHERE id='case'")
        assert (
            db.execute("SELECT storage_name FROM file_deletions").fetchone()[0] == "server-id.pdf"
        )
