"""Transaction orchestration for optimistic field review and explicit source review."""

import copy
import time

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Case, Correction, Document, User, uid
from ..schemas import Extraction, LimitationResolution
from .case_verification import refresh_case
from .review_state import effective_data, field_warnings, update_review_status


def check_revision(db: Session, document: Document, expected: int | None) -> None:
    """A conditional write protects SQLite as well as PostgreSQL against stale tabs."""
    if expected is None:
        raise HTTPException(428, "Reload the document to obtain its current review revision")
    updated = db.execute(
        update(Document)
        .where(Document.id == document.id, Document.revision == expected)
        .values(revision=expected + 1)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not updated:
        raise HTTPException(
            409,
            {
                "message": "This document changed in another tab or processing run. Your draft has not been saved. Reload the latest values before reviewing again.",
                "current_revision": document.revision,
            },
        )
    document.revision = expected + 1


def save_correction(db: Session, document: Document, user: User, payload: Extraction) -> None:
    """Keep existing row/provenance identity; assign new IDs once to user-added rows."""
    before = effective_data(document)
    if before is None or document.status in {"pending", "processing", "failed"}:
        raise HTTPException(409, "Wait for successful processing before reviewing")
    check_revision(db, document, payload.revision)
    if payload.extraction_revision != before["extraction_revision"]:
        raise HTTPException(409, "The extraction basis changed; reload the current document")
    after = payload.model_dump(mode="json")
    current_rows = {item["id"]: item for item in before["line_items"]}
    seen = set()
    for item in after["line_items"]:
        item_id = item.get("id")
        if item_id is None:
            if item.get("source"):
                raise HTTPException(422, "A new row cannot invent source provenance")
            item["id"] = uid()
        else:
            if item_id not in current_rows or item_id in seen:
                raise HTTPException(
                    422, "Row IDs must be distinct and belong to the current document review"
                )
            seen.add(item_id)
            expected_source = current_rows[item_id].get("source")
            if item.get("source") != expected_source:
                raise HTTPException(
                    422, "Line-item source is immutable; preserve the row's extraction provenance"
                )
    after["sources"] = copy.deepcopy(before.get("sources", {}))
    after["source_warnings"] = copy.deepcopy(before.get("source_warnings", []))
    after["warnings"] = field_warnings(after)
    after["confidence_label"] = (
        "Human reviewed; original extraction and processing runs retained separately"
    )
    after.pop("revision", None)
    document.corrected = after
    document.review_extraction_revision = before["extraction_revision"]
    update_review_status(document)
    db.add(
        Correction(
            document_id=document.id,
            user_id=user.id,
            before=before,
            after=effective_data(document),
            extraction_revision=before["extraction_revision"],
            document_revision=document.revision,
            action="field_review",
        )
    )
    refresh_case(db, db.get(Case, document.case_id), changed=True)
    db.commit()


def resolve_source_limitation(
    db: Session, document: Document, user: User, warning_id: str, payload: LimitationResolution
) -> None:
    before = effective_data(document)
    if before is None or document.status in {"pending", "processing", "failed"}:
        raise HTTPException(
            409, "Wait for successful processing before reviewing a source limitation"
        )
    warning = next((item for item in before["source_warnings"] if item["id"] == warning_id), None)
    if warning is None:
        raise HTTPException(404, "Unresolved source limitation not found")
    check_revision(db, document, payload.revision)
    resolution = {
        "id": warning_id,
        "reason": payload.reason.strip(),
        "user_id": user.id,
        "created_at": time.time(),
        "document_revision": document.revision,
        "extraction_revision": before["extraction_revision"],
    }
    document.resolved_limitations = [*(document.resolved_limitations or []), resolution]
    update_review_status(document)
    db.add(
        Correction(
            document_id=document.id,
            user_id=user.id,
            before=before,
            after=effective_data(document),
            action="source_resolution",
            resolution=resolution,
            extraction_revision=before["extraction_revision"],
            document_revision=document.revision,
        )
    )
    refresh_case(db, db.get(Case, document.case_id), changed=True)
    db.commit()
