import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..models import (
    Case,
    Correction,
    Document,
    Job,
    Page,
    ProcessingRun,
    uid,
)
from ..schemas import (
    Extraction,
    LimitationResolution,
)
from ..services.case_verification import refresh_case
from ..services.corrections import resolve_source_limitation, save_correction
from ..services.extraction import PDFError
from ..services.file_storage import (
    finish_file_deletions,
    rollback_upload,
    save_upload,
    schedule_file_deletion,
    validate_file,
)
from ..services.presentation import document_summary
from ..services.review_state import effective_data
from .access import owned_case, owned_document

router = APIRouter()


def enqueue_file(db, case, path, filename, document_id):
    doc = Document(
        id=document_id,
        case_id=case.id,
        filename=Path(filename).name[:255] or "document.pdf",
        storage_name=path.name,
    )
    db.add(doc)
    db.flush()
    db.add(Job(document_id=doc.id))
    return doc


@router.post("/api/cases/{case_id}/documents", status_code=201)
def upload(
    case_id: str,
    files: list[UploadFile] = File(...),
    user=Depends(current_user),
    db=Depends(get_db),
):
    case = owned_case(db, case_id, user, lock=True)
    if not 1 <= len(files) <= 5:
        raise HTTPException(400, "Upload between one and five PDFs at a time")
    cfg = settings()
    owner_id, case_identifier = user.id, case.id
    saved, docs = [], []
    commit_started = False
    try:
        cfg.storage_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            doc_id = uid()
            path = cfg.storage_dir / f"{doc_id}.pdf"
            save_upload(file, path, saved, cfg.max_file_mb)
            validate_file(path, cfg.max_pages)
            docs.append(enqueue_file(db, case, path, file.filename or "document.pdf", doc_id))
        refresh_case(db, case, changed=True)
        commit_started = True
        db.commit()
        return [document_summary(d) for d in docs]
    except Exception as exc:
        rollback_upload(
            db, saved, check_committed=commit_started, user_id=owner_id, case_id=case_identifier
        )
        if isinstance(exc, PDFError):
            raise HTTPException(400, str(exc))
        if isinstance(exc, OSError):
            raise HTTPException(503, "Document storage unavailable; please retry shortly") from None
        if commit_started:
            raise HTTPException(
                503, "Upload result uncertain; refresh the case before uploading again"
            ) from None
        raise


@router.get("/api/documents/{document_id}")
def get_document(document_id: str, user=Depends(current_user), db=Depends(get_db)):
    document = owned_document(db, document_id, user)
    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.number)
    ).all()
    audits = db.scalars(
        select(Correction)
        .where(Correction.document_id == document.id)
        .order_by(Correction.created_at.desc())
    ).all()
    runs = db.scalars(
        select(ProcessingRun)
        .where(ProcessingRun.document_id == document.id)
        .order_by(ProcessingRun.revision.desc())
    ).all()
    return {
        **document_summary(document),
        "original": document.original,
        "latest_raw": document.latest_raw,
        "data": effective_data(document),
        "classification": document.classification,
        "pages": [
            {
                "number": page.number,
                "text": page.text,
                "extraction_revision": page.extraction_revision,
            }
            for page in pages
        ],
        "corrections": [
            {
                key: getattr(audit, key)
                for key in (
                    "id",
                    "user_id",
                    "created_at",
                    "before",
                    "after",
                    "extraction_revision",
                    "document_revision",
                    "action",
                    "resolution",
                )
            }
            for audit in audits
        ],
        "processing_runs": [
            {
                "id": run.id,
                "status": run.status,
                "error": run.error,
                "revision": run.revision,
                "created_at": run.created_at,
                "metadata": run.metadata_json,
                "extraction": run.extraction,
                "pages": run.pages,
            }
            for run in runs
        ],
        "resolved_limitations": document.resolved_limitations,
        "effective_basis": "review anchored to earlier run"
        if document.corrected and document.review_extraction_revision != document.raw_revision
        else "current reviewed data"
        if document.corrected
        else "latest raw extraction",
    }


@router.get("/api/documents/{document_id}/file")
def source_file(document_id: str, user=Depends(current_user), db=Depends(get_db)):
    doc = owned_document(db, document_id, user)
    path = settings().storage_dir / doc.storage_name
    if not path.exists():
        raise HTTPException(404, "Stored PDF is missing")
    return FileResponse(
        path, media_type="application/pdf", filename=doc.filename, content_disposition_type="inline"
    )


@router.delete("/api/documents/{document_id}")
def remove_document(document_id: str, user=Depends(current_user), db=Depends(get_db)):
    doc = owned_document(db, document_id, user, lock=True)
    case = db.get(Case, doc.case_id)
    storage_name = doc.storage_name
    schedule_file_deletion(db, storage_name, user.id, case.id)
    db.delete(doc)
    if case.comparison is not None:
        case.comparison = {
            "reference_document_id": None
            if case.comparison.get("reference_document_id") == doc.id
            else case.comparison.get("reference_document_id"),
            "target_document_ids": [
                identifier
                for identifier in case.comparison.get("target_document_ids", [])
                if identifier != doc.id
            ],
        }
    db.flush()
    refresh_case(db, case, changed=True)
    db.commit()
    removed = finish_file_deletions([storage_name])
    return {"ok": True, "storage_cleanup_pending": not removed}


@router.post("/api/documents/{document_id}/retry")
def retry_document(document_id: str, user=Depends(current_user), db=Depends(get_db)):
    doc = owned_document(db, document_id, user, lock=True)
    job = db.scalar(select(Job).where(Job.document_id == doc.id).with_for_update())
    if doc.status not in {"failed", "completed", "needs_review"}:
        raise HTTPException(409, "Document is already queued or processing")
    job.status, job.attempts, job.error, job.available_at, job.lease_token = (
        "pending",
        0,
        None,
        time.time(),
        None,
    )
    doc.status, doc.error = "pending", None
    refresh_case(db, db.get(Case, doc.case_id), changed=True)
    db.commit()
    return document_summary(doc)


@router.put("/api/documents/{document_id}/correction")
def correct_document(
    document_id: str, body: Extraction, user=Depends(current_user), db=Depends(get_db)
):
    document = owned_document(db, document_id, user, lock=True)
    save_correction(db, document, user, body)
    return {
        "ok": True,
        "revision": db.get(Case, document.case_id).revision,
        "document_revision": document.revision,
        "data": effective_data(document),
    }


@router.post("/api/documents/{document_id}/source-limitations/{warning_id}/resolve")
def resolve_limitation(
    document_id: str,
    warning_id: str,
    body: LimitationResolution,
    user=Depends(current_user),
    db=Depends(get_db),
):
    document = owned_document(db, document_id, user, lock=True)
    resolve_source_limitation(db, document, user, warning_id, body)
    return {"ok": True, "document_revision": document.revision}
