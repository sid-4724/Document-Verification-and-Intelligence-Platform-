"""Pure extraction/review transformations; source limitations survive ordinary field saves."""

import copy
import hashlib
import uuid
from typing import Any

PARSER_VERSION = "labelled-layouts-v3"


def row_id(document_id: str, extraction_revision: int, index: int) -> str:
    """Raw row IDs refer to a particular run/ordinal, never to displayed field values."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"docverify:{document_id}:{extraction_revision}:row:{index}")
    )


def limitation(document_id: str, kind: str, message: str, page: int | None = None) -> dict:
    identity = f"{document_id}:{kind}:{page}:{message}"
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest(),
        "kind": kind,
        "message": message,
        "page": page,
    }


def prepare_raw(data: dict, document_id: str, revision: int, previous: dict | None = None) -> dict:
    result = copy.deepcopy(data)
    result["extraction_revision"] = revision
    result.pop("revision", None)
    for index, item in enumerate(result.get("line_items", [])):
        item["id"] = row_id(document_id, revision, index)
        if item.get("source") and previous:

            def anchor(source):
                return {
                    key: value
                    for key, value in (source or {}).items()
                    if key != "extraction_revision"
                }

            old_matches = [
                row
                for row in previous.get("line_items", [])
                if anchor(row.get("source")) == anchor(item["source"])
            ]
            new_matches = [
                row
                for row in result.get("line_items", [])
                if anchor(row.get("source")) == anchor(item["source"])
            ]
            if len(old_matches) == len(new_matches) == 1:
                item["id"] = old_matches[0]["id"]
        if item.get("source"):
            item["source"]["extraction_revision"] = revision
    for source in result.get("sources", {}).values():
        source["extraction_revision"] = revision
    return result


def field_warnings(data: dict) -> list[str]:
    warnings = []
    for field in ("document_number", "order_reference", "currency", "subtotal", "total"):
        if data.get(field) is None or data.get(field) == "":
            warnings.append(f"Missing or uncertain {field.replace('_', ' ')}")
    if data.get("document_type") == "unknown":
        warnings.append("Document type requires human review")
    if not data.get("line_items"):
        warnings.append("Line items remain unknown")
    for item in data.get("line_items", []):
        if not item.get("description") or any(
            item.get(key) is None for key in ("quantity", "unit", "unit_price", "amount")
        ):
            warnings.append(f"Incomplete line item: {item.get('description') or 'unnamed'}")
        elif (item.get("unit") or "").strip().lower() in {"", "?", "unknown", "n/a", "na", "-"}:
            warnings.append(f"Unknown unit for line item: {item.get('description') or 'unnamed'}")
    return warnings


def effective_data(document: Any) -> dict | None:
    """Corrections remain anchored to their own run; new raw rows are never auto-merged."""
    snapshot = document.corrected or document.latest_raw or document.original
    if snapshot is None:
        return None
    result = copy.deepcopy(snapshot)
    resolved = {item["id"] for item in (document.resolved_limitations or [])}
    unresolved = [
        item for item in (document.source_limitations or []) if item["id"] not in resolved
    ]
    result["source_warnings"] = unresolved
    if document.corrected:
        warnings = field_warnings(result)
    else:
        structural_messages = {item["message"] for item in result.get("source_warnings", [])}
        warnings = [
            message
            for message in result.get("warnings", [])
            if message not in structural_messages
            and "OCR required" not in message
            and "No supported line-item table" not in message
        ]
        warnings.extend(field_warnings(result))
    result["warnings"] = list(dict.fromkeys([*warnings, *[item["message"] for item in unresolved]]))
    result["revision"] = document.revision
    result["extraction_revision"] = (
        document.review_extraction_revision if document.corrected else document.raw_revision
    )
    return result


def update_review_status(document: Any) -> None:
    data = effective_data(document)
    document.status = "needs_review" if data and data["warnings"] else "completed"
