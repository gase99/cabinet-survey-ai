import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())

def now_utc():
    return datetime.now(UTC)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user, admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    # telegram linking
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    customers = relationship("Customer", back_populates="owner")
    projects = relationship("Project", back_populates="owner")

class Customer(Base):
    __tablename__ = "customers"
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    owner = relationship("User", back_populates="customers")
    projects = relationship("Project", back_populates="customer")

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")  # draft, in_progress, completed, archived, deleted
    site_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    owner = relationship("User", back_populates="projects")
    customer = relationship("Customer", back_populates="projects")
    rooms = relationship("Room", back_populates="project", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="project")

class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    room_type: Mapped[str] = mapped_column(String(50), nullable=False, default="rectangular")  # rectangular, L, U, irregular
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project = relationship("Project", back_populates="rooms")
    walls = relationship("Wall", back_populates="room", cascade="all, delete-orphan")

class Wall(Base):
    __tablename__ = "walls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    length_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    height_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=2700)
    # coordinates in room frame
    start_x_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_y_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_x_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_y_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_status: Mapped[str] = mapped_column(String(20), default="needs_review")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", name="fk_walls_approved_by_users"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(ForeignKey("observations.id", name="fk_walls_source_observation_id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    room = relationship("Room", back_populates="walls")
    elements = relationship("Element", back_populates="wall", cascade="all, delete-orphan")

class Element(Base):
    __tablename__ = "elements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    wall_id: Mapped[str] = mapped_column(ForeignKey("walls.id"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # window, door, column, beam, gas_pipe, water_pipe, drain, electrical, switch, socket, ventilation, recess, protrusion, custom
    offset_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sill_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="needs_review")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", name="fk_elements_approved_by_users"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(ForeignKey("observations.id", name="fk_elements_source_observation_id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    wall = relationship("Wall", back_populates="elements")

class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", name="fk_observations_owner_id_users"), index=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # manual, sketch_ai, voice_ai, text_ai, import
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    source_image_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_region: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # bbox polygon or text span
    prompt_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="needs_review", nullable=False)
    linked_entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    linked_entity_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    clarification: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # local or s3
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class DrawingVersion(Base):
    __tablename__ = "drawing_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_drawing_project_version"),)

class ExportJob(Base):
    __tablename__ = "export_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf, png
    layout: Mapped[str] = mapped_column(String(10), nullable=False, default="A4")  # A3, A4
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")  # queued, running, done, failed
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # excluded_items / flagged_items decided at request time (never re-derived later).
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    project = relationship("Project", back_populates="audit_events")

class PairingCode(Base):
    __tablename__ = "pairing_codes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class TelegramDelivery(Base):
    __tablename__ = "telegram_deliveries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    export_job_id: Mapped[str | None] = mapped_column(ForeignKey("export_jobs.id"), nullable=True)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, sent, failed, cancelled
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", name="fk_idempotency_records_owner_id_users"), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    __table_args__ = (UniqueConstraint("owner_id", "scope", "idempotency_key", name="uq_idempotency_owner_scope_key"),)

class SyncOperation(Base):
    __tablename__ = "sync_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)  # create, update, delete
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    base_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, applied, conflict, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class AIConfig(Base):
    __tablename__ = "ai_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    usage_limit_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    refresh_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

class AuthThrottle(Base):
    __tablename__ = "auth_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


class MeasurementRevision(Base):
    __tablename__ = "measurement_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", name="fk_measurement_revisions_project_id_projects"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_revision_id: Mapped[str | None] = mapped_column(ForeignKey("measurement_revisions.id", name="fk_measurement_revisions_prev_id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by: Mapped[str] = mapped_column(ForeignKey("users.id", name="fk_measurement_revisions_changed_by_users"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", name="fk_measurement_revisions_approved_by_users"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "revision_number", name="uq_measurement_entity_revision"),)


@event.listens_for(MeasurementRevision, "before_update")
def _forbid_revision_update(mapper, connection, target):
    raise ValueError("MeasurementRevision records are immutable; append a new revision instead")


@event.listens_for(MeasurementRevision, "before_delete")
def _forbid_revision_delete(mapper, connection, target):
    raise ValueError("MeasurementRevision records are immutable and cannot be deleted")


@event.listens_for(AuditEvent, "before_update")
def _forbid_audit_update(mapper, connection, target):
    raise ValueError("AuditEvent records are append-only; updates are forbidden")


@event.listens_for(AuditEvent, "before_delete")
def _forbid_audit_delete(mapper, connection, target):
    raise ValueError("AuditEvent records are append-only; deletes are forbidden")


@event.listens_for(AuditEvent.__table__, "after_create")
def _install_audit_append_only_triggers(target, connection, **kwargs):
    dialect = connection.dialect.name
    if dialect == "sqlite":
        connection.execute(text(
            "CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update "
            "BEFORE UPDATE ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; UPDATE is forbidden'); END"
        ))
        connection.execute(text(
            "CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete "
            "BEFORE DELETE ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only; DELETE is forbidden'); END"
        ))
    elif dialect == "postgresql":
        connection.execute(text(
            "CREATE OR REPLACE FUNCTION forbid_audit_events_mutation() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_events is append-only; % is forbidden', TG_OP; END; "
            "$$ LANGUAGE plpgsql"
        ))
        connection.execute(text("DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events"))
        connection.execute(text(
            "CREATE TRIGGER trg_audit_events_no_update BEFORE UPDATE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION forbid_audit_events_mutation()"
        ))
        connection.execute(text("DROP TRIGGER IF EXISTS trg_audit_events_no_delete ON audit_events"))
        connection.execute(text(
            "CREATE TRIGGER trg_audit_events_no_delete BEFORE DELETE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION forbid_audit_events_mutation()"
        ))


