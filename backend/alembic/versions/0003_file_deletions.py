"""Keep physical file deletion retryable after committing document removal."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cases", sa.Column("finding_reviews", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_table(
        "file_deletions",
        sa.Column("storage_name", sa.String(80), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.Float(), nullable=False),
        sa.Column("error_type", sa.String(80), nullable=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("reason", sa.String(40), nullable=False, server_default="logical_removal"),
    )
    op.create_index("ix_file_deletions_available_at", "file_deletions", ["available_at"])
    op.create_index("ix_file_deletions_user_id", "file_deletions", ["user_id"])
    op.create_index("ix_file_deletions_case_id", "file_deletions", ["case_id"])


def downgrade():
    # Downgrading would discard pending privacy cleanup work.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM file_deletions")):
        raise RuntimeError("Finish pending file deletions before downgrading")
    op.drop_table("file_deletions")
    op.drop_column("cases", "finding_reviews")
