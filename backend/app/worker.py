"""Single-process DB worker with atomic claims, lease fencing, and bounded retries."""

import importlib.metadata
import logging
import time

from sqlalchemy import delete, or_, select, update

from .config import settings
from .db import SessionLocal
from .models import Case, Chunk, Document, Job, Page, ProcessingRun, uid
from .services.case_verification import refresh_case
from .services.classification import classify
from .services.extraction import PDFError, extract_pdf
from .services.file_storage import retry_one_file_deletion
from .services.retrieval import make_chunks
from .services.review_state import PARSER_VERSION, prepare_raw, update_review_status

log = logging.getLogger(__name__)


def claim_job(db, now=None):
    now = now or time.time()
    cfg = settings()
    stale = (Job.status == "processing") & (Job.claimed_at < now - cfg.job_lease_seconds)
    # Recover exhausted stale leases rather than leaving them stuck forever.
    exhausted_ids = db.scalars(
        select(Job.id).where(stale, Job.attempts >= cfg.job_max_attempts)
    ).all()
    for identifier in exhausted_ids:
        snapshot = db.get(Job, identifier)
        document = db.get(Document, snapshot.document_id) if snapshot else None
        if not document:
            continue
        # Recovery uses the same case-before-job lock order as source writers.
        case = db.scalar(
            select(Case).where(Case.id == document.case_id).with_for_update(skip_locked=True)
        )
        if case is None:
            continue
        job = db.scalar(
            select(Job)
            .where(Job.id == identifier, stale, Job.attempts >= cfg.job_max_attempts)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            continue
        job.status, job.error, job.lease_token = (
            "failed",
            "Processing lease expired after maximum retries",
            None,
        )
        document.status, document.error = "failed", job.error
        document.revision += 1
        db.add(
            ProcessingRun(
                document_id=document.id,
                revision=None,
                status="failed",
                error=job.error,
                extraction={},
                pages=[],
                metadata_json={
                    "origin": "expired_lease_recovery",
                    "parser_version": PARSER_VERSION,
                    "job_attempt": job.attempts,
                },
            )
        )
        refresh_case(db, case, changed=True)
    db.flush()
    eligible = or_((Job.status == "pending") & (Job.available_at <= now), stale)
    candidate = db.scalar(
        select(Job.id)
        .where(eligible, Job.attempts < cfg.job_max_attempts)
        .order_by(Job.available_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if not candidate:
        db.commit()
        return None
    token = uid()
    result = db.execute(
        update(Job)
        .where(Job.id == candidate, eligible, Job.attempts < cfg.job_max_attempts)
        .values(status="processing", claimed_at=now, lease_token=token, attempts=Job.attempts + 1)
        .returning(Job.id, Job.document_id)
    )
    row = result.first()
    if not row:
        db.rollback()
        return None
    doc = db.get(Document, row.document_id)
    doc.status, doc.error = "processing", None
    db.commit()
    return {
        "id": row.id,
        "document_id": row.document_id,
        "token": token,
        "storage_name": doc.storage_name,
    }


def extract_document(claim):
    cfg = settings()
    extraction, pages = extract_pdf(
        cfg.storage_dir / claim["storage_name"], claim["document_id"], cfg.max_pages
    )
    classification = classify("\n".join(p["text"] for p in pages))
    if extraction["document_type"] == "unknown" and classification["model_prediction"]:
        extraction["document_type"] = classification["model_prediction"]
    if classification["disagreement"]:
        extraction["warnings"].append(
            "Keyword and ML type predictions disagree; confirm document type"
        )
    chunks = make_chunks(pages)
    return extraction, pages, classification, chunks


def save_processing_result(claim, extraction, pages, classification, chunks):
    with SessionLocal() as db:
        # Lock the case before the job/document, matching API writers' lock order.
        doc = db.get(Document, claim["document_id"])
        if not doc:
            return False
        case = db.scalar(select(Case).where(Case.id == doc.case_id).with_for_update())
        job = db.scalar(select(Job).where(Job.id == claim["id"]).with_for_update())
        if not case or not job or job.lease_token != claim["token"] or job.status != "processing":
            return False
        extraction_revision = doc.raw_revision + 1
        extraction = prepare_raw(extraction, doc.id, extraction_revision, previous=doc.latest_raw)
        db.add(
            ProcessingRun(
                document_id=doc.id,
                revision=extraction_revision,
                extraction=extraction,
                pages=pages,
                metadata_json={
                    "origin": "worker",
                    "parser_version": PARSER_VERSION,
                    "pdfplumber_version": importlib.metadata.version("pdfplumber"),
                    "classification": classification,
                    "classification_features": "heading-weighted-tfidf-v1",
                    "sklearn_version": importlib.metadata.version("scikit-learn"),
                    "job_attempt": job.attempts,
                },
            )
        )
        for model in (Page, Chunk):
            db.execute(delete(model).where(model.document_id == doc.id))
        for page in pages:
            db.add(Page(document_id=doc.id, extraction_revision=extraction_revision, **page))
        for chunk in chunks:
            db.add(Chunk(document_id=doc.id, extraction_revision=extraction_revision, **chunk))
        if doc.original is None:
            doc.original = extraction
        doc.latest_raw, doc.classification = extraction, classification
        doc.raw_revision = extraction_revision
        doc.revision += 1
        by_id = {warning["id"]: warning for warning in (doc.source_limitations or [])}
        by_id.update({warning["id"]: warning for warning in extraction.get("source_warnings", [])})
        doc.source_limitations = list(by_id.values())
        update_review_status(doc)
        doc.error = None
        job.status, job.error, job.lease_token = "completed", None, None
        refresh_case(db, case, changed=True)
        db.commit()
    return True


def record_processing_failure(claim, error):
    cfg = settings()
    terminal = isinstance(error, PDFError)
    message = (
        str(error)
        if terminal
        else f"Processing failed ({type(error).__name__}); retry scheduled if attempts remain"
    )
    with SessionLocal() as db:
        document = db.get(Document, claim["document_id"])
        if not document:
            return
        case = db.scalar(select(Case).where(Case.id == document.case_id).with_for_update())
        job = db.scalar(select(Job).where(Job.id == claim["id"]).with_for_update())
        if not job or job.lease_token != claim["token"]:
            return
        failed = terminal or job.attempts >= cfg.job_max_attempts
        job.status = "failed" if failed else "pending"
        job.error, job.lease_token = message, None
        job.available_at = time.time() + min(2**job.attempts, 30)
        doc = db.get(Document, job.document_id)
        if doc:
            doc.status, doc.error = ("failed" if failed else "pending"), message
            doc.revision += 1
            db.add(
                ProcessingRun(
                    document_id=doc.id,
                    revision=None,
                    status="failed",
                    error=message,
                    extraction={},
                    pages=[],
                    metadata_json={
                        "origin": "worker_failure",
                        "parser_version": PARSER_VERSION,
                        "job_attempt": job.attempts,
                    },
                )
            )
            refresh_case(db, case, changed=True)
        db.commit()
    # Exception messages and tracebacks can contain extracted names or SQL parameters.
    log.error(
        "document_processing_failed document_id=%s error_type=%s",
        claim["document_id"],
        type(error).__name__,
    )


def process_claim(claim):
    try:
        extraction, pages, classification, chunks = extract_document(claim)
        saved = save_processing_result(claim, extraction, pages, classification, chunks)
        if saved:
            log.info(
                "document_processed document_id=%s pages=%s",
                claim["document_id"],
                len(pages),
            )
    except Exception as error:
        record_processing_failure(claim, error)


def run_once():
    deleted_file = retry_one_file_deletion()
    with SessionLocal() as db:
        claim = claim_job(db)
    if claim:
        process_claim(claim)
    return bool(claim) or deleted_file


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("worker_started")
    while True:
        try:
            if not run_once():
                time.sleep(1)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log.error("worker_loop_failed error_type=%s", type(exc).__name__)
            time.sleep(2)


if __name__ == "__main__":
    main()
