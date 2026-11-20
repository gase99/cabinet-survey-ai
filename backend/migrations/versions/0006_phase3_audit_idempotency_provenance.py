"""Phase 3 append-only audit values/triggers, idempotency records, AI provenance, and Telegram tombstones.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _install_audit_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update "
            "BEFORE UPDATE ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; UPDATE is forbidden'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete "
            "BEFORE DELETE ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; DELETE is forbidden'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE OR REPLACE FUNCTION forbid_audit_events_mutation() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_events is append-only; % is forbidden', TG_OP; END; "
            "$$ LANGUAGE plpgsql"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events")
        op.execute(
            "CREATE TRIGGER trg_audit_events_no_update BEFORE UPDATE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION forbid_audit_events_mutation()"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete ON audit_events")
        op.execute(
            "CREATE TRIGGER trg_audit_events_no_delete BEFORE DELETE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION forbid_audit_events_mutation()"
        )


def _drop_audit_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS forbid_audit_events_mutation()")


def upgrade() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.add_column(sa.Column("old_values", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("new_values", sa.JSON(), nullable=True))

    _install_audit_triggers()

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_idempotency_records_owner_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "scope",
            "idempotency_key",
            name="uq_idempotency_owner_scope_key",
        ),
    )
    op.create_index(
        op.f("ix_idempotency_records_owner_id"),
        "idempotency_records",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_idempotency_records_expires_at"),
        "idempotency_records",
        ["expires_at"],
        unique=False,
    )

    with op.batch_alter_table("observations") as batch:
        batch.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.add_column(sa.Column("owner_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("source_image_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("prompt_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("provider", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("model_name", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("linked_entity_type", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("linked_entity_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_observations_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
        )
        batch.create_index(
            op.f("ix_observations_owner_id"),
            ["owner_id"],
            unique=False,
        )
        batch.create_index(
            op.f("ix_observations_linked_entity_id"),
            ["linked_entity_id"],
            unique=False,
        )

    with op.batch_alter_table("walls") as batch:
        batch.add_column(sa.Column("source_observation_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_walls_source_observation_id",
            "observations",
            ["source_observation_id"],
            ["id"],
        )

    with op.batch_alter_table("elements") as batch:
        batch.add_column(sa.Column("source_observation_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_elements_source_observation_id",
            "observations",
            ["source_observation_id"],
            ["id"],
        )

    with op.batch_alter_table("pairing_codes") as batch:
        batch.add_column(sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch.add_column(
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("telegram_deliveries") as batch:
        batch.add_column(
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch.add_column(
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("telegram_deliveries") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("is_deleted")
        batch.drop_column("version")

    with op.batch_alter_table("pairing_codes") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("is_deleted")
        batch.drop_column("version")
        batch.drop_column("telegram_chat_id")

    with op.batch_alter_table("elements") as batch:
        batch.drop_constraint("fk_elements_source_observation_id", type_="foreignkey")
        batch.drop_column("source_observation_id")

    with op.batch_alter_table("walls") as batch:
        batch.drop_constraint("fk_walls_source_observation_id", type_="foreignkey")
        batch.drop_column("source_observation_id")

    with op.batch_alter_table("observations") as batch:
        batch.drop_index(op.f("ix_observations_linked_entity_id"))
        batch.drop_index(op.f("ix_observations_owner_id"))
        batch.drop_constraint("fk_observations_owner_id_users", type_="foreignkey")
        batch.drop_column("linked_entity_id")
        batch.drop_column("linked_entity_type")
        batch.drop_column("model_name")
        batch.drop_column("provider")
        batch.drop_column("prompt_id")
        batch.drop_column("source_image_sha256")
        batch.drop_column("owner_id")
        batch.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    op.drop_index(op.f("ix_idempotency_records_expires_at"), table_name="idempotency_records")
    op.drop_index(op.f("ix_idempotency_records_owner_id"), table_name="idempotency_records")
    op.drop_table("idempotency_records")

    _drop_audit_triggers()
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_column("new_values")
        batch.drop_column("old_values")
