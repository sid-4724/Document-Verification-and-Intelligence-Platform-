"""Store PDFs privately and retain a database task until a deleted PDF is removed."""

import logging
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..db import SessionLocal
from ..models import Document, FileDeletion
from .extraction import validate_pdf

log = logging.getLogger(__name__)


def save_upload(upload, path, saved_paths, max_file_mb):
    size = 0
    with path.open("xb") as output:
        saved_paths.append(path)
        while True:
            chunk = upload.file.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > max_file_mb * 1024 * 1024:
                raise HTTPException(413, f"Each PDF must be at most {max_file_mb} MB")
            output.write(chunk)


def validate_file(path, max_pages):
    with path.open("rb") as source:
        if not source.read(1024).lstrip().startswith(b"%PDF-"):
            raise HTTPException(400, "File content is not a PDF")
    validate_pdf(path, max_pages)


def rollback_upload(db, saved_paths, check_committed=False, user_id=None, case_id=None):
    try:
        db.rollback()
    except SQLAlchemyError as error:
        log.error("upload_rollback_failed error_type=%s", type(error).__name__)
    if check_committed:
        # A read can race a delayed COMMIT. Preserve every file now; reconcile after a delay.
        try:
            with SessionLocal() as fresh_db:
                retained_names = set(
                    fresh_db.scalars(
                        select(Document.storage_name).where(
                            Document.storage_name.in_([path.name for path in saved_paths])
                        )
                    )
                )
                for path in saved_paths:
                    if path.name not in retained_names:
                        schedule_file_deletion(
                            fresh_db,
                            path.name,
                            user_id,
                            case_id,
                            reason="uncertain_upload",
                            delay_seconds=60,
                        )
                fresh_db.commit()
        except SQLAlchemyError as error:
            log.error("upload_cleanup_deferred error_type=%s", type(error).__name__)
            return
        return
    for path in saved_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            # A failed cleanup must not hide the original upload error.
            log.error(
                "upload_cleanup_failed storage_name=%s error_type=%s",
                path.name,
                type(error).__name__,
            )
            try:
                with SessionLocal() as fresh_db:
                    schedule_file_deletion(
                        fresh_db, path.name, user_id, case_id, reason="upload_rollback"
                    )
                    fresh_db.commit()
            except SQLAlchemyError as cleanup_error:
                log.error(
                    "upload_cleanup_queue_unavailable error_type=%s", type(cleanup_error).__name__
                )


def schedule_file_deletion(
    db, storage_name, user_id=None, case_id=None, *, reason="logical_removal", delay_seconds=0
):
    # No document foreign key: this task must survive deletion of that document.
    if db.get(FileDeletion, storage_name) is None:
        db.add(
            FileDeletion(
                storage_name=storage_name,
                user_id=user_id,
                case_id=case_id,
                reason=reason,
                available_at=time.time() + delay_seconds,
            )
        )


def try_file_deletion(db, task):
    if Path(task.storage_name).name != task.storage_name or not task.storage_name.endswith(".pdf"):
        task.error_type = "UnsafeStorageName"
        task.attempts += 1
        task.available_at = time.time() + 60
        db.commit()
        return False
    if db.scalar(select(Document.id).where(Document.storage_name == task.storage_name).limit(1)):
        # A delayed upload commit may have succeeded after reconciliation was scheduled.
        db.delete(task)
        db.commit()
        return True
    try:
        (settings().storage_dir / task.storage_name).unlink(missing_ok=True)
    except OSError as error:
        task.attempts += 1
        task.available_at = time.time() + 60
        task.error_type = type(error).__name__
        log.warning(
            "file_deletion_pending storage_name=%s error_type=%s",
            task.storage_name,
            task.error_type,
        )
        db.commit()
        return False
    db.delete(task)
    db.commit()
    return True


def finish_file_deletions(storage_names):
    """Try immediately after committing; the worker retries anything that remains."""
    all_removed = True
    with SessionLocal() as db:
        try:
            for name in storage_names:
                task = db.scalar(
                    select(FileDeletion).where(FileDeletion.storage_name == name).with_for_update()
                )
                if task is not None and not try_file_deletion(db, task):
                    all_removed = False
        except SQLAlchemyError as error:
            try:
                db.rollback()
            except SQLAlchemyError as rollback_error:
                log.error(
                    "file_deletion_rollback_failed error_type=%s", type(rollback_error).__name__
                )
            log.error("file_deletion_retry_deferred error_type=%s", type(error).__name__)
            return False
    return all_removed


def retry_one_file_deletion():
    with SessionLocal() as db:
        task = db.scalar(
            select(FileDeletion)
            .where(FileDeletion.available_at <= time.time())
            .order_by(FileDeletion.available_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if task is None:
            return False
        try_file_deletion(db, task)
        return True
