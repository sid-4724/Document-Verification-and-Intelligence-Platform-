"""API snapshots of effective values, comparison selection, and honest case readiness."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Case, Document, FileDeletion, Finding
from .case_verification import refresh_case
from .comparison import comparison_scope
from .review_state import effective_data


def document_summary(document: Document) -> dict:
    data = effective_data(document) or {}
    return {
        "id": document.id,
        "filename": document.filename,
        "status": document.status,
        "error": document.error,
        "created_at": document.created_at,
        "document_type": data.get("document_type", "unknown"),
        "revision": document.revision,
        "raw_revision": document.raw_revision,
        "review_extraction_revision": document.review_extraction_revision,
        "warning_count": len(data.get("warnings", [])),
    }


def case_summary(db: Session, case: Case) -> dict:
    documents = db.scalars(
        select(Document)
        .where(Document.case_id == case.id)
        .order_by(Document.created_at, Document.id)
    ).all()
    findings = db.scalars(select(Finding).where(Finding.case_id == case.id)).all()
    scope = comparison_scope(
        [
            {"id": document.id, "status": document.status, "data": effective_data(document) or {}}
            for document in documents
        ],
        case.comparison,
    )
    status_counts = {
        status: sum(document.status == status for document in documents)
        for status in ("pending", "processing", "completed", "needs_review", "failed")
    }
    readiness = {
        "status_counts": status_counts,
        "readable_count": sum(document.original is not None for document in documents),
        "unresolved_count": sum(
            bool((effective_data(document) or {}).get("warnings")) for document in documents
        ),
        "all_documents_checked": bool(documents)
        and all(
            document.status == "completed" and not (effective_data(document) or {}).get("warnings")
            for document in documents
        ),
        "comparison_ready": scope["ready"],
    }
    return {
        "id": case.id,
        "cleanup_pending_count": len(
            db.scalars(
                select(FileDeletion).where(
                    FileDeletion.user_id == case.user_id, FileDeletion.case_id == case.id
                )
            ).all()
        ),
        "name": case.name,
        "tolerance": case.tolerance,
        "created_at": case.created_at,
        "revision": case.revision,
        "verified_revision": case.verified_revision,
        "stale": case.revision != case.verified_revision,
        "document_count": len(documents),
        "processing_count": status_counts["pending"] + status_counts["processing"],
        "finding_count": len(findings),
        "documents": [document_summary(document) for document in documents],
        "comparison": scope,
        "readiness": readiness,
    }


def findings_data(db: Session, case: Case) -> list[dict]:
    if case.revision != case.verified_revision:
        refresh_case(db, case)
        db.flush()
    return [
        {
            key: getattr(finding, key)
            for key in (
                "id",
                "kind",
                "rule",
                "identity",
                "severity",
                "explanation",
                "document_ids",
                "expected",
                "observed",
                "sources",
                "review_status",
            )
        }
        for finding in db.scalars(
            select(Finding).where(Finding.case_id == case.id).order_by(Finding.kind, Finding.id)
        )
    ]
