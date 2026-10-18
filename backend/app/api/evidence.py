from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..auth import current_user
from ..db import get_db
from ..models import (
    Chunk,
    Correction,
    Document,
)
from ..schemas import (
    SearchInput,
)
from ..services.presentation import findings_data
from ..services.retrieval import answer_question, retrieve
from ..services.review_state import effective_data
from ..services.verification import verify_documents
from .access import owned_case

router = APIRouter()


@router.post("/api/cases/{case_id}/search")
def search(case_id: str, body: SearchInput, user=Depends(current_user), db=Depends(get_db)):
    case = owned_case(db, case_id, user, lock=True)
    current_findings = findings_data(db, case)
    documents = db.scalars(select(Document).where(Document.case_id == case.id)).all()
    scoped_findings = (
        current_findings
        if body.scope == "reviewed"
        else verify_documents(
            [
                {
                    "id": document.id,
                    "filename": document.filename,
                    "status": document.status,
                    "data": document.latest_raw or document.original or {},
                }
                for document in documents
            ],
            Decimal(case.tolerance),
            selection=case.comparison,
        )
    )
    rows = db.execute(
        select(Chunk, Document.filename).join(Document).where(Document.case_id == case.id)
    ).all()
    chunks = [
        {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "filename": filename,
            "page": chunk.page,
            "text": chunk.text,
            "embedding": chunk.embedding,
            "embedding_meta": chunk.embedding_meta,
            "extraction_revision": chunk.extraction_revision,
            "source_type": "original_passage",
        }
        for chunk, filename in rows
    ]
    evidence, status = retrieve(body.query, chunks, mode=body.mode)
    for item in evidence:
        item.pop("embedding", None)
        item.pop("embedding_meta", None)
    records = []
    if body.scope == "reviewed":
        for document in documents:
            data = effective_data(document)
            if data is None:
                continue
            audit = db.scalar(
                select(Correction)
                .where(Correction.document_id == document.id)
                .order_by(Correction.created_at.desc())
                .limit(1)
            )
            records.append(
                {
                    "id": f"reviewed:{document.id}:{document.revision}",
                    "source_type": "reviewed_record",
                    "document_id": document.id,
                    "filename": document.filename,
                    "values_origin": "human_review"
                    if document.corrected
                    else "latest_raw_unreviewed",
                    "values": data,
                    "provenance": {
                        "document_revision": document.revision,
                        "extraction_revision": data["extraction_revision"],
                        "latest_raw_revision": document.raw_revision,
                        "correction_id": audit.id if audit else None,
                        "reviewer_id": audit.user_id if audit else None,
                        "corrected_at": audit.created_at if audit else None,
                    },
                    "notice": "Human corrections are reviewed records, not quotations from the original PDF.",
                }
            )
    revision = case.revision
    db.commit()
    answer, ids, generation_status = answer_question(
        body.query, evidence, scoped_findings, scope=body.scope, reviewed_records=records
    )
    return {
        "evidence": evidence,
        "reviewed_records": records,
        "scope": body.scope,
        "revision": revision,
        "answer": answer,
        "cited_source_ids": ids,
        "retrieval_status": status,
        "generation_status": generation_status,
        "verification": scoped_findings,
        "correction_notice": "Original passages preserve PDF text. Reviewed records separately identify current values, human corrections, and their extraction/audit revisions.",
    }
