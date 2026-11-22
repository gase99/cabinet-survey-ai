"""Background export jobs: queued/running/done/failed status and persisted result summary.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("export_jobs") as batch_op:
        batch_op.add_column(sa.Column("result_summary", sa.JSON(), nullable=True))
    # Legacy synchronous rows left in a non-terminal state can never finish.
    op.execute(
        "UPDATE export_jobs SET status = 'failed', "
        "error_message = 'Interrupted before background export jobs were introduced' "
        "WHERE status IN ('pending', 'processing')"
    )


def downgrade() -> None:
    with op.batch_alter_table("export_jobs") as batch_op:
        batch_op.drop_column("result_summary")
