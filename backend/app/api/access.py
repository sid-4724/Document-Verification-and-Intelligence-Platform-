from fastapi import HTTPException
from sqlalchemy import select

from ..models import Case, Document


def owned_case(db, case_id, user, lock=False):
    query = select(Case).where(Case.id == case_id, Case.user_id == user.id)
    if lock:
        query = query.with_for_update()
    case = db.scalar(query)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


def owned_document(db, document_id, user, lock=False):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    owned_case(db, document.case_id, user, lock)
    if lock:
        db.refresh(document)
    return document
