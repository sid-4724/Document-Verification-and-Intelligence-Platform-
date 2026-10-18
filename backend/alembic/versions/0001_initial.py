"""Initial DocVerify tables.

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("csrf", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("tolerance", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("verified_revision", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_cases_user_id", "cases", ["user_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("original", sa.JSON),
        sa.Column("corrected", sa.JSON),
        sa.Column("classification", sa.JSON),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    for table in ("pages", "chunks"):
        columns = [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "document_id",
                sa.String(36),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("text", sa.Text, nullable=False),
        ]
        columns += (
            [sa.Column("number", sa.Integer, nullable=False)]
            if table == "pages"
            else [sa.Column("page", sa.Integer, nullable=False), sa.Column("embedding", sa.JSON)]
        )
        op.create_table(table, *columns)
        op.create_index(f"ix_{table}_document_id", table, ["document_id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.Float, nullable=False),
        sa.Column("claimed_at", sa.Float),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_jobs_queue", "jobs", ["status", "available_at"])
    op.create_table(
        "corrections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("before", sa.JSON, nullable=False),
        sa.Column("after", sa.JSON, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_corrections_document_id", "corrections", ["document_id"])
    op.create_table(
        "findings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("document_ids", sa.JSON, nullable=False),
        sa.Column("expected", sa.Text),
        sa.Column("observed", sa.Text),
        sa.Column("sources", sa.JSON, nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
    )
    op.create_index("ix_findings_case_id", "findings", ["case_id"])


def downgrade():
    for table in (
        "findings",
        "corrections",
        "jobs",
        "chunks",
        "pages",
        "documents",
        "cases",
        "sessions",
        "users",
    ):
        op.drop_table(table)
