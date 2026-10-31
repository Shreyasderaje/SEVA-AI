"""M4: monotonic sequence columns for stable ordering.

`created_at` has second-level precision on some platforms (Windows: ~15.6 ms),
so rapid history/notification rows tie and `ORDER BY created_at` becomes
non-deterministic. `seq` is a per-scope monotonic counter (per donation for
status history, per user for notifications) used as the tie-breaker.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e2a94c6f10"
down_revision = "e91b7f3c5d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("donation_status_history") as batch:
        batch.add_column(sa.Column("seq", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE donation_status_history SET seq = (SELECT COUNT(*) FROM "
        "donation_status_history h2 WHERE h2.donation_id = donation_status_history.donation_id "
        "AND h2.rowid <= donation_status_history.rowid)"
    )
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("seq", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE notifications SET seq = (SELECT COUNT(*) FROM notifications n2 "
        "WHERE n2.user_id = notifications.user_id AND n2.rowid <= notifications.rowid)"
    )


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("seq")
    with op.batch_alter_table("donation_status_history") as batch:
        batch.drop_column("seq")
