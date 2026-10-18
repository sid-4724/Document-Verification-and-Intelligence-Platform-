"""Seed an isolated random account, restart services yourself, then check durable data."""

import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "var/persistence-check.json"


def business_snapshot(value):
    """Ignore only additive identity/provenance fields when checking a pre-migration snapshot."""
    if isinstance(value, dict):
        return {
            key: business_snapshot(item)
            for key, item in value.items()
            if key not in {"id", "revision", "extraction_revision", "source_warnings"}
        }
    if isinstance(value, list):
        return [business_snapshot(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["seed", "check"])
    parser.add_argument("--url", default="http://localhost:3000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=30) as client:
        if args.phase == "seed":
            response = client.post(
                "/api/auth/register",
                json={
                    "email": f"persistence-{secrets.token_hex(6)}@example.test",
                    "password": secrets.token_urlsafe(24),
                },
            )
            response.raise_for_status()
            client.headers["X-CSRF-Token"] = response.json()["csrf"]
            response = client.post("/api/cases", json={"name": "Persistence check (synthetic)"})
            response.raise_for_status()
            case_id = response.json()["id"]
            response = client.post(
                f"/api/cases/{case_id}/documents",
                files={
                    "files": (
                        "matching_po.pdf",
                        (ROOT / "sample_data/matching_po.pdf").read_bytes(),
                        "application/pdf",
                    )
                },
            )
            response.raise_for_status()
            document_id = response.json()[0]["id"]
            for _ in range(60):
                response = client.get(f"/api/documents/{document_id}")
                response.raise_for_status()
                if response.json()["status"] in {"completed", "needs_review", "failed"}:
                    break
                time.sleep(1)
            assert response.json()["status"] != "failed", response.text
            assert response.json()["original"] is not None, "Processing did not complete within 60s"
            file = client.get(f"/api/documents/{document_id}/file")
            file.raise_for_status()
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(
                json.dumps(
                    {
                        "cookies": dict(client.cookies),
                        "case_id": case_id,
                        "document_id": document_id,
                        "sha256": hashlib.sha256(file.content).hexdigest(),
                        "original": response.json()["original"],
                    }
                )
            )
            STATE.chmod(0o600)
            print(
                "Seeded a synthetic account and processed PDF. Restart services, then run the check phase."
            )
        else:
            state = json.loads(STATE.read_text())
            client.cookies.update(state["cookies"])
            response = client.get(f"/api/cases/{state['case_id']}")
            response.raise_for_status()
            assert response.json()["document_count"] == 1
            response = client.get(f"/api/documents/{state['document_id']}")
            response.raise_for_status()
            assert business_snapshot(response.json()["original"]) == business_snapshot(
                state["original"]
            )
            file = client.get(f"/api/documents/{state['document_id']}/file")
            file.raise_for_status()
            assert hashlib.sha256(file.content).hexdigest() == state["sha256"]
            print(
                "Persistence verified: session, case, extraction, and original PDF survived restart."
            )


if __name__ == "__main__":
    main()
