import numpy as np
from app.services import retrieval


class FakeEmbedder:
    def get_sentence_embedding_dimension(self):
        return 2

    def encode(self, texts, normalize_embeddings=True):
        return np.array([[1.0, 0.0] for _ in texts])


def test_semantic_vectors_require_matching_resolved_metadata(monkeypatch):
    model = FakeEmbedder()
    monkeypatch.setattr(retrieval.settings(), "embedding_revision", "synthetic-model-commit")
    monkeypatch.setattr(
        retrieval, "embedding_backend", lambda: (model, "Synthetic semantic mechanics test")
    )
    metadata = retrieval.embedding_metadata(model)
    chunk = {
        "id": "real-source",
        "document_id": "doc",
        "page": 2,
        "text": "Copper cable",
        "embedding": [1.0, 0.0],
        "embedding_meta": metadata,
    }
    evidence, status = retrieval.retrieve("wire", [chunk])
    assert evidence[0]["score"] == 1.0
    for incompatible in (
        None,
        {**metadata, "resolved_revision": "different"},
        {**metadata, "dimension": 3},
        {**metadata, "model_identifier": "another-model"},
    ):
        evidence, status = retrieval.retrieve("Copper", [{**chunk, "embedding_meta": incompatible}])
        assert evidence and "incompatible" in status
        assert evidence[0]["score"] != 1.0


def test_chunk_metadata_records_model_and_page(monkeypatch):
    model = FakeEmbedder()
    monkeypatch.setattr(retrieval.settings(), "embedding_revision", "synthetic-model-commit")
    monkeypatch.setattr(retrieval, "embedding_backend", lambda: (model, "synthetic"))
    chunks = retrieval.make_chunks([{"number": 2, "text": "Copper cable quantity 100"}])
    assert chunks[0]["page"] == 2
    assert chunks[0]["embedding_meta"]["resolved_revision"] == "synthetic-model-commit"
    assert chunks[0]["embedding_meta"]["normalized"]


def test_optional_encode_failure_keeps_keyword_chunks(monkeypatch):
    class BrokenModel(FakeEmbedder):
        def encode(self, *args, **kwargs):
            raise RuntimeError("Synthetic model outage")

    monkeypatch.setattr(retrieval, "embedding_backend", lambda: (BrokenModel(), "synthetic"))
    chunks = retrieval.make_chunks([{"number": 1, "text": "Copper cable"}])
    assert chunks and chunks[0].get("embedding") is None
