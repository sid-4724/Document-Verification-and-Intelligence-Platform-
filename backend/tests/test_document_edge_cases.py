"""Small, fictional examples for the independent review; no provider calls."""

import errno
import io
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from app import worker
from app.api import documents
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Document, FileDeletion, Job
from app.schemas import Extraction
from app.services import retrieval
from app.services.extraction import number, parse_pages
from app.services.matching import match_candidates, normalize
from app.services.verification import verify_documents
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .conftest import register
from .test_api_worker import process_all, upload


def post_pdf(client, case, content, filename="input.pdf"):
    return client.post(
        f"/api/cases/{case['id']}/documents",
        files={"files": (filename, content, "application/pdf")},
    )


def sample_pdf():
    root = Path(__file__).resolve().parents[2]
    return (root / "sample_data/matching_po.pdf").read_bytes()


@pytest.mark.parametrize("value", ["12,34", "1.234,56", "1 2", "1,23,4", "1e4"])
def test_ambiguous_amount_stays_unknown(value):
    assert number(value) is None


@pytest.mark.parametrize(
    "value, expected",
    [("1,234.56", "1234.56"), ("1,23,456.78", "123456.78"), ("₹ 80.50", "80.50"), ("0", "0")],
)
def test_supported_amounts(value, expected):
    assert number(value) == Decimal(expected)


def test_non_english_identifiers_are_not_discarded():
    left = [{"sku": "部品甲", "description": "Cable"}]
    right = [{"sku": "部品乙", "description": "Cable"}]
    assert match_candidates(left, right)[0]["conflict"] is True
    assert normalize("हिंदी") != normalize("हद")
    assert normalize("Café") == normalize("Cafe\u0301")
    rows = [{"description": "铜电缆"}]
    assert match_candidates(rows, rows)[0]["method"] == "exact_description"


@pytest.mark.parametrize(
    "line, field",
    [
        ("Currency: inr", "currency"),
        ("Tax rate: 150%", "tax_rate"),
        ("Supplier: " + "A" * 301, "supplier"),
    ],
)
def test_extracted_fields_obey_the_review_schema(line, field):
    data = parse_pages([{"number": 1, "text": "INVOICE\n" + line}], "doc")
    Extraction.model_validate(data)
    if field == "currency":
        assert data[field] == "INR"
    else:
        assert data[field] is None
        assert data["source_warnings"]


def test_one_oversized_row_does_not_crash_the_whole_extraction():
    text = "INVOICE\nA1 | " + "a" * 501 + " | 1 | m | 2 | 2\nA2 | Cable | 1 | m | 2 | 2"
    data = parse_pages([{"number": 1, "text": text}], "doc")
    assert len(data["line_items"]) == 1
    assert any(w["kind"] == "invalid_row" for w in data["source_warnings"])


def test_row_limit_is_enforced_during_extraction():
    text = "INVOICE\n" + "\n".join(f"A{i} | Cable | 1 | m | 2 | 2" for i in range(201))
    data = parse_pages([{"number": 1, "text": text}], "doc")
    Extraction.model_validate(data)
    assert len(data["line_items"]) == 200
    assert any(w["kind"] == "row_limit" for w in data["source_warnings"])


def test_unicode_names_and_missing_values_are_preserved():
    data = parse_pages(
        [
            {
                "number": 1,
                "text": "INVOICE\nSupplier: José & Sons / शर्मा\nCustomer: 李明\nTotal: ?\nA1 | Cable | ? | m | 2 | ?",
            }
        ],
        "doc",
    )
    assert data["supplier"] == "José & Sons / शर्मा"
    assert data["customer"] == "李明"
    assert data["total"] is None
    assert data["line_items"][0]["quantity"] is None


def test_omitted_rows_do_not_prove_subtotal_is_wrong():
    rows = "\n".join(f"A{i} | Cable | 1 | m | 1 | 1" for i in range(201))
    data = parse_pages([{"number": 1, "text": f"INVOICE\n{rows}\nSubtotal: 201"}], "doc")
    findings = verify_documents([{"id": "doc", "filename": "large.pdf", "data": data}])
    assert any(finding["kind"] == "extraction_uncertainty" for finding in findings)
    assert not any(finding["rule"] == "subtotal_line_sum" for finding in findings)


