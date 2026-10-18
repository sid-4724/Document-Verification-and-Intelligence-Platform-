import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..models import (
    Case,
    uid,
)
from .documents import enqueue_file

router = APIRouter()


@router.post("/api/demo", status_code=201)
def load_demo(user=Depends(current_user), db=Depends(get_db)):
    if not settings().demo_mode:
        raise HTTPException(404, "Demo loading is disabled")
    root = Path(__file__).resolve().parents[3] / "sample_data"
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(503, "Run scripts/generate_samples.py before loading demo data")
    created, saved = [], []
    try:
        for sample in json.loads(manifest_path.read_text())["cases"]:
            case = Case(user_id=user.id, name=sample["name"], tolerance="0.01", verified_revision=0)
            db.add(case)
            db.flush()
            for filename in sample["files"]:
                doc_id = uid()
                path = settings().storage_dir / f"{doc_id}.pdf"
                path.parent.mkdir(parents=True, exist_ok=True)
                saved.append(path)
                shutil.copyfile(root / filename, path)
                enqueue_file(db, case, path, filename, doc_id)
            created.append(case.id)
        db.commit()
    except Exception:
        db.rollback()
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    return {"case_ids": created}
