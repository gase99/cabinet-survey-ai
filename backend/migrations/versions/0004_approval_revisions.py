"""Approval metadata and immutable measurement revision history."""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "measurement_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("change_reason", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sa.String(length=36), nullable=False),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name="fk_measurement_revisions_approved_by_users"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], name="fk_measurement_revisions_changed_by_users"),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["measurement_revisions.id"], name="fk_measurement_revisions_prev_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_measurement_revisions_project_id_projects"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", "revision_number", name="uq_measurement_entity_revision"),
    )
    op.create_index(op.f("ix_measurement_revisions_entity_id"), "measurement_revisions", ["entity_id"], unique=False)
    op.create_index(op.f("ix_measurement_revisions_project_id"), "measurement_revisions", ["project_id"], unique=False)

    with op.batch_alter_table("walls") as batch_op:
        batch_op.add_column(sa.Column("approved_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_walls_approved_by_users", "users", ["approved_by"], ["id"])

    with op.batch_alter_table("elements") as batch_op:
        batch_op.add_column(sa.Column("approved_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_elements_approved_by_users", "users", ["approved_by"], ["id"])


def downgrade():
    with op.batch_alter_table("elements") as batch_op:
        batch_op.drop_constraint("fk_elements_approved_by_users", type_="foreignkey")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by")

    with op.batch_alter_table("walls") as batch_op:
        batch_op.drop_constraint("fk_walls_approved_by_users", type_="foreignkey")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by")

    op.drop_index(op.f("ix_measurement_revisions_project_id"), table_name="measurement_revisions")
    op.drop_index(op.f("ix_measurement_revisions_entity_id"), table_name="measurement_revisions")
    op.drop_table("measurement_revisions")
