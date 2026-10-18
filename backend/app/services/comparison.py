"""Select one reference and individual targets; invoice aggregation is unsupported."""


def comparison_scope(documents: list[dict], selection: dict | None = None) -> dict:
    available = {
        document["id"]: document
        for document in documents
        if document.get("data")
        and document.get("status") not in {"pending", "processing", "failed"}
    }
    if selection is not None:
        reference = selection.get("reference_document_id")
        targets = [
            identifier
            for identifier in selection.get("target_document_ids", [])
            if identifier != reference
        ]
        mode = "explicit"
    else:
        orders = [
            document["id"]
            for document in documents
            if document.get("data", {}).get("document_type") == "purchase_order"
        ]
        reference = orders[0] if len(orders) == 1 else None
        targets = (
            [identifier for identifier in available if identifier != reference] if reference else []
        )
        mode = "automatic_unambiguous"
    targets = list(dict.fromkeys(targets))
    ready = reference in available and all(identifier in available for identifier in targets)
    note = "One reference is compared separately with each selected target; targets are never compared with each other."
    if len(documents) >= 2 and reference is None:
        note = "Select one reference document and its targets. Multiple/absent purchase orders cannot be selected automatically."
    elif reference and not ready:
        note = "Selected documents have not all produced readable extractions; comparisons are incomplete."
    invoice_targets = [
        identifier
        for identifier in targets
        if identifier in available
        and available[identifier]["data"].get("document_type") == "invoice"
    ]
    return {
        "mode": mode,
        "reference_document_id": reference,
        "target_document_ids": targets,
        "ready": ready,
        "note": note,
        "multiple_invoices": len(invoice_targets) > 1,
    }
