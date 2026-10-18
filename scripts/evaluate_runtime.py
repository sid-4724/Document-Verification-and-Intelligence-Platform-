"""Synthetic case/page/chunk evaluation with thresholds selected ONLY on validation cases."""

import json
from pathlib import Path

from app.config import settings
from app.services.classification import keyword_classify, load_model
from app.services.extraction import extract_pdf
from app.services.retrieval import answer_question, make_chunks, retrieve
from reportlab.pdfgen import canvas
from sklearn.metrics import confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation"


def render(
    path: Path, heading: str, supplier: str, item: str, quantity: int, unit_price: int
) -> None:
    """Two-page fictional PDFs; metadata and line evidence deliberately occupy different pages."""
    if path.exists():
        return
    pdf = canvas.Canvas(str(path))
    lines = [
        heading,
        "SYNTHETIC SAMPLE - FICTIONAL DATA",
        "Document number: " + path.stem,
        "Order reference: " + path.parent.name,
        "Supplier: " + supplier,
        "Customer: Fictional Evaluation Studio",
        "Currency: INR",
    ]
    lines += [
        f"Fictional administrative note {index}: inspection scheduling and packaging details only."
        for index in range(18)
    ]
    for index, line in enumerate(lines):
        pdf.drawString(35, 780 - index * 20, line)
    pdf.showPage()
    lines = [
        "SYNTHETIC SAMPLE - FICTIONAL LINE DETAILS",
        "SKU | Description | Quantity | Unit | Unit price | Amount",
        f"ITEM-01 | {item} | {quantity} | pcs | {unit_price} | {quantity * unit_price}",
        f"Subtotal: {quantity * unit_price}",
        "Tax: 0",
        f"Total: {quantity * unit_price}",
    ]
    lines += [
        f"Fictional administrative note {index}: inspection scheduling and packaging details only."
        for index in range(12)
    ]
    for index, line in enumerate(lines):
        pdf.drawString(35, 780 - index * 20, line)
    pdf.save()


def build_dataset() -> list[dict]:
    specifications = [
        ("validation_cable", "validation", "Copper cable", "wire", "Fern Supply", 100, 120, 80),
        ("validation_bolt", "validation", "Steel bolt M8", "fasteners", "Birch Works", 20, 25, 3),
        ("test_ink", "test", "Printer ink", "printing liquid", "Maple Supply", 12, 15, 40),
        ("test_safety", "test", "Safety glove", "hand protection", "Willow Trading", 30, 40, 9),
        ("test_crate", "test", "Wooden crate", "shipping box", "Cedar Works", 8, 10, 50),
    ]
    cases = []
    for name, split, item, paraphrase, supplier, ordered, invoiced, price in specifications:
        folder = OUT / "runtime_samples" / name
        folder.mkdir(parents=True, exist_ok=True)
        corpus = []
        for identifier, heading, quantity in (
            ("reference", "PURCHASE ORDER", ordered),
            ("target", "INVOICE", invoiced),
        ):
            path = folder / f"{identifier}.pdf"
            render(path, heading, supplier, item, quantity, price)
            _, pages = extract_pdf(path, identifier, 30)
            for index, chunk in enumerate(make_chunks(pages, embed=False)):
                corpus.append(
                    {
                        **chunk,
                        "id": f"{name}:{identifier}:page{chunk['page']}:chunk{index}",
                        "document_id": identifier,
                        "filename": path.name,
                    }
                )
        row_reference = f"ITEM-01 | {item} | {ordered} | pcs | {price} | {ordered * price}"
        row_target = f"ITEM-01 | {item} | {invoiced} | pcs | {price} | {invoiced * price}"
        queries = [
            {
                "query": f"{item} quantity purchase order",
                "support": "answerable",
                "relevant": [{"document_id": "reference", "page": 2, "fragment": row_reference}],
            },
            {
                "query": f"{item} quantity invoice",
                "support": "answerable",
                "relevant": [{"document_id": "target", "page": 2, "fragment": row_target}],
            },
            {
                "query": f"How many {paraphrase} were billed?",
                "support": "answerable",
                "paraphrase": True,
                "relevant": [{"document_id": "target", "page": 2, "fragment": row_target}],
            },
            {
                "query": f"Who is the supplier {supplier}?",
                "support": "answerable",
                "relevant": [
                    {"document_id": "reference", "page": 1, "fragment": f"Supplier: {supplier}"},
                    {"document_id": "target", "page": 1, "fragment": f"Supplier: {supplier}"},
                ],
            },
            {
                "query": "What is the unit price?",
                "support": "ambiguous",
                "relevant": [
                    {"document_id": "reference", "page": 2, "fragment": row_reference},
                    {"document_id": "target", "page": 2, "fragment": row_target},
                ],
            },
            {"query": "What is the supplier bank IBAN?", "support": "unanswerable", "relevant": []},
            {"query": "Warranty expiry date", "support": "unanswerable", "relevant": []},
            {"query": "Shipment tracking AWB", "support": "unanswerable", "relevant": []},
        ]
        cases.append({"case_id": name, "split": split, "chunks": corpus, "queries": queries})
    (OUT / "runtime_dataset.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "label_policy": "Document/page/fragment labels determine gold runtime chunk IDs. Ambiguous price queries require clarification; no support is inferred from shared words.",
                "cases": cases,
            },
            indent=2,
        )
    )
    return cases


