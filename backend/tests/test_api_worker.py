import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from app import worker
from app.db import SessionLocal
from app.main import app
from app.models import Case, Chunk, Document, Job, Page, ProcessingRun
from app.services.exports import csv_safe
from app.worker import claim_job, process_claim, run_once
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import select

from .conftest import register

ROOT = Path(__file__).resolve().parents[2]


def upload(client, case, filenames=("both_po.pdf", "both_invoice.pdf")):
    files = [
        ("files", (name, (ROOT / "sample_data" / name).read_bytes(), "application/pdf"))
        for name in filenames
    ]
    response = client.post(f"/api/cases/{case['id']}/documents", files=files)
    assert response.status_code == 201, response.text
    return response.json()


def process_all():
    count = 0
    while run_once():
        count += 1
        assert count < 30


def test_full_api_journey_and_corrections(client, case):
    docs = upload(client, case)
    process_all()
    findings = client.get(f"/api/cases/{case['id']}/findings").json()
    assert {"quantity_difference", "unit_price_difference", "subtotal_difference"} <= {
        f["kind"] for f in findings
    }
    detail = client.get(f"/api/documents/{docs[1]['id']}").json()
    assert detail["data"]["line_items"][0]["quantity"] == "120"
    updated = detail["data"]
    updated["line_items"][0].update(quantity="100", unit_price="80", amount="8000")
    updated["subtotal"] = updated["total"] = "8000"
    response = client.put(f"/api/documents/{docs[1]['id']}/correction", json=updated)
    assert response.status_code == 200, response.text
    assert client.get(f"/api/cases/{case['id']}/findings").json() == []
    detail = client.get(f"/api/documents/{docs[1]['id']}").json()
    assert detail["original"]["line_items"][0]["quantity"] == "120"
    assert detail["data"]["line_items"][0]["quantity"] == "100"
    assert detail["corrections"][0]["before"]["line_items"][0]["quantity"] == "120"
    case_data = client.get(f"/api/cases/{case['id']}").json()
    assert case_data["revision"] == case_data["verified_revision"]
    export = client.get(f"/api/cases/{case['id']}/export.json")
    assert export.json()["documents"][1]["data"]["subtotal"] == "8000"
    assert "attachment" in export.headers["content-disposition"]
    assert client.get(f"/api/cases/{case['id']}/findings.csv").text.startswith("kind,severity")
    assert client.get(f"/api/documents/{docs[0]['id']}/file").content.startswith(b"%PDF-")


def test_citations_real_sources_no_key_and_case_isolation(client, case):
    docs = upload(client, case)
    process_all()
    other = client.post("/api/cases", json={"name": "Different case"}).json()
    upload(client, other, ("sample_quotation.pdf",))
    process_all()
    result = client.post(f"/api/cases/{case['id']}/search", json={"query": "Copper cable"}).json()
    assert result["answer"] is None
    assert result["generation_status"] == "Evidence search — answer generation not configured."
    assert result["evidence"]
    assert all(e["document_id"] in {d["id"] for d in docs} for e in result["evidence"])
    with SessionLocal() as db:
        for source in result["evidence"]:
            chunk = db.get(Chunk, source["id"])
            assert chunk.document_id == source["document_id"]
            assert db.scalar(
                select(Page).where(
                    Page.document_id == source["document_id"], Page.number == source["page"]
                )
            )
    for finding in result["verification"]:
        for source in finding["sources"]:
            assert source["document_id"] in {d["id"] for d in docs}
            assert source["page"] == 1


@pytest.mark.parametrize(
    "path",
    [
        "case",
        "findings",
        "search",
        "json",
        "csv",
        "document",
        "file",
        "retry",
        "correct",
        "delete_document",
        "delete_case",
        "rename",
        "upload",
        "review",
    ],
)
def test_other_user_cannot_access_any_route(client, case, path):
    docs = upload(client, case)
    process_all()
    with TestClient(app) as intruder:
        register(intruder, f"intruder-{path}@example.test")
        c, d = case["id"], docs[0]["id"]
        operations = {
            "case": ("get", f"/api/cases/{c}", {}),
            "findings": ("get", f"/api/cases/{c}/findings", {}),
            "search": ("post", f"/api/cases/{c}/search", {"json": {"query": "Copper"}}),
            "json": ("get", f"/api/cases/{c}/export.json", {}),
            "csv": ("get", f"/api/cases/{c}/findings.csv", {}),
            "document": ("get", f"/api/documents/{d}", {}),
            "file": ("get", f"/api/documents/{d}/file", {}),
            "retry": ("post", f"/api/documents/{d}/retry", {}),
            "correct": ("put", f"/api/documents/{d}/correction", {"json": {}}),
            "delete_document": ("delete", f"/api/documents/{d}", {}),
            "delete_case": ("delete", f"/api/cases/{c}", {}),
            "rename": ("patch", f"/api/cases/{c}", {"json": {"name": "Owned?"}}),
            "upload": (
                "post",
                f"/api/cases/{c}/documents",
                {"files": {"files": ("bad.pdf", b"bad", "application/pdf")}},
            ),
            "review": (
                "patch",
                f"/api/cases/{c}/findings/unknown",
                {"json": {"review_status": "resolved"}},
            ),
        }
        method, url, kwargs = operations[path]
        assert getattr(intruder, method)(url, **kwargs).status_code == 404
        assert intruder.get("/api/cases").json() == []