def test_retry_stops_presenting_old_comparisons_as_current(client, case):
    docs = upload(client, case)
    process_all()
    current = client.get(f"/api/cases/{case['id']}").json()
    response = client.put(
        f"/api/cases/{case['id']}/comparison",
        json={
            "revision": current["revision"],
            "reference_document_id": docs[0]["id"],
            "target_document_ids": [docs[1]["id"]],
        },
    )
    revision = response.json()["revision"]
    assert client.post(f"/api/documents/{docs[1]['id']}/retry").status_code == 200
    updated = client.get(f"/api/cases/{case['id']}").json()
    assert updated["revision"] > revision
    findings = client.get(f"/api/cases/{case['id']}/findings").json()
    assert any(item["kind"] == "comparison_not_ready" for item in findings)
    assert not any(item["kind"] == "quantity_difference" for item in findings)


@pytest.mark.parametrize("body", [{"content": [None]}, {"content": ["bad"]}, {"content": None}, []])
def test_malformed_provider_response_falls_back(monkeypatch, body):
    monkeypatch.setattr(settings(), "anthropic_api_key", "fictional-test-key")

    def reply(url, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    monkeypatch.setattr(retrieval.httpx, "post", reply)
    answer, ids, status = retrieval.answer_question("Cable?", [{"id": "one", "text": "Cable"}], [])
    assert answer is None and ids == [] and "unavailable" in status


def test_provider_timeout_preserves_evidence(monkeypatch):
    monkeypatch.setattr(settings(), "anthropic_api_key", "fictional-test-key")

    def timeout(url, **kwargs):
        assert kwargs["timeout"] == 30
        raise httpx.ReadTimeout("Fictional provider timeout")

    monkeypatch.setattr(retrieval.httpx, "post", timeout)
    answer, ids, status = retrieval.answer_question("Cable?", [{"id": "one", "text": "Cable"}], [])
    assert answer is None and ids == [] and "unavailable" in status


@pytest.mark.parametrize("content", [b"", b"%PDF-1.7 corrupted", b"\x89PNG\r\n\x1a\nimage"])
def test_empty_corrupt_and_disguised_images_are_rejected(client, case, content):
    before = set(settings().storage_dir.iterdir())
    response = post_pdf(client, case, content)
    assert response.status_code == 400
    assert set(settings().storage_dir.iterdir()) == before
    assert client.get(f"/api/cases/{case['id']}").json()["document_count"] == 0


def test_password_protected_pdf_is_rejected(client, case):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, encrypt=StandardEncryption("fictional-password"))
    pdf.drawString(40, 700, "INVOICE: Private synthetic example")
    pdf.save()
    response = post_pdf(client, case, output.getvalue())
    assert response.status_code == 400
    assert "encrypted" in response.json()["detail"]


@pytest.mark.parametrize("scan_kind", ["blurred", "rotated", "low_resolution"])
def test_image_only_pdf_explicitly_requires_ocr(client, case, scan_kind):
    scan = Image.new("RGB", (500, 100), "white")
    ImageDraw.Draw(scan).text((20, 20), "INVOICE TOTAL 100", fill="black")
    if scan_kind == "blurred":
        scan = scan.filter(ImageFilter.GaussianBlur(4))
    elif scan_kind == "rotated":
        scan = scan.rotate(90, expand=True)
    else:
        scan = scan.resize((50, 10))
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawImage(ImageReader(scan), 40, 500, width=300, height=200)
    pdf.save()
    response = post_pdf(client, case, output.getvalue())
    assert response.status_code == 201
    process_all()
    document = client.get(f"/api/documents/{response.json()[0]['id']}").json()
    assert document["status"] == "failed"
    assert "OCR required" in document["error"]


def test_content_validation_and_server_generated_storage_path(client, case):
    response = post_pdf(client, case, sample_pdf(), "../../outside.txt")
    assert response.status_code == 201
    identifier = response.json()[0]["id"]
    with SessionLocal() as db:
        document = db.get(Document, identifier)
        assert document.filename == "outside.txt"
        assert document.storage_name == f"{identifier}.pdf"
    assert (settings().storage_dir / f"{identifier}.pdf").is_file()


def test_duplicate_uploads_remain_separate_and_private(client, case):
    first = post_pdf(client, case, sample_pdf()).json()[0]
    second = post_pdf(client, case, sample_pdf()).json()[0]
    assert first["id"] != second["id"]
    with TestClient(app) as other:
        register(other, "other-upload@example.test")
        other_case = other.post("/api/cases", json={"name": "Other"}).json()
        third = post_pdf(other, other_case, sample_pdf()).json()[0]
        assert third["id"] not in {first["id"], second["id"]}
        assert other.get(f"/api/documents/{first['id']}/file").status_code == 404
        assert client.get(f"/api/documents/{third['id']}/file").status_code == 404


