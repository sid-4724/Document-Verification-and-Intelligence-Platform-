"""Upgrade an isolated old-schema database and verify retained values/history limits."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_legacy_upgrade_preserves_accounts_pdf_metadata_and_reviews(tmp_path):
    path = tmp_path / "migration_test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}", "PYTHONPATH": str(ROOT / "backend")}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "0001"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    raw = {
        "supplier": "Retained fictional supplier",
        "line_items": [{"description": "Cable", "quantity": "2", "source": None}],
        "sources": {},
        "warnings": [],
    }
    corrected = {**raw, "supplier": "Reviewed fictional supplier"}
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            ("user", "migration@example.test", "unchanged-synthetic-hash", 1),
        )
        db.execute(
            "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("case", "user", "Retained case", "0.01", 4, 4, 1),
        )
        db.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "doc",
                "case",
                "fictional.pdf",
                "server-generated.pdf",
                "completed",
                None,
                json.dumps(raw),
                json.dumps(corrected),
                None,
                1,
            ),
        )
        db.execute(
            "INSERT INTO corrections VALUES (?, ?, ?, ?, ?, ?)",
            ("audit", "doc", "user", json.dumps(raw), json.dumps(corrected), 2),
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT email, password_hash FROM users").fetchone() == (
            "migration@example.test",
            "unchanged-synthetic-hash",
        )
        filename, storage_name, original, effective, status = db.execute(
            "SELECT filename, storage_name, original, corrected, status FROM documents"
        ).fetchone()
        assert filename == "fictional.pdf" and storage_name == "server-generated.pdf"
        assert json.loads(original)["supplier"] == raw["supplier"]
        assert json.loads(effective)["supplier"] == corrected["supplier"]
        assert json.loads(original)["line_items"][0]["id"]
        assert status == "needs_review"
        metadata, created_at = db.execute(
            "SELECT metadata_json, created_at FROM processing_runs"
        ).fetchone()
        assert json.loads(metadata)["origin"] == "legacy_retained_snapshot" and created_at is None
        assert db.execute("SELECT extraction_revision FROM corrections").fetchone()[0] is None
        assert db.execute("SELECT revision > verified_revision FROM cases").fetchone()[0] == 1
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
        assert db.execute("SELECT COUNT(*) FROM file_deletions").fetchone()[0] == 0
