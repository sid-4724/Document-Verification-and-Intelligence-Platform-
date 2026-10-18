"""Reproducible synthetic training; entire generator families held out at test time."""

import json
import random
from pathlib import Path

import joblib
from app.services.classification import classification_features, keyword_classify
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["purchase_order", "quotation", "invoice"]
HEADINGS = {
    "purchase_order": [
        "PURCHASE ORDER",
        "Procurement order",
        "Purchase order request",
        "Approved purchase order",
    ],
    "quotation": ["SUPPLIER QUOTATION", "Supplier quote", "Price proposal", "Quotation for goods"],
    "invoice": ["INVOICE", "Billing statement", "Invoice for payment", "Tax invoice"],
}
FAMILIES = [
    "{heading}\nDocument number: {identifier}\nSupplier: {supplier}\nCustomer: {customer}\nCopper cable {qty} m at {price}. {action}",
    "{heading}\nFrom {supplier} to {customer}. Reference {identifier}. {action}\nLine: machine brackets {qty} pieces. Unit price {price}",
    "{heading}\n{action} under reference {identifier}.\n{supplier} / {customer}\nNet amount {qty} x {price}; currency INR",
    "{heading}\n{customer}\n{supplier}\nIssued reference {identifier}\nMaterial: packing paper; Quantity {qty}; Rate {price}. {action}",
    "{heading}\nTransaction {identifier} between {supplier} and {customer}.\n{action}. Wooden pallets: {qty} pcs, {price} per piece.",
    "{heading}\n{supplier}: {action}\nRequested by {customer}\nOur ref {identifier}, steel rod {qty} kg at {price}. Total due per attached schedule.",
]


def dataset():
    rng = random.Random(42)
    samples = []
    for family, template in enumerate(FAMILIES):
        for label in LABELS:
            for i in range(40):
                action = {
                    "purchase_order": "Please supply the listed goods as authorized",
                    "quotation": "We offer these prices subject to acceptance",
                    "invoice": "Payment for delivered goods is due in 30 days",
                }[label]
                text = template.format(
                    heading=HEADINGS[label][family % 4],
                    identifier=f"REF-{rng.randrange(1000, 9999)}",
                    supplier=rng.choice(["Copperleaf", "Birch Trading", "Fern Works"]),
                    customer=rng.choice(["Northstar Labs", "Juniper Studio", "Aspen Systems"]),
                    qty=rng.randrange(10, 200),
                    price=rng.randrange(15, 500),
                    action=action,
                )
                samples.append(
                    {"family": family, "label": label, "text": text, "id": f"f{family}-{label}-{i}"}
                )
    return samples


def train():
    samples = dataset()
    train_rows = [s for s in samples if s["family"] < 4]
    test = [s for s in samples if s["family"] >= 4]
    model = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2), sublinear_tf=True, preprocessor=classification_features
                ),
            ),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42, C=1.0)),
        ]
    )
    model.fit([s["text"] for s in train_rows], [s["label"] for s in train_rows])
    labels = [s["label"] for s in test]
    predictions = model.predict([s["text"] for s in test])
    rules = [keyword_classify(s["text"]) for s in test]
    metrics = {
        "synthetic_only": True,
        "seed": 42,
        "dataset_size": len(samples),
        "train_size": len(train_rows),
        "test_size": len(test),
        "train_families": [0, 1, 2, 3],
        "test_families": [4, 5],
        "labels": LABELS,
        "feature_configuration": "Unigram/bigram TF-IDF with first-line heading repeated 10 times, sublinear TF, logistic C=1.0",
        "tfidf_logistic_macro_f1": f1_score(labels, predictions, average="macro"),
        "keyword_macro_f1": f1_score(labels, rules, average="macro"),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=LABELS).tolist(),
        "keyword_confusion_matrix": confusion_matrix(labels, rules, labels=LABELS).tolist(),
        "limitation": "Entire templates are held out, but headings and class-specific phrasing repeat. This toy synthetic task does not establish real-world accuracy.",
    }
    (ROOT / "evaluation/models").mkdir(exist_ok=True)
    joblib.dump(model, ROOT / "evaluation/models/classifier.joblib")
    (ROOT / "evaluation/classification_metrics.json").write_text(json.dumps(metrics, indent=2))
    (ROOT / "evaluation/classification_dataset.json").write_text(json.dumps(samples, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    train()
