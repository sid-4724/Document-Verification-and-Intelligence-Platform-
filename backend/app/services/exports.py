"""Export a locked current-state snapshot; escape potential spreadsheet formulas."""

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Case, Document
from .presentation import case_summary, document_summary, findings_data
from .review_state import effective_data


def csv_safe(value: object) -> str:
    content = "" if value is None else str(value)
    return (
        "'" + content
        if content.lstrip().startswith(("=", "+", "-", "@"))
        or content.startswith(("\t", "\r", "\n"))
        else content
    )


def structured_export(db: Session, case: Case) -> str:
    findings = findings_data(db, case)
    documents = db.scalars(
        select(Document)
        .where(Document.case_id == case.id)
        .order_by(Document.created_at, Document.id)
    ).all()
    payload = {
        "case": case_summary(db, case),
        "documents": [
            {
                **document_summary(document),
                "data": effective_data(document),
                "original": document.original,
                "latest_raw": document.latest_raw,
            }
            for document in documents
        ],
        "findings": findings,
    }
    return json.dumps(payload, indent=2)


def findings_csv(db: Session, case: Case) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = [
        "kind",
        "severity",
        "review_status",
        "expected",
        "observed",
        "explanation",
        "document_ids",
        "sources",
        "rule",
        "identity",
    ]
    writer.writerow(columns)
    for finding in findings_data(db, case):
        writer.writerow(
            [
                csv_safe(
                    json.dumps(finding[column])
                    if isinstance(finding[column], (list, dict))
                    else finding[column]
                )
                for column in columns
            ]
        )
    return output.getvalue()