def test_database_failure_rolls_back_upload_and_returns_safe_error(client, case, monkeypatch):
    before = set(settings().storage_dir.iterdir())

    def unavailable(*args, **kwargs):
        raise OperationalError(
            "INSERT fictional", {"name": "PRIVATE_SENTINEL"}, Exception("offline")
        )

    monkeypatch.setattr(documents, "refresh_case", unavailable)
    with TestClient(app, raise_server_exceptions=False) as requester:
        requester.cookies.update(client.cookies)
        requester.headers.update(client.headers)
        response = post_pdf(requester, case, sample_pdf())
    assert response.status_code == 503
    assert "PRIVATE_SENTINEL" not in response.text
    assert set(settings().storage_dir.iterdir()) == before
    with SessionLocal() as db:
        assert db.scalars(select(Document)).all() == []
        assert db.scalars(select(Job)).all() == []


def test_lost_commit_reply_does_not_delete_a_committed_pdf(client, case, monkeypatch):
    original_commit = Session.commit

    def lost_reply(db):
        original_commit(db)
        raise OperationalError("COMMIT", {}, Exception("Fictional lost commit reply"))

    monkeypatch.setattr(Session, "commit", lost_reply)
    response = post_pdf(client, case, sample_pdf())
    assert response.status_code == 503
    assert "refresh" in response.json()["detail"]
    with SessionLocal() as db:
        document = db.scalar(select(Document))
        assert document is not None
        assert (settings().storage_dir / document.storage_name).read_bytes() == sample_pdf()


def test_second_file_storage_failure_rolls_back_the_batch(client, case, monkeypatch):
    before = set(settings().storage_dir.iterdir())
    real_open = Path.open
    written_files = 0

    def broken_open(path, mode="r", *args, **kwargs):
        nonlocal written_files
        if path.parent == settings().storage_dir and mode == "xb":
            written_files += 1
            if written_files == 2:
                raise OSError(errno.ENOSPC, "Fictional full disk")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)
    with TestClient(app, raise_server_exceptions=False) as requester:
        requester.cookies.update(client.cookies)
        requester.headers.update(client.headers)
        response = requester.post(
            f"/api/cases/{case['id']}/documents",
            files=[("files", ("a.pdf", sample_pdf())), ("files", ("b.pdf", sample_pdf()))],
        )
    assert response.status_code == 503
    assert set(settings().storage_dir.iterdir()) == before
    with SessionLocal() as db:
        assert db.scalars(select(Document)).all() == []


def test_worker_does_not_log_document_text_from_exceptions(client, case, monkeypatch, caplog):
    upload(client, case, ("matching_po.pdf",))

    def failure(*args, **kwargs):
        raise RuntimeError("PRIVATE_SENTINEL: fictional name and account number")

    monkeypatch.setattr(worker, "extract_pdf", failure)
    assert worker.run_once()
    assert "document_processing_failed" in caplog.text
    assert "PRIVATE_SENTINEL" not in caplog.text


def test_storage_delete_failure_remains_retryable(client, case, monkeypatch):
    document = upload(client, case, ("matching_po.pdf",))[0]
    real_unlink = Path.unlink

    def denied(path, *args, **kwargs):
        if path.parent == settings().storage_dir:
            raise PermissionError("Fictional storage permission failure")
        return real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", denied)
        with TestClient(app, raise_server_exceptions=False) as requester:
            requester.cookies.update(client.cookies)
            requester.headers.update(client.headers)
            response = requester.delete(f"/api/documents/{document['id']}")
        assert response.status_code == 200
        assert response.json()["storage_cleanup_pending"] is True
        assert client.get(f"/api/documents/{document['id']}").status_code == 404
        with SessionLocal() as db:
            task = db.scalar(select(FileDeletion))
            assert task.attempts == 1
            assert (settings().storage_dir / task.storage_name).exists()
            task.available_at = 0
            db.commit()
    assert worker.run_once()
    with SessionLocal() as db:
        assert db.scalars(select(FileDeletion)).all() == []
    assert not (settings().storage_dir / f"{document['id']}.pdf").exists()
