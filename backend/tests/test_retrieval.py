import json

import httpx
import pytest
from app.services import retrieval
from app.services.retrieval import answer_question, retrieve


def test_unanswerable_keyword_query_and_no_key():
    evidence, status = retrieve(
        "galaxy spacecraft",
        [{"id": "1", "document_id": "a", "page": 1, "text": "Copper cable quantity invoice"}],
    )
    assert evidence == []
    answer, ids, status = answer_question("galaxy spacecraft", evidence, [])
    assert answer is None and ids == [] and "not configured" in status


def test_semantic_missing_model_visible_fallback(monkeypatch):
    monkeypatch.setattr(retrieval.settings(), "semantic_enabled", True)
    monkeypatch.setattr(retrieval.settings(), "embedding_model", "/does-not-exist")
    retrieval.embedding_backend.cache_clear()
    try:
        evidence, status = retrieve(
            "Copper", [{"id": "1", "document_id": "a", "page": 1, "text": "Copper cable invoice"}]
        )
        assert evidence and "unavailable" in status
    finally:
        retrieval.embedding_backend.cache_clear()


@pytest.mark.parametrize("ids,accepted", [(["real"], True), (["foreign"], False), ([], False)])
def test_provider_citations_validated(monkeypatch, ids, accepted):
    monkeypatch.setattr(retrieval.settings(), "anthropic_api_key", "synthetic-test-key")

    def fake_post(url, **kwargs):
        assert "untrusted_document_evidence" in kwargs["json"]["messages"][0]["content"]
        assert "untrusted DATA" in kwargs["json"]["system"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"answer": "Copper cable was invoiced.", "source_ids": ids}
                        ),
                    }
                ]
            },
        )

    monkeypatch.setattr(retrieval.httpx, "post", fake_post)
    answer, cited, status = answer_question(
        "What was invoiced?",
        [{"id": "real", "document_id": "a", "page": 1, "text": "Invoice: Copper cable"}],
        [],
    )
    if accepted:
        assert answer and cited == ["real"]
    else:
        assert cited == []
        assert "insufficient" in (answer or "").lower() or "validation failed" in status


def test_provider_failure_does_not_break_evidence(monkeypatch):
    monkeypatch.setattr(retrieval.settings(), "anthropic_api_key", "synthetic-test-key")

    def failure(*args, **kwargs):
        raise httpx.ConnectError("Synthetic network outage")

    monkeypatch.setattr(retrieval.httpx, "post", failure)
    answer, ids, status = answer_question("Copper?", [{"id": "real", "text": "Copper"}], [])
    assert answer is None and ids == [] and "unavailable" in status
