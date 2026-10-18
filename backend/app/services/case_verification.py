"""Persist deterministic results atomically with source changes and preserve review status."""

import copy
import json
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Case, Document, Finding
from .review_state import effective_data
from .verification import verify_documents


def material_signature(finding: dict) -> str:
    """Ignore additive provenance metadata when importing a unique legacy finding status."""
    result = {
        key: copy.deepcopy(finding.get(key))
        for key in (
            "kind",
            "severity",
            "document_ids",
            "explanation",
            "expected",
            "observed",
            "sources",
        )
    }
    for source in result["sources"] or []:
        source.pop("extraction_revision", None)
    return json.dumps(result, sort_keys=True)


def refresh_case(db: Session, case: Case, changed: bool = False) -> None:
    """Caller holds the case lock; results and their revision commit with its mutation."""
    if changed:
        case.revision += 1
    db.flush()
    documents = db.scalars(
        select(Document)
        .where(Document.case_id == case.id)
        .order_by(Document.created_at, Document.id)
    ).all()
    results = verify_documents(
        [
            {
                "id": document.id,
                "filename": document.filename,
                "status": document.status,
                "data": effective_data(document) or {},
            }
            for document in documents
        ],
        Decimal(case.tolerance),
        selection=case.comparison,
    )
    previous = list(db.scalars(select(Finding).where(Finding.case_id == case.id)))
    statuses = {finding.id: finding.review_status for finding in previous}
    inactive = {
        document.id
        for document in documents
        if document.status in {"pending", "processing", "failed"}
    }
    result_ids = {result["id"] for result in results}
    retained_reviews = {}
    for identifier, entry in (case.finding_reviews or {}).items():
        if isinstance(entry, str):
            # Imported v3 caches had no document binding; restore only an exact current result.
            if identifier in result_ids:
                statuses.setdefault(identifier, entry)
            continue
        if inactive.intersection(entry["document_ids"]):
            retained_reviews[identifier] = entry
        elif identifier in result_ids:
            statuses.setdefault(identifier, entry["status"])
    for finding in previous:
        if finding.review_status != "open" and inactive.intersection(finding.document_ids):
            retained_reviews[finding.id] = {
                "status": finding.review_status,
                "document_ids": finding.document_ids,
            }
    # Keep decisions only across a processing pause. Reverted changed facts need new review.
    case.finding_reviews = retained_reviews
    legacy = defaultdict(list)
    for finding in previous:
        if finding.rule == "legacy":
            legacy[
                material_signature(
                    {
                        key: getattr(finding, key)
                        for key in (
                            "kind",
                            "severity",
                            "document_ids",
                            "explanation",
                            "expected",
                            "observed",
                            "sources",
                        )
                    }
                )
            ].append(finding.review_status)
    db.execute(delete(Finding).where(Finding.case_id == case.id))
    for result in results:
        signature = material_signature(result)
        result["review_status"] = statuses.get(
            result["id"], legacy[signature][0] if len(legacy[signature]) == 1 else "open"
        )
        db.add(Finding(case_id=case.id, **result))
    case.verified_revision = case.revision
