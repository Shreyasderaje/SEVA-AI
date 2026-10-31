"""M4: pickup scheduling columns on donation_offers.

When an organization accepts an offer it schedules the pickup: date, time
window, and instructions. The donor's own preferred pickup window already
lives on `donations`; these columns hold the organization's confirmed plan.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d85e01a9b7"
down_revision = "a7c31f9d21b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("donation_offers") as batch:
        batch.add_column(sa.Column("pickup_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("pickup_window_start", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("pickup_window_end", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("pickup_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("donation_offers") as batch:
        batch.drop_column("pickup_instructions")
        batch.drop_column("pickup_window_end")
        batch.drop_column("pickup_window_start")
        batch.drop_column("pickup_date")