def score(cases: list[dict], threshold: float) -> dict:
    recalls, reciprocal, supports = [], [], []
    unsupported_hits = abstentions = total = ambiguous = 0
    rows = []
    for case in cases:
        for query in case["queries"]:
            relevant_ids = {
                chunk["id"]
                for chunk in case["chunks"]
                if any(
                    chunk["document_id"] == label["document_id"]
                    and chunk["page"] == label["page"]
                    and label["fragment"] in chunk["text"]
                    for label in query["relevant"]
                )
            }
            if query["relevant"]:
                assert relevant_ids, "Gold passage labels must point to actual runtime chunks"
            evidence, _ = retrieve(
                query["query"], case["chunks"], mode="keyword", keyword_threshold=threshold
            )
            returned = [chunk["id"] for chunk in evidence]
            recall = len(set(returned) & relevant_ids) / len(relevant_ids) if relevant_ids else None
            rank = next(
                (
                    1 / (index + 1)
                    for index, identifier in enumerate(returned)
                    if identifier in relevant_ids
                ),
                0.0,
            )
            if relevant_ids:
                recalls.append(recall)
                reciprocal.append(rank)
            if query["support"] == "answerable":
                supports.append(bool(set(returned) & relevant_ids))
            if query["support"] == "unanswerable":
                unsupported_hits += bool(returned)
            if query["support"] == "ambiguous":
                ambiguous += 1
            answer, _, generation_status = answer_question(query["query"], evidence, [])
            assert answer is None and "not configured" in generation_status
            total += 1
            abstentions += answer is None
            rows.append(
                {
                    "case": case["case_id"],
                    "query": query["query"],
                    "support_label": query["support"],
                    "gold_chunk_ids": sorted(relevant_ids),
                    "returned_ids": returned,
                    "recall_at_5": recall,
                    "reciprocal_rank": rank,
                }
            )
    return {
        "queries": total,
        "recall_at_5": sum(recalls) / len(recalls),
        "mrr": sum(reciprocal) / len(reciprocal),
        "gold_support_passage_coverage": sum(supports) / len(supports),
        "unanswerable_queries_with_evidence": unsupported_hits,
        "ambiguous_queries_requiring_clarification": ambiguous,
        "no_key_abstentions": abstentions,
        "rows": rows,
    }


