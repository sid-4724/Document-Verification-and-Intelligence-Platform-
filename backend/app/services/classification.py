"""Transparent keyword baseline and a locally trained synthetic TF-IDF model."""

import hashlib
import io
from functools import lru_cache
from pathlib import Path

import joblib

MODEL = Path(__file__).resolve().parents[3] / "evaluation/models/classifier.joblib"


def classification_features(text: str) -> str:
    # Repeated headings emphasize document intent over incidental order references.
    # This is a transparent feature choice, applied identically in training and inference.
    heading = text.splitlines()[0] if text.splitlines() else ""
    return ((heading + "\n") * 10 + text).lower()


def keyword_classify(text: str) -> str:
    text = text.lower()
    # Headings carry more weight than references embedded in invoice bodies.
    heading = "\n".join(text.splitlines()[:5])
    for label, words in (
        ("purchase_order", ["purchase order", "procurement order"]),
        ("quotation", ["quotation", "supplier quote", "price proposal"]),
        ("invoice", ["invoice", "billing statement"]),
    ):
        if any(word in heading for word in words):
            return label
    return "unknown"


@lru_cache
def load_model():
    if not MODEL.exists():
        return None
    try:
        contents = MODEL.read_bytes()
        model = joblib.load(io.BytesIO(contents))
        model.docverify_artifact_sha256 = hashlib.sha256(contents).hexdigest()
        return model
    except (ValueError, OSError, ImportError):
        return None


def classify(text: str) -> dict:
    baseline = keyword_classify(text)
    model = load_model()
    predicted = str(model.predict([text])[0]) if model is not None else None
    return {
        "keyword_prediction": baseline,
        "model_prediction": predicted,
        "model_status": "TF-IDF + logistic regression, trained on synthetic data"
        if model
        else "Model unavailable; run scripts/train_classifier.py",
        "disagreement": predicted is not None and baseline != "unknown" and predicted != baseline,
        "model_metadata": {
            "artifact_sha256": getattr(model, "docverify_artifact_sha256", None),
            "family": "TF-IDF + logistic regression" if model else "keyword rules only",
            "feature_version": "heading-weighted-tfidf-v1",
            "training_data": "synthetic generator families",
        },
    }
