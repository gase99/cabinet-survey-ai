"""Soft-delete tombstone columns and optimistic concurrency versions."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False))

    with op.batch_alter_table("ai_configs") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False))

    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("rooms") as batch_op:
        batch_op.add_column(sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("walls") as batch_op:
        batch_op.add_column(sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("elements") as batch_op:
        batch_op.add_column(sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("elements") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")

    with op.batch_alter_table("walls") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")

    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")

    with op.batch_alter_table("ai_configs") as batch_op:
        batch_op.drop_column("version")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("version")
