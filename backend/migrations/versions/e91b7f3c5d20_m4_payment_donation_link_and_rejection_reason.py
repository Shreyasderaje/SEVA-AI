"""M4: payment_records additions — donation link and admin rejection reason."""

import sqlalchemy as sa
from alembic import op

revision = "e91b7f3c5d20"
down_revision = "c4d85e01a9b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payment_records") as batch:
        batch.add_column(sa.Column("donation_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payment_records") as batch:
        batch.drop_column("rejection_reason")
        batch.drop_column("donation_id")
