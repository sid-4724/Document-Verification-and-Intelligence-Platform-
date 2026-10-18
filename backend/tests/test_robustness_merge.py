"""Gaps verified while merging the supplied ZIP; all failures use fictional markers."""

from pathlib import Path

import httpx
import pytest
from app import worker
from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Document, FileDeletion
from app.schemas import Extraction
from app.services import file_storage, retrieval
from app.services.extraction import parse_pages
from app.services.verification import verify_documents
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .conftest import register
from .test_api_worker import process_all, upload
from .test_document_edge_cases import post_pdf, sample_pdf


def test_manual_and_extracted_currency_share_normalization():
    assert Extraction(currency=" inr ").currency == "INR"
    assert (
        parse_pages([{"number": 1, "text": "INVOICE\nCurrency: inr"}], "doc")["currency"] == "INR"
    )


def test_metadata_warning_does_not_suppress_known_table_sum_error():
    data = parse_pages(
        [
            {
                "number": 1,
                "text": "INVOICE\nSupplier: "
                + "A" * 301
                + "\nA1 | Cable | 2 | m | 1 | 2\nSubtotal: 3",
            }
        ],
        "doc",
    )
    assert data["source_warnings"][0]["kind"] == "invalid_field"
    assert any(
        finding["rule"] == "subtotal_line_sum"
        for finding in verify_documents([{"id": "doc", "filename": "fictional.pdf", "data": data}])
    )


def test_commit_uncertain_and_fresh_read_unavailable_preserves_file(
    client, case, monkeypatch, caplog
):
    def unavailable_commit(db):
        raise OperationalError("COMMIT", {}, Exception("PRIVATE_SENTINEL"))

    def unavailable_session():
        raise OperationalError("SELECT", {}, Exception("PRIVATE_SENTINEL"))

    monkeypatch.setattr(Session, "commit", unavailable_commit)
    monkeypatch.setattr(file_storage, "SessionLocal", unavailable_session)
    response = post_pdf(client, case, sample_pdf())
    assert response.status_code == 503 and "refresh" in response.json()["detail"]
    assert "PRIVATE_SENTINEL" not in caplog.text and "PRIVATE_SENTINEL" not in response.text
    assert len(list(settings().storage_dir.glob("*.pdf"))) >= 1
    with SessionLocal() as db:
        assert not db.scalars(select(Document)).all()


