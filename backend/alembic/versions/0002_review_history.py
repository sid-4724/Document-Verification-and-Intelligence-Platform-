"""Add review/run history without deleting application records.

Legacy original means first RETAINED snapshot: earlier overwritten runs are unrecoverable.
"""

import copy
import hashlib
import re
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def stable_row(document_id, revision_number, index):
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"docverify:{document_id}:{revision_number}:row:{index}")
    )


def upgrade():
    op.add_column("cases", sa.Column("comparison", sa.JSON, nullable=True))
    for column in [
        sa.Column("latest_raw", sa.JSON),
        sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("review_extraction_revision", sa.Integer),
        sa.Column("source_limitations", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("resolved_limitations", sa.JSON, nullable=False, server_default="[]"),
    ]:
        op.add_column("documents", column)
    op.add_column("pages", sa.Column("extraction_revision", sa.Integer))
    op.add_column("chunks", sa.Column("extraction_revision", sa.Integer))
    op.add_column("chunks", sa.Column("embedding_meta", sa.JSON))
    for column in [
        sa.Column("extraction_revision", sa.Integer),
        sa.Column("document_revision", sa.Integer),
        sa.Column("action", sa.String(32), nullable=False, server_default="field_review"),
        sa.Column("resolution", sa.JSON),
    ]:
        op.add_column("corrections", column)
    op.add_column(
        "findings", sa.Column("rule", sa.String(64), nullable=False, server_default="legacy")
    )
    op.add_column("findings", sa.Column("identity", sa.JSON, nullable=False, server_default="{}"))
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer, nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("extraction", sa.JSON, nullable=False),
        sa.Column("pages", sa.JSON, nullable=False),
        sa.Column("metadata_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.Float, nullable=True),
    )
    op.create_index("ix_processing_runs_document_id", "processing_runs", ["document_id"])
    op.create_index(
        "ix_processing_run_revision", "processing_runs", ["document_id", "revision"], unique=True
    )
    connection = op.get_bind()
    documents = sa.table(
        "documents",
        sa.column("id", sa.String),
        sa.column("original", sa.JSON),
        sa.column("corrected", sa.JSON),
        sa.column("classification", sa.JSON),
        sa.column("latest_raw", sa.JSON),
        sa.column("revision", sa.Integer),
        sa.column("raw_revision", sa.Integer),
        sa.column("source_limitations", sa.JSON),
        sa.column("status", sa.String),
    )
    pages = sa.table(
        "pages",
        sa.column("document_id", sa.String),
        sa.column("number", sa.Integer),
        sa.column("text", sa.Text),
        sa.column("extraction_revision", sa.Integer),
    )
    runs = sa.table(
        "processing_runs",
        sa.column("id", sa.String),
        sa.column("document_id", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("extraction", sa.JSON),
        sa.column("pages", sa.JSON),
        sa.column("metadata_json", sa.JSON),
        sa.column("created_at", sa.Float),
    )
    for document in connection.execute(sa.select(documents)).mappings().all():
        if not document["original"]:
            continue
        doc_id = document["id"]
        raw = copy.deepcopy(document["original"])
        raw["extraction_revision"] = 1
        for index, item in enumerate(raw.get("line_items", [])):
            item["id"] = stable_row(doc_id, 1, index)
            if item.get("source"):
                item["source"]["extraction_revision"] = 1
        for source in raw.get("sources", {}).values():
            source["extraction_revision"] = 1
        stored_pages = [
            {"number": page["number"], "text": page["text"]}
            for page in connection.execute(
                sa.select(pages).where(pages.c.document_id == doc_id).order_by(pages.c.number)
            ).mappings()
        ]
        limitations = []
        for page in stored_pages:
            if len(re.sub(r"\W", "", page["text"])) < 20:
                message = f"Page {page['number']} has no usable text; OCR required or explicit manual source review"
                kind = "ocr_page"
                limitation_id = hashlib.sha256(
                    f"{doc_id}:{kind}:{page['number']}:{message}".encode()
                ).hexdigest()
                limitations.append(
                    {"id": limitation_id, "kind": kind, "message": message, "page": page["number"]}
                )
        for warning in raw.get("warnings", []):
            if "No supported line-item table" in warning or ("OCR" in warning and not limitations):
                kind = "incomplete_table" if "table" in warning else "ocr_page"
                limitations.append(
                    {
                        "id": hashlib.sha256(
                            f"{doc_id}:{kind}:None:{warning}".encode()
                        ).hexdigest(),
                        "kind": kind,
                        "message": warning,
                        "page": None,
                    }
                )
        raw["source_warnings"] = copy.deepcopy(limitations)
        corrected = copy.deepcopy(document["corrected"])
        if corrected:
            # We cannot prove which historical processing run supplied a legacy review.
            corrected["extraction_revision"] = None
            for index, item in enumerate(corrected.get("line_items", [])):
                item["id"] = str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"docverify:{doc_id}:legacy-review:row:{index}")
                )
                if item.get("source"):
                    item["source"]["extraction_revision"] = None
            for source in corrected.get("sources", {}).values():
                source["extraction_revision"] = None
            message = "Legacy review predates retained processing history; its extraction revision cannot be recovered"
            kind = "legacy_provenance"
            limitations.append(
                {
                    "id": hashlib.sha256(f"{doc_id}:{kind}:None:{message}".encode()).hexdigest(),
                    "kind": kind,
                    "message": message,
                    "page": None,
                }
            )
        values = {
            "original": raw,
            "latest_raw": raw,
            "corrected": corrected,
            "revision": 1,
            "raw_revision": 1,
            "source_limitations": limitations,
        }
        if limitations and document["status"] in {"completed", "needs_review"}:
            values["status"] = "needs_review"
        connection.execute(documents.update().where(documents.c.id == doc_id).values(**values))
        connection.execute(
            pages.update().where(pages.c.document_id == doc_id).values(extraction_revision=1)
        )
        connection.execute(
            sa.text("UPDATE chunks SET extraction_revision = 1 WHERE document_id = :document_id"),
            {"document_id": doc_id},
        )
        connection.execute(
            runs.insert().values(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"docverify:legacy-run:{doc_id}")),
                document_id=doc_id,
                revision=1,
                extraction=raw,
                pages=stored_pages,
                metadata_json={
                    "origin": "legacy_retained_snapshot",
                    "parser_version": "unknown",
                    "classification": document["classification"],
                    "history_limit": "Earlier overwritten extractions and processing timestamps were not stored and cannot be recovered",
                },
                created_at=None,
            )
        )
    # Old results must be refreshed through the new rules, without removing review data now.
    connection.execute(sa.text("UPDATE cases SET revision = revision + 1"))


def downgrade():
    raise RuntimeError(
        "This additive history migration has no destructive downgrade; restore an explicit backup if rollback is needed"
    )
