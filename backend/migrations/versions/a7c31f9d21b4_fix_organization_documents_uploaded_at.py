"""Fix organization_documents.uploaded_at server default.

Migration 001 rendered the Python string "CURRENT_TIMESTAMP" as a quoted SQL
literal, so SQLite stored the TEXT 'CURRENT_TIMESTAMP' instead of evaluating
the keyword — reading any row of this table raised
``ValueError: Invalid isoformat string``. Discovered by the M3 organization
tests; no M1/M2 functionality ever read this table.

Applies a batch (SQLite-safe) default fix and repairs any rows that already
hold the literal string.
"""

import sqlalchemy as sa
from alembic import op

revision = "a7c31f9d21b4"
down_revision = "3cb71d79fa42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organization_documents") as batch:
        batch.alter_column(
            "uploaded_at",
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
    op.execute(
        "UPDATE organization_documents SET uploaded_at = CURRENT_TIMESTAMP "
        "WHERE uploaded_at = 'CURRENT_TIMESTAMP'"
    )


def downgrade() -> None:
    with op.batch_alter_table("organization_documents") as batch:
        batch.alter_column(
            "uploaded_at",
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=sa.text("'CURRENT_TIMESTAMP'"),
        )