def classifier_challenge() -> dict:
    # This separately authored challenge is never fed into classifier training.
    labels = ["purchase_order", "quotation", "invoice", "unknown"]
    intents = {
        "purchase_order": "Please supply the listed goods. This authorizes procurement.",
        "quotation": "We offer these rates subject to your acceptance. Prices valid for thirty days.",
        "invoice": "Payment for delivered goods is due in 30 days. Please settle the billed amount.",
        "unknown": "Delivery acknowledgment: packages received. This receipt gives no price or authorization.",
    }
    examples = []
    for split, title, count in (
        ("validation", "CUSTOMER COPY", 4),
        ("test", "TRANSACTION RECORD", 12),
    ):
        for label in labels:
            for index in range(count):
                text = f"{title}\nFictional supplier Lakeview {index}\nFictional customer Rowan {index}\n{intents[label]}\nGoods: packing materials. Units: {index + 2}. Reference R-{index + 300}."
                examples.append({"split": split, "label": label, "text": text})
    model = load_model()
    assert model is not None, "Run scripts/train_classifier.py first"
    test_rows = [example for example in examples if example["split"] == "test"]
    actual = [example["label"] for example in test_rows]
    predicted = model.predict([example["text"] for example in test_rows])
    rules = [keyword_classify(example["text"]) for example in test_rows]
    result = {
        "synthetic_only": True,
        "labels": labels,
        "validation_size": 16,
        "test_size": len(test_rows),
        "model": "existing heading-weighted TF-IDF + logistic regression; no challenge tuning",
        "macro_f1": f1_score(actual, predicted, labels=labels, average="macro", zero_division=0),
        "keyword_macro_f1": f1_score(
            actual, rules, labels=labels, average="macro", zero_division=0
        ),
        "confusion_matrix": confusion_matrix(actual, predicted, labels=labels).tolist(),
        "keyword_confusion_matrix": confusion_matrix(actual, rules, labels=labels).tolist(),
        "limitation": "Repeated synthetic intents still make this small challenge artificial. The trained classifier has no unknown-class detector and cannot emit unknown.",
    }
    (OUT / "classification_challenge_dataset.json").write_text(json.dumps(examples, indent=2))
    (OUT / "classification_challenge_metrics.json").write_text(json.dumps(result, indent=2))
    return result


def evaluate_runtime() -> dict:
    settings().anthropic_api_key = ""  # This offline evaluation never contacts a provider.
    cases = build_dataset()
    validation = [case for case in cases if case["split"] == "validation"]
    test = [case for case in cases if case["split"] == "test"]
    candidates = [0.035, 0.02, 0.06, 0.1, 0.16]
    validation_results = [
        {"threshold": threshold, "metrics": score(validation, threshold)}
        for threshold in candidates
    ]
    # Objective fixed before examining the test: support coverage, then fewer false hits,
    # then recall. Stable ties keep the previous default (first candidate).
    chosen = max(
        validation_results,
        key=lambda result: (
            result["metrics"]["gold_support_passage_coverage"],
            -result["metrics"]["unanswerable_queries_with_evidence"],
            result["metrics"]["recall_at_5"],
        ),
    )
    config = {
        "keyword_min_score": chosen["threshold"],
        "selected_from": "validation_cable, validation_bolt only",
        "objective": "support passage coverage; fewer unsupported evidence hits; recall; stable default tie",
        "chunking": "page-lines-700-overlap2-v1",
    }
    (OUT / "retrieval_validation_config.json").write_text(json.dumps(config, indent=2))
    result = {
        "synthetic_only": True,
        "evaluation_level": "case-scoped runtime page chunks",
        "method": "runtime make_chunks + retrieve(mode=keyword)",
        "config": config,
        "validation_cases": 2,
        "test_cases": 3,
        "validation_candidates": validation_results,
        "test": score(test, config["keyword_min_score"]),
        "limitation": "Support coverage tests gold labelled passages, not generated-answer entailment. No-key mode abstains on every query, including supported ones. No live embedding/provider quality is claimed.",
    }
    (OUT / "runtime_retrieval_metrics.json").write_text(json.dumps(result, indent=2))
    challenge = classifier_challenge()
    print(
        json.dumps(
            {
                "runtime_retrieval": {
                    key: value for key, value in result["test"].items() if key != "rows"
                },
                "selected_keyword_threshold": config["keyword_min_score"],
                "challenge_macro_f1": challenge["macro_f1"],
                "challenge_keyword_macro_f1": challenge["keyword_macro_f1"],
            },
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    evaluate_runtime()