def test_csrf_origin_and_logout(client, account):
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/cases", json={"name": "Unsafe"}).status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert (
        client.post(
            "/api/cases", json={"name": "Unsafe"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/cases").status_code == 401


def test_invalid_and_oversize_uploads(client, case, monkeypatch):
    for content in (b"not a PDF", b"%PDF-1.7 garbage"):
        response = client.post(
            f"/api/cases/{case['id']}/documents",
            files={"files": ("invoice.pdf", content, "application/pdf")},
        )
        assert response.status_code == 400
    monkeypatch.setattr(worker.settings(), "max_file_mb", 1)
    assert (
        client.post(
            f"/api/cases/{case['id']}/documents",
            files={"files": ("x.pdf", b"%PDF-" + b"x" * (1024 * 1024), "application/pdf")},
        ).status_code
        == 413
    )
    assert client.get(f"/api/cases/{case['id']}").json()["document_count"] == 0


def test_page_limit_and_ocr_required(client, case):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for _ in range(31):
        pdf.drawString(50, 700, "Synthetic PDF page")
        pdf.showPage()
    pdf.save()
    assert (
        client.post(
            f"/api/cases/{case['id']}/documents",
            files={"files": ("long.pdf", output.getvalue(), "application/pdf")},
        ).status_code
        == 400
    )
    blank = io.BytesIO()
    pdf = canvas.Canvas(blank)
    pdf.rect(10, 10, 100, 100)
    pdf.showPage()
    pdf.save()
    response = client.post(
        f"/api/cases/{case['id']}/documents",
        files={"files": ("scanned.pdf", blank.getvalue(), "application/pdf")},
    )
    assert response.status_code == 201
    process_all()
    doc = client.get(f"/api/documents/{response.json()[0]['id']}").json()
    assert doc["status"] == "failed" and "OCR required" in doc["error"]


def test_jobs_atomic_claim_stale_recovery_and_idempotency(client, case):
    docs = upload(client, case, ("both_po.pdf",))

    def claim():
        with SessionLocal() as db:
            return claim_job(db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(), [0, 1]))
    actual = [c for c in claims if c]
    assert len(actual) == 1
    with SessionLocal() as db:
        job = db.scalar(select(Job))
        job.claimed_at = time.time() - 1000
        db.commit()
    recovered = claim()
    assert recovered["token"] != actual[0]["token"]
    process_claim(actual[0])
    assert client.get(f"/api/documents/{docs[0]['id']}").json()["original"] is None
    process_claim(recovered)
    process_claim(recovered)
    with SessionLocal() as db:
        assert len(db.scalars(select(Page)).all()) == 1
        assert len(db.scalars(select(Chunk)).all()) == 1
    assert not run_once()


def test_bounded_retries_and_manual_retry(client, case, monkeypatch):
    docs = upload(client, case, ("both_po.pdf",))

    def transient(*args):
        raise RuntimeError("Synthetic transient failure")

    monkeypatch.setattr(worker, "extract_pdf", transient)
    for attempt in range(3):
        assert run_once()
        with SessionLocal() as db:
            job = db.scalar(select(Job))
            assert job.attempts == attempt + 1
            job.available_at = 0
            db.commit()
    assert not run_once()
    assert client.get(f"/api/documents/{docs[0]['id']}").json()["status"] == "failed"
    assert client.post(f"/api/documents/{docs[0]['id']}/retry").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(Job)).attempts == 0
        assert (
            len(db.scalars(select(ProcessingRun).where(ProcessingRun.status == "failed")).all())
            == 3
        )


def test_exhausted_stale_lease_records_failure_and_refreshes_readiness(client, case):
    docs = upload(client, case, ("matching_po.pdf",))
    with SessionLocal() as db:
        claim_job(db)
        job = db.scalar(select(Job))
        job.attempts = 3
        job.claimed_at = time.time() - 1000
        db.commit()
    assert not run_once()
    assert client.get(f"/api/documents/{docs[0]['id']}").json()["status"] == "failed"
    summary = client.get(f"/api/cases/{case['id']}").json()
    assert summary["readiness"]["status_counts"]["failed"] == 1
    assert not summary["readiness"]["all_documents_checked"]
    assert summary["revision"] == summary["verified_revision"]


def test_demo_expectations_and_explicit_loading(client, account):
    assert client.get("/api/cases").json() == []
    response = client.post("/api/demo")
    assert response.status_code == 201
    process_all()
    manifest = json.loads((ROOT / "sample_data/manifest.json").read_text())
    for case_id, sample in zip(response.json()["case_ids"], manifest["cases"]):
        kinds = {f["kind"] for f in client.get(f"/api/cases/{case_id}/findings").json()}
        assert set(sample["expected_finding_types"]) <= kinds, (sample["name"], kinds)
        if not sample["expected_finding_types"]:
            assert not kinds


@pytest.mark.parametrize(
    "value", ['=HYPERLINK("x")', "+SUM(A1)", "-10", "@IMPORT", "  =formula", "\tunsafe", "\runsafe"]
)
def test_csv_formula_escaping(value):
    assert csv_safe(value).startswith("'")


def test_fabricated_correction_provenance_rejected(client, case):
    doc = upload(client, case, ("both_po.pdf",))[0]
    process_all()
    data = client.get(f"/api/documents/{doc['id']}").json()["data"]
    data["line_items"][0]["source"]["document_id"] = "some-other-document"
    assert client.put(f"/api/documents/{doc['id']}/correction", json=data).status_code == 422


def test_delete_cascades_and_removes_pdf(client, case):
    docs = upload(client, case)
    process_all()
    with SessionLocal() as db:
        path = worker.settings().storage_dir / db.get(Document, docs[0]["id"]).storage_name
    assert path.exists()
    assert client.delete(f"/api/cases/{case['id']}").status_code == 200
    assert not path.exists()
    with SessionLocal() as db:
        for model in (Document, Job, Page, Chunk, Case):
            assert not db.scalars(select(model)).all()
