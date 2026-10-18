"""Measure parser exact-match fields and keyword ranking on labelled synthetic PDFs."""

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.services.extraction import extract_pdf
from app.services.retrieval import keyword_rank

ROOT = Path(__file__).resolve().parents[1]


def equal(a, b):
    if a is None or b is None:
        return a is None and b is None
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except InvalidOperation:
        return str(a) == str(b)


def evaluate():
    manifest = json.loads((ROOT / "sample_data/manifest.json").read_text())
    stats = defaultdict(lambda: [0, 0])
    errors = []
    texts = []
    filenames = []
    for doc in manifest["documents"]:
        actual, pages = extract_pdf(ROOT / "sample_data" / doc["file"], doc["file"], 30)
        texts.append("\n".join(p["text"] for p in pages))
        filenames.append(doc["file"])
        expected = doc["expected"]
        for key, value in expected.items():
            if key == "line_items":
                stats["line_item_count"][1] += 1
                stats["line_item_count"][0] += len(actual[key]) == len(value)
                for i, item in enumerate(value):
                    for field, wanted in item.items():
                        field_key = "line_item." + field
                        observed = (
                            actual[key][i].get(field) if i < len(actual[key]) else "MISSING_ROW"
                        )
                        stats[field_key][1] += 1
                        stats[field_key][0] += equal(observed, wanted)
                        if not equal(observed, wanted):
                            errors.append(
                                {
                                    "file": doc["file"],
                                    "field": f"line_items[{i}].{field}",
                                    "expected": wanted,
                                    "actual": observed,
                                }
                            )
            else:
                stats[key][1] += 1
                stats[key][0] += equal(actual.get(key), value)
                if not equal(actual.get(key), value):
                    errors.append(
                        {
                            "file": doc["file"],
                            "field": key,
                            "expected": value,
                            "actual": actual.get(key),
                        }
                    )
    extraction = {
        "synthetic_only": True,
        "documents": len(filenames),
        "families": manifest["layout_families"],
        "field_level_exact_accuracy": {
            k: {"correct": v[0], "total": v[1], "accuracy": v[0] / v[1]} for k, v in stats.items()
        },
        "errors": errors,
        "overall_accuracy": sum(v[0] for v in stats.values()) / sum(v[1] for v in stats.values()),
        "limitation": "Fixtures are known parser layouts, not an independent real-world extraction test set.",
    }
    queries = json.loads((ROOT / "evaluation/retrieval_queries.json").read_text())
    rows = []
    recalls = []
    reciprocal = []
    false_hits = 0
    for query in queries:
        scores = keyword_rank(query["query"], texts)
        ranked = [
            filenames[i]
            for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            if scores[i] > 0.035
        ]
        relevant = set(query["relevant_files"])
        if relevant:
            recall = len(set(ranked[:5]) & relevant) / len(relevant)
            mrr = next((1 / (i + 1) for i, name in enumerate(ranked) if name in relevant), 0)
            recalls.append(recall)
            reciprocal.append(mrr)
            rows.append(
                {
                    "query": query["query"],
                    "recall_at_5": recall,
                    "reciprocal_rank": mrr,
                    "top_5": ranked[:5],
                }
            )
        else:
            false_hits += bool(ranked)
            rows.append(
                {"query": query["query"], "unanswerable": True, "returned_evidence": ranked[:5]}
            )
    retrieval = {
        "evaluation_level": "historical document-level synthetic baseline (whole PDF text)",
        "synthetic_only": True,
        "method": "TF-IDF unigram/bigram cosine similarity",
        "documents": len(filenames),
        "queries": len(queries),
        "answerable_queries": len(recalls),
        "recall_at_5": sum(recalls) / len(recalls),
        "mrr": sum(reciprocal) / len(reciprocal),
        "unanswerable_queries_with_hits": false_hits,
        "rows": rows,
        "limitation": "Retrieval relevance does not prove answerability. Unanswerable queries may share words and return passages; no-key mode never generates an answer.",
    }
    (ROOT / "evaluation/extraction_metrics.json").write_text(json.dumps(extraction, indent=2))
    (ROOT / "evaluation/retrieval_metrics.json").write_text(json.dumps(retrieval, indent=2))
    print(
        json.dumps(
            {
                "extraction_accuracy": extraction["overall_accuracy"],
                "extraction_errors": errors,
                "retrieval_recall_at_5": retrieval["recall_at_5"],
                "retrieval_mrr": retrieval["mrr"],
                "unanswerable_queries_with_hits": false_hits,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    evaluate()
    from evaluate_runtime import evaluate_runtime

    evaluate_runtime()