def test_uncertain_uncommitted_upload_is_deferred_then_reconciled(client, case, monkeypatch):
    original_commit = Session.commit
    calls = 0

    def uncertain_first_commit(db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("COMMIT", {}, Exception("Fictional lost connection"))
        original_commit(db)

    monkeypatch.setattr(Session, "commit", uncertain_first_commit)
    response = post_pdf(client, case, sample_pdf())
    assert response.status_code == 503
    with SessionLocal() as db:
        task = db.scalar(select(FileDeletion))
        assert task.reason == "uncertain_upload"
        path = settings().storage_dir / task.storage_name
        assert path.exists()
        task.available_at = 0
        db.commit()
    assert file_storage.retry_one_file_deletion()
    assert not path.exists()


def test_cleanup_never_unlinks_a_referenced_document(client, case):
    document = upload(client, case, ("matching_po.pdf",))[0]
    with SessionLocal() as db:
        stored = db.get(Document, document["id"])
        path = settings().storage_dir / stored.storage_name
        file_storage.schedule_file_deletion(db, stored.storage_name, reason="uncertain_upload")
        db.commit()
    assert file_storage.retry_one_file_deletion()
    assert path.exists()
    with SessionLocal() as db:
        assert not db.scalars(select(FileDeletion)).all()


def test_cleanup_failure_keeps_original_upload_error_and_queues_retry(
    client, case, monkeypatch, caplog
):
    original_unlink = Path.unlink

    def failed_cleanup(path, *args, **kwargs):
        if path.parent == settings().storage_dir:
            raise PermissionError("PRIVATE_SENTINEL")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", failed_cleanup)
        response = post_pdf(client, case, b"not a pdf")
    assert response.status_code == 400 and "not a PDF" in response.json()["detail"]
    assert "PRIVATE_SENTINEL" not in caplog.text
    with SessionLocal() as db:
        task = db.scalar(select(FileDeletion))
        assert task.reason == "upload_rollback"
    assert file_storage.retry_one_file_deletion()


def test_case_deletion_cleanup_is_durable_and_user_scoped(client, case, monkeypatch):
    upload(client, case)
    real_unlink = Path.unlink

    def denied(path, *args, **kwargs):
        if path.parent == settings().storage_dir:
            raise PermissionError("Fictional denial")
        return real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", denied)
        result = client.delete(f"/api/cases/{case['id']}")
    assert result.status_code == 200 and result.json()["storage_cleanup_pending"]
    assert client.get(f"/api/cases/{case['id']}").status_code == 404
    assert client.get("/api/storage-cleanup").json()["pending_count"] == 2
    with TestClient(app) as other:
        register(other, "cleanup-other@example.test")
        assert other.get("/api/storage-cleanup").json() == {"pending_count": 0, "tasks": []}
    with SessionLocal() as db:
        for task in db.scalars(select(FileDeletion)):
            task.available_at = 0
        db.commit()
    assert file_storage.retry_one_file_deletion()
    assert file_storage.retry_one_file_deletion()
    assert client.get("/api/storage-cleanup").json()["pending_count"] == 0


def test_retry_keeps_unchanged_review_but_changed_then_reverted_facts_reopen(
    client, case, monkeypatch
):
    documents = upload(client, case)
    process_all()
    findings = client.get(f"/api/cases/{case['id']}/findings").json()
    quantity = next(finding for finding in findings if finding["kind"] == "quantity_difference")
    client.patch(
        f"/api/cases/{case['id']}/findings/{quantity['id']}", json={"review_status": "acknowledged"}
    )
    client.post(f"/api/documents/{documents[1]['id']}/retry")
    assert not any(
        finding["kind"] == "quantity_difference"
        for finding in client.get(f"/api/cases/{case['id']}/findings").json()
    )
    process_all()
    restored = next(
        finding
        for finding in client.get(f"/api/cases/{case['id']}/findings").json()
        if finding["kind"] == "quantity_difference"
    )
    assert restored["id"] == quantity["id"] and restored["review_status"] == "acknowledged"
    extractor = worker.extract_pdf

    def changed(*args):
        data, pages = extractor(*args)
        data["line_items"][0]["quantity"] = "121"
        return data, pages

    with monkeypatch.context() as patch:
        patch.setattr(worker, "extract_pdf", changed)
        client.post(f"/api/documents/{documents[1]['id']}/retry")
        process_all()
    changed_finding = next(
        finding
        for finding in client.get(f"/api/cases/{case['id']}/findings").json()
        if finding["kind"] == "quantity_difference"
    )
    assert changed_finding["review_status"] == "open"
    client.post(f"/api/documents/{documents[1]['id']}/retry")
    process_all()
    reverted = next(
        finding
        for finding in client.get(f"/api/cases/{case['id']}/findings").json()
        if finding["kind"] == "quantity_difference"
    )
    assert reverted["review_status"] == "open"


@pytest.mark.parametrize("operation", ["index", "metadata", "query"])
def test_embedding_exception_payload_never_enters_logs(monkeypatch, caplog, operation):
    class BrokenModel:
        def get_sentence_embedding_dimension(self):
            return 2

        def encode(self, *args, **kwargs):
            raise RuntimeError("PRIVATE_SENTINEL")

    model = BrokenModel()
    metadata = {"resolved_revision": "fake", "dimension": 2}
    monkeypatch.setattr(retrieval, "embedding_backend", lambda: (model, "synthetic"))
    if operation == "metadata":

        def fail(*args):
            raise RuntimeError("PRIVATE_SENTINEL")

        monkeypatch.setattr(retrieval, "embedding_metadata", fail)
    else:
        monkeypatch.setattr(retrieval, "embedding_metadata", lambda _: metadata)
    if operation == "index":
        retrieval.make_chunks([{"number": 1, "text": "Fictional cable"}])
    else:
        retrieval.retrieve(
            "cable",
            [
                {
                    "id": "one",
                    "text": "Fictional cable",
                    "embedding": [1, 0],
                    "embedding_meta": metadata,
                }
            ],
        )
    assert "PRIVATE_SENTINEL" not in caplog.text


def test_sql_engine_hides_bind_parameters():
    assert engine.hide_parameters


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"content": [{"type": "text", "text": 3}]},
        {"content": [{"type": "text", "text": "[]"}]},
        {"content": [{"type": "text", "text": '{"answer":3,"source_ids":["one"]}'}]},
    ],
)
def test_more_malformed_provider_shapes_remain_fallback(monkeypatch, body):
    monkeypatch.setattr(settings(), "anthropic_api_key", "fictional-test-key")
    monkeypatch.setattr(
        retrieval.httpx,
        "post",
        lambda url, **kwargs: httpx.Response(200, request=httpx.Request("POST", url), json=body),
    )
    answer, citations, status = retrieval.answer_question(
        "Cable?", [{"id": "one", "text": "Fictional cable"}], []
    )
    assert answer is None and citations == [] and "unavailable" in status


def test_malformed_provider_does_not_remove_api_evidence(client, case, monkeypatch):
    upload(client, case)
    process_all()
    monkeypatch.setattr(settings(), "anthropic_api_key", "fictional-test-key")
    monkeypatch.setattr(
        retrieval.httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json={"content": [None]}
        ),
    )
    result = client.post(f"/api/cases/{case['id']}/search", json={"query": "Copper cable"})
    assert result.status_code == 200
    assert result.json()["evidence"] and result.json()["answer"] is None
    assert "unavailable" in result.json()["generation_status"]
