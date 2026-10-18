"""Deterministic Decimal checks. Unknown values always produce review, never mismatch."""

import hashlib
import json
from decimal import Decimal

from .comparison import comparison_scope
from .matching import match_candidates, normalize


def dec(value: str | Decimal | int | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def unit(value: str | None) -> str:
    raw = normalize(value)
    if raw in {"", "unknown", "n a", "na", "none"}:
        return ""
    return {
        "metres": "m",
        "meters": "m",
        "metre": "m",
        "meter": "m",
        "pieces": "pcs",
        "piece": "pcs",
        "pc": "pcs",
        "hours": "hr",
        "hour": "hr",
        "kilograms": "kg",
    }.get(raw, raw)


def add_finding(
    findings,
    context,
    kind,
    severity,
    docs,
    explanation,
    expected=None,
    observed=None,
    sources=None,
    rule=None,
):
    sources = [s for s in (sources or []) if s]
    # Findings without specific fields still link to a real first page.
    if not sources:
        sources = [
            {"document_id": d["id"], "page": 1, "snippet": "Document overview", "bbox": None}
            for d in docs
        ]
    result = {
        "kind": kind,
        "severity": severity,
        "document_ids": [d["id"] for d in docs],
        "explanation": explanation,
        "expected": None if expected is None else str(expected),
        "observed": None if observed is None else str(observed),
        "sources": sources,
    }
    result["rule"] = rule or kind
    result["identity"] = {
        **context,
        "rule": result["rule"],
        "kind": kind,
        "documents": result["document_ids"],
    }
    material = json.loads(json.dumps(result))
    for source in material["sources"]:
        source.pop("extraction_revision", None)
    result["id"] = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    result["review_status"] = "open"
    findings.append(result)


def check_document_fields(doc, findings):
    data = doc["data"]
    context = {"document_id": doc["id"]}
    if not data or doc.get("status") in {"pending", "processing", "failed"}:
        return
    for field in ("document_number", "order_reference"):
        context = {"document_id": doc["id"], "field": field}
        if not data.get(field):
            add_finding(
                findings,
                context,
                "missing_identifier",
                "review",
                [doc],
                f"{field.replace('_', ' ').capitalize()} is missing or unreadable; confirm it before comparing.",
                sources=[data.get("sources", {}).get(field)],
            )
    context = {"document_id": doc["id"]}
    if data.get("warnings"):
        add_finding(
            findings,
            context,
            "extraction_uncertainty",
            "review",
            [doc],
            "; ".join(data["warnings"]),
        )


def check_line_totals(doc, tolerance, findings):
    data = doc["data"]
    amounts = []
    for index, item in enumerate(data.get("line_items", [])):
        context = {
            "document_id": doc["id"],
            "row_id": item.get("id") or f"unpersisted-row-{index}",
        }
        qty, price, amount = (dec(item.get(k)) for k in ("quantity", "unit_price", "amount"))
        amounts.append(amount)
        if (
            qty is not None
            and price is not None
            and amount is not None
            and abs(qty * price - amount) > tolerance
        ):
            add_finding(
                findings,
                context,
                "arithmetic_error",
                "error",
                [doc],
                f"{item['description']}: quantity × unit price does not equal the line amount.",
                qty * price,
                amount,
                [item.get("source")],
                rule="line_multiplication",
            )
    return amounts


def check_document_totals(doc, amounts, tolerance, findings):
    data = doc["data"]
    context = {"document_id": doc["id"]}
    subtotal, tax, total = (dec(data.get(k)) for k in ("subtotal", "tax", "total"))
    if (
        amounts
        and not any(
            warning.get("kind")
            in {"invalid_row", "row_limit", "incomplete_table", "ocr_page", "legacy_provenance"}
            for warning in data.get("source_warnings", [])
        )
        and all(a is not None for a in amounts)
        and subtotal is not None
        and abs(sum(amounts) - subtotal) > tolerance
    ):
        add_finding(
            findings,
            context,
            "arithmetic_error",
            "error",
            [doc],
            "The sum of line amounts differs from the stated subtotal.",
            sum(amounts),
            subtotal,
            [data.get("sources", {}).get("subtotal")],
            rule="subtotal_line_sum",
        )
    if (
        subtotal is not None
        and tax is not None
        and total is not None
        and abs(subtotal + tax - total) > tolerance
    ):
        add_finding(
            findings,
            context,
            "arithmetic_error",
            "error",
            [doc],
            "Subtotal + stated tax differs from the final total.",
            subtotal + tax,
            total,
            [data.get("sources", {}).get("total")],
            rule="subtotal_plus_tax",
        )
    rate = dec(data.get("tax_rate"))
    if (
        subtotal is not None
        and tax is not None
        and rate is not None
        and abs(subtotal * rate / 100 - tax) > tolerance
    ):
        add_finding(
            findings,
            context,
            "arithmetic_error",
            "error",
            [doc],
            "Tax differs from subtotal × explicit tax rate.",
            subtotal * rate / 100,
            tax,
            [data.get("sources", {}).get("tax")],
            rule="explicit_tax_rate",
        )


def check_document(doc, tolerance, findings):
    if not doc["data"] or doc.get("status") in {"pending", "processing", "failed"}:
        return
    check_document_fields(doc, findings)
    amounts = check_line_totals(doc, tolerance, findings)
    check_document_totals(doc, amounts, tolerance, findings)


def check_matched_row(first, second, i, matches, reverse_counts, tolerance, findings):
    reference_data, target_data = first["data"], second["data"]
    docs = [first, second]
    right = target_data.get("line_items", [])
    item = reference_data["line_items"][i]
    currency_ok = reference_data.get("currency") and reference_data.get(
        "currency"
    ) == target_data.get("currency")
    candidates = matches[i]["indices"]
    context = {
        "reference_document_id": first["id"],
        "target_document_id": second["id"],
        "reference_row_id": item.get("id") or f"unpersisted-row-{i}",
    }
    if matches[i]["conflict"]:
        add_finding(
            findings,
            context,
            "identifier_conflict",
            "review",
            docs,
            f"{item['description']}: nonempty SKUs conflict. Description similarity cannot confirm item identity.",
            item.get("sku"),
            ", ".join(right[j].get("sku") or "Unknown" for j in candidates),
            [item.get("source"), *[right[j].get("source") for j in candidates]],
            rule="identifier_precedence",
        )
        return
    if len(candidates) > 1 or (candidates and reverse_counts[candidates[0]] > 1):
        add_finding(
            findings,
            context,
            "ambiguous_match",
            "review",
            docs,
            f"Multiple possible matches for {item['description']}; human review is required.",
            sources=[item.get("source"), *[right[j].get("source") for j in candidates]],
        )
        return
    if not candidates:
        incomplete = bool(reference_data.get("warnings") or target_data.get("warnings"))
        add_finding(
            findings,
            context,
            "possible_missing_item" if incomplete else "missing_item",
            "review" if incomplete else "warning",
            docs,
            f"{item['description']} has no match in {second['filename']}."
            + (" Extraction is incomplete; confirm in the source." if incomplete else ""),
            item["description"],
            None,
            [item.get("source")],
        )
        return
    other = right[candidates[0]]
    context["target_row_id"] = other.get("id") or f"unpersisted-row-{candidates[0]}"
    if matches[i]["method"] == "fuzzy_description":
        add_finding(
            findings,
            context,
            "fuzzy_match",
            "review",
            docs,
            f"{item['description']}: only fuzzy description evidence is available; confirm the candidate before treating its differences as established.",
            sources=[item.get("source"), other.get("source")],
            rule="fuzzy_candidate_review",
        )
        return
    sources = [item.get("source"), other.get("source")]
    units_ok = bool(
        item.get("unit")
        and other.get("unit")
        and unit(item["unit"])
        and unit(item["unit"]) == unit(other["unit"])
    )
    if not units_ok:
        add_finding(
            findings,
            context,
            "unit_incompatible",
            "review",
            docs,
            f"{item['description']}: units differ or are unknown; quantity and unit-price comparisons were skipped.",
            item.get("unit"),
            other.get("unit"),
            sources,
        )
    for field, kind, allowed in (
        ("quantity", "quantity_difference", units_ok),
        ("unit_price", "unit_price_difference", units_ok and currency_ok),
    ):
        context["field"] = field
        expected, observed = dec(item.get(field)), dec(other.get(field))
        if allowed and (expected is None or observed is None):
            add_finding(
                findings,
                context,
                "extraction_uncertainty",
                "review",
                docs,
                f"{item['description']}: {field.replace('_', ' ')} is unknown; no mismatch confirmed.",
                sources=sources,
            )
        elif allowed and abs(expected - observed) > (
            Decimal(0) if field == "quantity" else tolerance
        ):
            add_finding(
                findings,
                context,
                kind,
                "warning",
                docs,
                f"{item['description']}: {field.replace('_', ' ')} differs between documents.",
                expected,
                observed,
                sources,
            )


def check_extra_rows(first, second, reserved, findings):
    reference_data, target_data = first["data"], second["data"]
    docs = [first, second]
    right = target_data.get("line_items", [])
    for j, other in enumerate(right):
        if j not in reserved:
            context = {
                "reference_document_id": first["id"],
                "target_document_id": second["id"],
                "target_row_id": other.get("id") or f"unpersisted-row-{j}",
            }
            incomplete = bool(reference_data.get("warnings") or target_data.get("warnings"))
            add_finding(
                findings,
                context,
                "possible_extra_item" if incomplete else "extra_item",
                "review" if incomplete else "warning",
                docs,
                f"{other['description']} appears only in {second['filename']}.",
                None,
                other["description"],
                [other.get("source")],
            )


def compare_document_pair(first, second, tolerance, findings):
    context = {"reference_document_id": first["id"], "target_document_id": second["id"]}
    reference_data, target_data = first["data"], second["data"]
    docs = [first, second]
    refs = [reference_data.get("order_reference"), target_data.get("order_reference")]
    if all(refs) and normalize(refs[0]) != normalize(refs[1]):
        add_finding(
            findings,
            context,
            "order_reference_difference",
            "review",
            docs,
            "Order references differ; these documents may belong to different orders.",
            *refs,
            [
                reference_data.get("sources", {}).get("order_reference"),
                target_data.get("sources", {}).get("order_reference"),
            ],
        )
        return
    currency_ok = reference_data.get("currency") and reference_data.get(
        "currency"
    ) == target_data.get("currency")
    if not currency_ok:
        add_finding(
            findings,
            context,
            "currency_incompatible",
            "review",
            docs,
            "Currency is different or unknown; monetary comparisons require a shared currency. No conversion was performed.",
            reference_data.get("currency"),
            target_data.get("currency"),
            [
                reference_data.get("sources", {}).get("currency"),
                target_data.get("sources", {}).get("currency"),
            ],
        )
    left, right = reference_data.get("line_items", []), target_data.get("line_items", [])
    if not left or not right:
        add_finding(
            findings,
            context,
            "extraction_uncertainty",
            "review",
            docs,
            "A line-item table is unavailable; missing-item comparisons cannot be confirmed.",
        )
        return
    matches = match_candidates(left, right)
    candidate_map = {index: match["indices"] for index, match in matches.items()}
    reserved = {j for candidates in candidate_map.values() for j in candidates}
    reverse_counts = {j: sum(j in c for c in candidate_map.values()) for j in reserved}
    for index in range(len(left)):
        check_matched_row(first, second, index, matches, reverse_counts, tolerance, findings)
    check_extra_rows(first, second, reserved, findings)
    context = {"reference_document_id": first["id"], "target_document_id": second["id"]}
    sa, sb = dec(reference_data.get("subtotal")), dec(target_data.get("subtotal"))
    if currency_ok and sa is not None and sb is not None and abs(sa - sb) > tolerance:
        add_finding(
            findings,
            context,
            "subtotal_difference",
            "warning",
            docs,
            f"Subtotal difference: {target_data['currency']} {sb - sa:,.2f} (observed − expected).",
            sa,
            sb,
            [
                reference_data.get("sources", {}).get("subtotal"),
                target_data.get("sources", {}).get("subtotal"),
            ],
        )


def check_comparison_scope(documents, selection, findings):
    scope = comparison_scope(documents, selection)
    readable = {
        doc["id"]: doc
        for doc in documents
        if doc.get("data") and doc.get("status") not in {"pending", "processing", "failed"}
    }
    context = {"scope": "case"}
    if len(documents) >= 2 and not scope["ready"]:
        add_finding(
            findings,
            context,
            "comparison_not_ready",
            "review",
            documents,
            scope["note"],
            rule="comparison_selection",
        )
    if scope["multiple_invoices"]:
        add_finding(
            findings,
            context,
            "multiple_invoices",
            "review",
            [
                readable[i]
                for i in [scope["reference_document_id"], *scope["target_document_ids"]]
                if i in readable
            ],
            "Multiple invoices may represent partial fulfilment. Only individual reference-to-target comparisons are shown; invoice aggregation is unsupported.",
            rule="partial_fulfilment_scope",
        )
    pairs = [
        (readable[scope["reference_document_id"]], readable[target_id])
        for target_id in scope["target_document_ids"]
        if scope["reference_document_id"] in readable and target_id in readable
    ]
    return pairs


def verify_documents(
    documents: list[dict], tolerance=Decimal("0.01"), selection: dict | None = None
) -> list[dict]:
    findings = []
    for document in documents:
        check_document(document, tolerance, findings)
    pairs = check_comparison_scope(documents, selection, findings)
    for reference, target in pairs:
        compare_document_pair(reference, target, tolerance, findings)
    return findings
