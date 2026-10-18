from fastapi import APIRouter, Depends, Response

from ..auth import current_user
from ..db import get_db
from ..services.exports import findings_csv, structured_export
from .access import owned_case

router = APIRouter()


@router.get("/api/cases/{case_id}/export.json")
def export_json(case_id: str, user=Depends(current_user), db=Depends(get_db)):
    case = owned_case(db, case_id, user, lock=True)
    content = structured_export(db, case)
    db.commit()
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="docverify-extraction.json"'},
    )


@router.get("/api/cases/{case_id}/findings.csv")
def export_csv(case_id: str, user=Depends(current_user), db=Depends(get_db)):
    case = owned_case(db, case_id, user, lock=True)
    content = findings_csv(db, case)
    db.commit()
    return Response(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="docverify-findings.csv"'},
    )
