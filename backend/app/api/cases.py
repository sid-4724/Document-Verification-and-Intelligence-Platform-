from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth import current_user
from ..db import get_db
from ..models import (
    Case,
    Document,
    FileDeletion,
    Finding,
)
from ..schemas import (
    CaseInput,
    ComparisonInput,
)
from ..services.case_verification import refresh_case
from ..services.file_storage import finish_file_deletions, schedule_file_deletion
from ..services.presentation import case_summary, findings_data
from .access import owned_case

router = APIRouter()


@router.get("/api/cases")
def list_cases(user=Depends(current_user), db=Depends(get_db)):
    return [
        case_summary(db, c)
        for c in db.scalars(
            select(Case).where(Case.user_id == user.id).order_by(Case.created_at.desc())
        )
    ]


@router.post("/api/cases", status_code=201)
def create_case(body: CaseInput, user=Depends(current_user), db=Depends(get_db)):
    case = Case(user_id=user.id, name=body.name, tolerance=str(body.tolerance), verified_revision=0)
    db.add(case)
    db.commit()
    return case_summary(db, case)


@router.get("/api/cases/{case_id}")
def get_case(case_id: str, user=Depends(current_user), db=Depends(get_db)):
    return case_summary(db, owned_case(db, case_id, user))


@router.patch("/api/cases/{case_id}")
def update_case(case_id: str, body: CaseInput, user=Depends(current_user), db=Depends(get_db)):
    case = owned_case(db, case_id, user, lock=True)
    case.name, case.tolerance = body.name, str(body.tolerance)
    refresh_case(db, case, changed=True)
    db.commit()
    return case_summary(db, case)


@router.delete("/api/cases/{case_id}")
def delete_case(case_id: str, user=Depends(current_user), db=Depends(get_db)):
    case = owned_case(db, case_id, user, lock=True)
    names = list(db.scalars(select(Document.storage_name).where(Document.case_id == case.id)))
    for name in names:
        schedule_file_deletion(db, name, user.id, case.id)
    db.delete(case)
    db.commit()
    removed = finish_file_deletions(names)
    return {"ok": True, "storage_cleanup_pending": not removed}


@router.get("/api/storage-cleanup")
def cleanup_status(user=Depends(current_user), db=Depends(get_db)):
    tasks = db.scalars(select(FileDeletion).where(FileDeletion.user_id == user.id)).all()
    return {
        "pending_count": len(tasks),
        "tasks": [
            {
                "case_id": task.case_id,
                "attempts": task.attempts,
                "error_type": task.error_type,
                "reason": task.reason,
            }
            for task in tasks
        ],
    }


@router.get("/api/cases/{case_id}/findings")
def findings(case_id: str, user=Depends(current_user), db=Depends(get_db)):
    result = findings_data(db, owned_case(db, case_id, user, lock=True))
    db.commit()
    return result


class ReviewFinding(BaseModel):
    review_status: str = Field(pattern="^(open|acknowledged|resolved)$")


@router.patch("/api/cases/{case_id}/findings/{finding_id}")
def review_finding(
    case_id: str,
    finding_id: str,
    body: ReviewFinding,
    user=Depends(current_user),
    db=Depends(get_db),
):
    owned_case(db, case_id, user, lock=True)
    finding = db.scalar(select(Finding).where(Finding.id == finding_id, Finding.case_id == case_id))
    if not finding:
        raise HTTPException(404, "Finding not found")
    finding.review_status = body.review_status
    db.commit()
    return {"ok": True}


@router.put("/api/cases/{case_id}/comparison")
def configure_comparison(
    case_id: str, body: ComparisonInput, user=Depends(current_user), db=Depends(get_db)
):
    case = owned_case(db, case_id, user, lock=True)
    if case.revision != body.revision:
        raise HTTPException(409, "Case changed; reload the comparison selection")
    ids = set(db.scalars(select(Document.id).where(Document.case_id == case.id)))
    requested = {
        identifier
        for identifier in [body.reference_document_id, *body.target_document_ids]
        if identifier
    }
    if not requested <= ids or body.reference_document_id in body.target_document_ids:
        raise HTTPException(422, "Choose distinct reference/targets belonging to this case")
    case.comparison = {
        "reference_document_id": body.reference_document_id,
        "target_document_ids": list(dict.fromkeys(body.target_document_ids)),
    }
    refresh_case(db, case, changed=True)
    db.commit()
    return case_summary(db, case)
