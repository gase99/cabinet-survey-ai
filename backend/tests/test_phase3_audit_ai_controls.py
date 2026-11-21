"""Pre-Phase-3 Gap A (zero hard deletes across all DELETE routes) and Phase 3 Audit & AI controls."""
import io
import uuid
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import event, text
from sqlalchemy.exc import DatabaseError

from app.ai import speech
from app.core.config import settings
from app.main import app
from app.models.db_models import (
    AuditEvent,
    Customer,
    Element,
    ExportJob,
    IdempotencyRecord,
    PairingCode,
    Project,
    Room,
    TelegramDelivery,
    User,
    Wall,
    now_utc,
)

WORKER_SECRET = "phase3-test-worker-secret"


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), "white").save(buf, format="PNG")
    return buf.getvalue()


def _wav_bytes() -> bytes:
    return b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 16


def _register_and_login(client, email: str | None = None) -> tuple[dict, str]:
    addr = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": addr, "password": "TestPass123!", "display_name": "Surveyor"},
    )
    assert r.status_code == 201
    tok = client.post(
        "/api/v1/auth/login", json={"email": addr, "password": "TestPass123!"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return headers, me["id"]


def _create_approved_closed_room(client, headers) -> tuple[str, str, list[str], str]:
    proj = client.post(
        "/api/v1/projects", headers=headers, json={"title": "Phase 3 Kitchen"}
    ).json()
    pid = proj["id"]
    room = client.post(
        f"/api/v1/projects/{pid}/rooms",
        headers=headers,
        json={"label": "Kitchen", "room_type": "rectangular"},
    ).json()
    rid = room["id"]
    specs = [
        ("Wall A", 4000, 2700, 0, 0, 4000, 0),
        ("Wall B", 3000, 2700, 4000, 0, 4000, 3000),
        ("Wall C", 4000, 2700, 4000, 3000, 0, 3000),
        ("Wall D", 3000, 2700, 0, 3000, 0, 0),
    ]
    wall_ids: list[str] = []
    for label, l_mm, h_mm, sx, sy, ex, ey in specs:
        w = client.post(
            f"/api/v1/rooms/{rid}/walls",
            headers=headers,
            json={
                "label": label,
                "length_mm": l_mm,
                "height_mm": h_mm,
                "start_x_mm": sx,
                "start_y_mm": sy,
                "end_x_mm": ex,
                "end_y_mm": ey,
            },
        )
        assert w.status_code == 201
        wid = w.json()["id"]
        wall_ids.append(wid)
        assert client.post(f"/api/v1/walls/{wid}/approve", headers=headers).status_code == 200

    elem = client.post(
        f"/api/v1/walls/{wall_ids[0]}/elements",
        headers=headers,
        json={
            "label": "Window 1",
            "kind": "window",
            "offset_mm": 600,
            "width_mm": 1200,
            "height_mm": 1100,
            "sill_mm": 900,
        },
    )
    assert elem.status_code == 201
    eid = elem.json()["id"]
    assert client.post(f"/api/v1/elements/{eid}/approve", headers=headers).status_code == 200
    return pid, rid, wall_ids, eid


def test_gap_a_every_delete_endpoint_soft_deletes_excludes_from_lists_and_emits_tombstones(
    client, auth_headers, db_session, monkeypatch
):
    """Pre-Phase-3 Gap A: call EVERY DELETE endpoint in FastAPI, verify zero SQL DELETEs,
    is_deleted=True in DB, exclusion from GET lists, and tombstones in /sync/pull."""
    monkeypatch.setattr(settings, "telegram_worker_secret", WORKER_SECRET)

    delete_routes = {
        path
        for path, ops in app.openapi()["paths"].items()
        if "delete" in ops
    }
    assert delete_routes == {
        "/api/v1/customers/{customer_id}",
        "/api/v1/projects/{project_id}",
        "/api/v1/rooms/{room_id}",
        "/api/v1/walls/{wall_id}",
        "/api/v1/elements/{element_id}",
        "/api/v1/telegram/unlink",
    }

    customer = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={"name": "Reza", "phone": "09120000000"},
    )
    assert customer.status_code == 201
    cid = customer.json()["id"]

    pid, rid, wall_ids, eid = _create_approved_closed_room(client, auth_headers)
    wid = wall_ids[0]

    export_resp = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert export_resp.status_code == 201
    export_id = export_resp.json()["id"]

    pair_resp = client.post("/api/v1/telegram/pairing-code", headers=auth_headers)
    assert pair_resp.status_code == 200
    code = pair_resp.json()["code"]
    verify_resp = client.post(
        "/api/v1/telegram/verify-pairing",
        headers={"X-Webhook-Secret": WORKER_SECRET},
        json={"code": code, "telegram_chat_id": "998877", "telegram_username": "workshop_bot"},
    )
    assert verify_resp.status_code == 200
    send_resp = client.post(
        "/api/v1/telegram/send",
        headers=auth_headers,
        json={"export_job_id": export_id},
    )
    assert send_resp.status_code == 200
    delivery_id = send_resp.json()["delivery_id"]

    executed_sql: list[str] = []
    bind = db_session.get_bind()

    def _capture_sql(conn, cursor, statement, parameters, context, executemany):
        executed_sql.append(statement.strip().upper())

    event.listen(bind, "before_cursor_execute", _capture_sql)
    try:
        r_elem = client.delete(f"/api/v1/elements/{eid}", headers=auth_headers)
        assert r_elem.status_code == 200
        assert client.get(f"/api/v1/walls/{wid}/elements", headers=auth_headers).json() == []

        r_wall = client.delete(f"/api/v1/walls/{wid}", headers=auth_headers)
        assert r_wall.status_code == 200
        listed_wall_ids = [
            w["id"]
            for w in client.get(f"/api/v1/rooms/{rid}/walls", headers=auth_headers).json()
        ]
        assert wid not in listed_wall_ids

        r_room = client.delete(f"/api/v1/rooms/{rid}", headers=auth_headers)
        assert r_room.status_code == 200
        assert client.get(f"/api/v1/projects/{pid}/rooms", headers=auth_headers).json() == []

        r_proj = client.delete(f"/api/v1/projects/{pid}", headers=auth_headers)
        assert r_proj.status_code == 200
        assert client.get("/api/v1/projects", headers=auth_headers).json() == []

        r_cust = client.delete(f"/api/v1/customers/{cid}", headers=auth_headers)
        assert r_cust.status_code == 200
        assert client.get("/api/v1/customers", headers=auth_headers).json() == []

        r_tg = client.delete("/api/v1/telegram/unlink", headers=auth_headers)
        assert r_tg.status_code == 200
        tg_link_id = r_tg.json()["id"]
        assert client.get("/api/v1/telegram/link-status", headers=auth_headers).json()["linked"] is False
        assert client.get("/api/v1/telegram/deliveries", headers=auth_headers).json() == []
    finally:
        event.remove(bind, "before_cursor_execute", _capture_sql)

    # Zero SQL DELETE statements executed across all 6 DELETE endpoints
    hard_deletes = [stmt for stmt in executed_sql if stmt.startswith("DELETE ")]
    assert hard_deletes == []

    # Every row still exists in the database with is_deleted=True
    db_session.expire_all()
    for model, pk in [
        (Element, eid),
        (Wall, wid),
        (Room, rid),
        (Project, pid),
        (Customer, cid),
        (PairingCode, tg_link_id),
        (TelegramDelivery, delivery_id),
    ]:
        row = db_session.get(model, pk)
        assert row is not None, f"{model.__tablename__}:{pk} was hard deleted"
        assert row.is_deleted is True, f"{model.__tablename__}:{pk} missing is_deleted=True"
        assert row.deleted_at is not None

    # /sync/pull returns tombstones for every deleted entity
    pull = client.get("/api/v1/sync/pull", headers=auth_headers).json()
    tombstones = {(t["entity_type"], t["entity_id"]): t for t in pull["tombstones"]}
    for etype, pk in [
        ("element", eid),
        ("wall", wid),
        ("room", rid),
        ("project", pid),
        ("customer", cid),
        ("telegram_link", tg_link_id),
        ("telegram_delivery", delivery_id),
    ]:
        assert (etype, pk) in tombstones
        assert tombstones[(etype, pk)]["is_deleted"] is True


def test_audit_log_records_all_required_actions_and_enforces_admin_only_get(
    client, db_session
):
    user_headers, user_id = _register_and_login(client, "surveyor-audit@example.com")
    admin_headers, admin_id = _register_and_login(client, "admin-audit@example.com")
    admin_user = db_session.get(User, admin_id)
    admin_user.role = "admin"
    db_session.commit()

    # Non-admin and unauthenticated callers are blocked from /admin/audit
    assert client.get("/api/v1/admin/audit").status_code == 401
    assert client.get("/api/v1/admin/audit", headers=user_headers).status_code == 403

    # 1. Approve + Export
    pid, _rid, wall_ids, eid = _create_approved_closed_room(client, user_headers)
    wid = wall_ids[0]
    exp = client.post(
        f"/api/v1/exports/{pid}",
        headers=user_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert exp.status_code == 201
    export_id = exp.json()["id"]

    # 2. Edit-after-approval (REST PUT)
    wall_now = client.get(f"/api/v1/walls/{wid}", headers=user_headers).json()
    edited = client.put(
        f"/api/v1/walls/{wid}",
        headers=user_headers,
        json={"length_mm": 4100, "end_x_mm": 4100, "version": wall_now["version"]},
    )
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "needs_review"

    # 3. Sync edits (create + update + approve + edit-after-approval via sync)
    sync_cust_id = str(uuid.uuid4())
    r_sync_create = client.post(
        "/api/v1/sync/push",
        headers=user_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "customer",
                    "entity_id": sync_cust_id,
                    "operation": "create",
                    "payload": {"name": "Sync Client", "phone": "09121112233"},
                }
            ]
        },
    )
    assert r_sync_create.json()["results"][0]["status"] == "applied"

    r_sync_update = client.post(
        "/api/v1/sync/push",
        headers=user_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "customer",
                    "entity_id": sync_cust_id,
                    "operation": "update",
                    "base_version": 1,
                    "payload": {"name": "Sync Client Renamed"},
                }
            ]
        },
    )
    assert r_sync_update.json()["results"][0]["status"] == "applied"

    # 4. Conflict detection + conflict resolution (keep_server and keep_local)
    conflict_op_id = str(uuid.uuid4())
    r_conflict = client.post(
        "/api/v1/sync/push",
        headers=user_headers,
        json={
            "operations": [
                {
                    "id": conflict_op_id,
                    "entity_type": "customer",
                    "entity_id": sync_cust_id,
                    "operation": "update",
                    "base_version": 1,  # stale; server is at v2
                    "payload": {"name": "Stale Offline Edit"},
                }
            ]
        },
    )
    assert r_conflict.json()["results"][0]["status"] == "conflict"

    r_resolve = client.post(
        f"/api/v1/sync/conflicts/{conflict_op_id}/resolve",
        headers=user_headers,
        json={
            "resolution": "keep_local",
            "payload": {"name": "Resolved Offline Winner"},
            "base_version": 2,
        },
    )
    assert r_resolve.status_code == 200
    assert r_resolve.json()["new_version"] == 3

    # 5. Soft delete
    assert client.delete(f"/api/v1/elements/{eid}", headers=user_headers).status_code == 200

    # Admin inspects audit log
    events_resp = client.get("/api/v1/admin/audit?limit=200", headers=admin_headers)
    assert events_resp.status_code == 200
    events = events_resp.json()
    by_action: dict[str, list[dict]] = {}
    for ev in events:
        by_action.setdefault(ev["action"], []).append(ev)

    for required_action in [
        "wall.approve",
        "element.approve",
        "wall.edit_after_approval",
        "sync.create",
        "sync.update",
        "sync.conflict_detected",
        "sync.conflict_resolved",
        "element.soft_delete",
        "export.create",
    ]:
        assert required_action in by_action, f"Missing audit action {required_action}"
        sample = by_action[required_action][0]
        assert sample["actor_id"] == user_id
        assert sample["user_id"] == user_id
        assert sample["entity_type"] is not None
        assert sample["entity_id"] is not None
        assert sample["timestamp"] is not None

    # Verify old_values and new_values fidelity on key transitions
    edit_after = by_action["wall.edit_after_approval"][0]
    assert edit_after["old_values"]["review_status"] == "approved"
    assert edit_after["old_values"]["length_mm"] == 4000
    assert edit_after["new_values"]["review_status"] == "needs_review"
    assert edit_after["new_values"]["length_mm"] == 4100
    assert edit_after["new_values"]["approved_by"] is None

    approve_ev = next(e for e in by_action["wall.approve"] if e["entity_id"] == wid)
    assert approve_ev["old_values"]["review_status"] == "needs_review"
    assert approve_ev["new_values"]["review_status"] == "approved"
    assert approve_ev["new_values"]["approved_by"] == user_id

    conflict_resolved_ev = by_action["sync.conflict_resolved"][0]
    assert conflict_resolved_ev["old_values"]["name"] == "Sync Client Renamed"
    assert conflict_resolved_ev["new_values"]["name"] == "Resolved Offline Winner"
    assert conflict_resolved_ev["new_values"]["resolution"] == "keep_local"

    soft_del_ev = next(
        e for e in by_action["element.soft_delete"] if e["entity_id"] == eid
    )
    assert soft_del_ev["old_values"]["is_deleted"] is False
    assert soft_del_ev["new_values"]["is_deleted"] is True

    export_ev = next(
        e for e in by_action["export.create"] if e["entity_id"] == export_id
    )
    assert export_ev["old_values"] is None
    assert export_ev["new_values"]["format"] == "pdf"
    assert export_ev["new_values"]["status"] == "done"


def test_audit_log_blocks_updates_and_deletes_at_orm_and_sql_trigger_levels(
    client, auth_headers, db_session
):
    cust = client.post(
        "/api/v1/customers", headers=auth_headers, json={"name": "Immutable Audit Target"}
    )
    assert cust.status_code == 201
    ev = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_id == cust.json()["id"])
        .first()
    )
    assert ev is not None
    audit_id = ev.id
    original_action = ev.action

    # 1. ORM update is blocked
    with pytest.raises(ValueError, match="append-only"), db_session.begin_nested():
        ev.action = "tampered.action"
        db_session.flush()
    db_session.expire(ev)

    # 2. ORM delete is blocked
    with pytest.raises(ValueError, match="append-only"), db_session.begin_nested():
        db_session.delete(ev)
        db_session.flush()
    db_session.expire_all()

    # 3. Direct SQL UPDATE bypassing ORM is blocked by DB trigger
    with pytest.raises(DatabaseError, match="append-only"), db_session.begin_nested():
        db_session.execute(
            text("UPDATE audit_events SET action = 'tampered' WHERE id = :id"),
            {"id": audit_id},
        )

    # 4. Direct SQL DELETE bypassing ORM is blocked by DB trigger
    with pytest.raises(DatabaseError, match="append-only"), db_session.begin_nested():
        db_session.execute(
            text("DELETE FROM audit_events WHERE id = :id"),
            {"id": audit_id},
        )

    db_session.expire_all()
    persisted = db_session.get(AuditEvent, audit_id)
    assert persisted is not None
    assert persisted.action == original_action


class _HighConfidenceVisionProvider:
    provider_name = "openai_compatible"
    model = "vision-pro-test"

    async def analyze_sketch(self, data: bytes, *, language_hint: str = "fa,en") -> dict:
        return {
            "observations": [
                {
                    "label": "Wall North",
                    "value_mm": 3600,
                    "unit": "mm",
                    "source_text": "3600 mm",
                    "source_bbox": [0.1, 0.2, 0.6, 0.5],
                    "confidence": 1.0,
                    "needs_review": True,
                    "uncertainty": None,
                }
            ],
            "ambiguities": [],
            "clarification_questions": [],
        }


class _StubSTT(speech.STTProvider):
    async def transcribe(self, audio: bytes, mime: str, *, language_hint: str = "fa,en") -> str:
        return "طول دیوار سه متر و بیست سانتی‌متر"


def test_ai_per_user_rate_limit_boundary_and_retry_after_across_all_ai_endpoints(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "rate_limit_ai_per_minute", 3)
    monkeypatch.setattr(
        "app.api.v1.ai.configured_provider", lambda db: _HighConfidenceVisionProvider()
    )
    monkeypatch.setattr(
        "app.api.v1.ai.speech.get_stt_provider", lambda client=None: _StubSTT()
    )

    user1_headers, _ = _register_and_login(client, "ai-limit-u1@example.com")
    user2_headers, _ = _register_and_login(client, "ai-limit-u2@example.com")

    # User 1 consumes all 3 allowed requests across the 3 AI endpoints
    r1 = client.post(
        "/api/v1/ai/parse-text",
        headers=user1_headers,
        data={"text": "Wall A: 3000 mm"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v1/ai/sketch-analysis",
        headers=user1_headers,
        files={"file": ("sketch.png", _png_bytes(), "image/png")},
    )
    assert r2.status_code == 200

    r3 = client.post(
        "/api/v1/ai/transcription",
        headers=user1_headers,
        files={"file": ("voice.wav", _wav_bytes(), "audio/wav")},
    )
    assert r3.status_code == 200

    # Request 4+ on EVERY AI endpoint returns 429 with Retry-After
    over_text = client.post(
        "/api/v1/ai/parse-text",
        headers=user1_headers,
        data={"text": "Wall B: 2500 mm"},
    )
    assert over_text.status_code == 429
    assert 1 <= int(over_text.headers["Retry-After"]) <= 60

    over_sketch = client.post(
        "/api/v1/ai/sketch-analysis",
        headers=user1_headers,
        files={"file": ("sketch.png", _png_bytes(), "image/png")},
    )
    assert over_sketch.status_code == 429
    assert 1 <= int(over_sketch.headers["Retry-After"]) <= 60

    over_voice = client.post(
        "/api/v1/ai/transcription",
        headers=user1_headers,
        data={"text": "طول دیوار سه متر"},
    )
    assert over_voice.status_code == 429
    assert 1 <= int(over_voice.headers["Retry-After"]) <= 60

    # User 2 is unaffected (per-user limit)
    other_ok = client.post(
        "/api/v1/ai/parse-text",
        headers=user2_headers,
        data={"text": "Wall C: 2800 mm"},
    )
    assert other_ok.status_code == 200


def test_idempotency_key_on_exports_and_telegram_send_with_conflict_and_expiry(
    client, auth_headers, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "telegram_worker_secret", WORKER_SECRET)
    monkeypatch.setattr(settings, "idempotency_ttl_seconds", 3600)

    pid1, _, _, _ = _create_approved_closed_room(client, auth_headers)
    pid2, _, _, _ = _create_approved_closed_room(client, auth_headers)

    # Link Telegram
    code = client.post("/api/v1/telegram/pairing-code", headers=auth_headers).json()["code"]
    assert (
        client.post(
            "/api/v1/telegram/verify-pairing",
            headers={"X-Webhook-Secret": WORKER_SECRET},
            json={"code": code, "telegram_chat_id": "555111"},
        ).status_code
        == 200
    )

    # --- Export Idempotency ---
    idem_headers = {**auth_headers, "Idempotency-Key": "export-idem-001"}
    first_exp = client.post(
        f"/api/v1/exports/{pid1}",
        headers=idem_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert first_exp.status_code == 201
    job1_id = first_exp.json()["id"]

    # Same key + same body returns stored result without creating another ExportJob
    replay_exp = client.post(
        f"/api/v1/exports/{pid1}",
        headers=idem_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert replay_exp.status_code == 201
    assert replay_exp.json() == first_exp.json()
    assert db_session.query(ExportJob).filter(ExportJob.project_id == pid1).count() == 1

    # Same key + different body -> 422
    mismatch_exp = client.post(
        f"/api/v1/exports/{pid1}",
        headers=idem_headers,
        json={"format": "png", "layout": "A4"},
    )
    assert mismatch_exp.status_code == 422

    # Same key + different project_id -> 422
    mismatch_proj = client.post(
        f"/api/v1/exports/{pid2}",
        headers=idem_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert mismatch_proj.status_code == 422

    # Expire the export idempotency key -> fresh ExportJob created
    exp_rec = (
        db_session.query(IdempotencyRecord)
        .filter_by(scope="exports.create", idempotency_key="export-idem-001")
        .one()
    )
    exp_rec.expires_at = now_utc() - timedelta(seconds=5)
    db_session.commit()

    fresh_exp = client.post(
        f"/api/v1/exports/{pid1}",
        headers=idem_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert fresh_exp.status_code == 201
    job2_id = fresh_exp.json()["id"]
    assert job2_id != job1_id
    assert db_session.query(ExportJob).filter(ExportJob.project_id == pid1).count() == 2

    # --- Telegram Send Idempotency ---
    tg_headers = {**auth_headers, "Idempotency-Key": "tg-idem-001"}
    first_tg = client.post(
        "/api/v1/telegram/send",
        headers=tg_headers,
        json={"export_job_id": job1_id},
    )
    assert first_tg.status_code == 200
    deliv1_id = first_tg.json()["delivery_id"]

    # Same key + same body returns stored delivery without duplicating TelegramDelivery
    replay_tg = client.post(
        "/api/v1/telegram/send",
        headers=tg_headers,
        json={"export_job_id": job1_id},
    )
    assert replay_tg.status_code == 200
    assert replay_tg.json() == first_tg.json()
    assert db_session.query(TelegramDelivery).count() == 1

    # Same key + different body -> 422
    mismatch_tg = client.post(
        "/api/v1/telegram/send",
        headers=tg_headers,
        json={"export_job_id": job2_id},
    )
    assert mismatch_tg.status_code == 422

    # Expire the telegram idempotency key -> fresh TelegramDelivery created
    tg_rec = (
        db_session.query(IdempotencyRecord)
        .filter_by(scope="telegram.send", idempotency_key="tg-idem-001")
        .one()
    )
    tg_rec.expires_at = now_utc() - timedelta(seconds=5)
    db_session.commit()

    fresh_tg = client.post(
        "/api/v1/telegram/send",
        headers=tg_headers,
        json={"export_job_id": job1_id},
    )
    assert fresh_tg.status_code == 200
    assert fresh_tg.json()["delivery_id"] != deliv1_id
    assert db_session.query(TelegramDelivery).count() == 2


def test_ai_provenance_persisted_and_cannot_become_approved_without_user_post_approve(
    client, auth_headers, db_session, monkeypatch
):
    monkeypatch.setattr(
        "app.api.v1.ai.configured_provider", lambda db: _HighConfidenceVisionProvider()
    )
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()

    proj = client.post(
        "/api/v1/projects", headers=auth_headers, json={"title": "Provenance Survey"}
    ).json()
    pid = proj["id"]
    room = client.post(
        f"/api/v1/projects/{pid}/rooms",
        headers=auth_headers,
        json={"label": "Main Kitchen", "room_type": "rectangular"},
    ).json()
    rid = room["id"]

    # Upload source sketch image asset
    asset_resp = client.post(
        f"/api/v1/assets?project_id={pid}",
        headers=auth_headers,
        files={"file": ("field_sketch.png", _png_bytes(), "image/png")},
    )
    assert asset_resp.status_code == 201
    asset_id = asset_resp.json()["id"]

    # Analyze sketch (confidence=1.0 returned by model!)
    sketch_resp = client.post(
        "/api/v1/ai/sketch-analysis",
        headers=auth_headers,
        data={"project_id": pid, "asset_id": asset_id},
        files={"file": ("field_sketch.png", _png_bytes(), "image/png")},
    )
    assert sketch_resp.status_code == 200
    obs_out = sketch_resp.json()["observations"][0]
    candidate_id = obs_out["candidate_id"]
    assert obs_out["review_status"] == "needs_review"
    assert obs_out["needs_review"] is True
    assert "approved" not in obs_out

    # Verify persisted provenance row in observations table and /ai/candidates endpoint
    cand = client.get(
        f"/api/v1/ai/candidates/{candidate_id}", headers=auth_headers
    ).json()
    assert cand["source_type"] == "sketch_ai"
    assert cand["source_asset_id"] == asset_id
    assert len(cand["source_image_sha256"]) == 64
    assert cand["source_region"]["bbox"] == [0.1, 0.2, 0.6, 0.5]
    assert cand["prompt_id"] == "sketch_vision_v1"
    assert cand["confidence"] == 1.0
    assert cand["model_name"] == "vision-pro-test"
    assert cand["review_status"] == "needs_review"
    assert cand["linked_entity_id"] is None

    # AI output stays separate from survey tables: zero walls created automatically
    assert db_session.query(Wall).filter(Wall.room_id == rid).count() == 0

    # No direct /approve endpoint exists for AI candidates
    assert (
        client.post(
            f"/api/v1/ai/candidates/{candidate_id}/approve", headers=auth_headers
        ).status_code
        in {404, 405}
    )

    # Create resulting wall measurement linked to the AI candidate with confidence=1.0
    w_north = client.post(
        f"/api/v1/rooms/{rid}/walls",
        headers=auth_headers,
        json={
            "label": "Wall North",
            "length_mm": 3600,
            "height_mm": 2700,
            "start_x_mm": 0,
            "start_y_mm": 0,
            "end_x_mm": 3600,
            "end_y_mm": 0,
            "source": "sketch_ai",
            "confidence": 1.0,
            "source_observation_id": candidate_id,
        },
    )
    assert w_north.status_code == 201
    wid = w_north.json()["id"]
    assert w_north.json()["review_status"] == "needs_review"
    assert w_north.json()["approved_by"] is None
    assert w_north.json()["source_observation_id"] == candidate_id

    # Add remaining 3 walls and approve ONLY those 3 so wid is the sole gate
    other_specs = [
        ("Wall East", 3000, 2700, 3600, 0, 3600, 3000),
        ("Wall South", 3600, 2700, 3600, 3000, 0, 3000),
        ("Wall West", 3000, 2700, 0, 3000, 0, 0),
    ]
    for label, l_mm, h_mm, sx, sy, ex, ey in other_specs:
        ow = client.post(
            f"/api/v1/rooms/{rid}/walls",
            headers=auth_headers,
            json={
                "label": label,
                "length_mm": l_mm,
                "height_mm": h_mm,
                "start_x_mm": sx,
                "start_y_mm": sy,
                "end_x_mm": ex,
                "end_y_mm": ey,
            },
        ).json()
        assert (
            client.post(f"/api/v1/walls/{ow['id']}/approve", headers=auth_headers).status_code
            == 200
        )

    # Candidate is linked to wall, still unapproved
    cand_linked = client.get(
        f"/api/v1/ai/candidates/{candidate_id}", headers=auth_headers
    ).json()
    assert cand_linked["linked_entity_type"] == "wall"
    assert cand_linked["linked_entity_id"] == wid
    assert cand_linked["review_status"] == "needs_review"

    # Attempt 1: REST PUT with review_status='approved' -> 422
    put_approve = client.put(
        f"/api/v1/walls/{wid}",
        headers=auth_headers,
        json={"review_status": "approved", "version": 1},
    )
    assert put_approve.status_code == 422

    # Attempt 2: Sync update mixing dimension + review_status='approved' -> failed
    sync_smuggle = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "wall",
                    "entity_id": wid,
                    "operation": "update",
                    "base_version": 1,
                    "payload": {"length_mm": 3600, "review_status": "approved"},
                }
            ]
        },
    )
    assert sync_smuggle.json()["results"][0]["status"] == "failed"

    # Attempt 3: Export while AI-derived wall has not had POST /approve -> 409
    blocked_export = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert blocked_export.status_code == 409

    assert client.get(f"/api/v1/walls/{wid}", headers=auth_headers).json()["review_status"] == "needs_review"
    assert (
        client.get(f"/api/v1/ai/candidates/{candidate_id}", headers=auth_headers).json()[
            "review_status"
        ]
        == "needs_review"
    )

    # Explicit user approval via POST /walls/{id}/approve succeeds
    approved_wall = client.post(f"/api/v1/walls/{wid}/approve", headers=auth_headers)
    assert approved_wall.status_code == 200
    assert approved_wall.json()["review_status"] == "approved"
    assert approved_wall.json()["approved_by"] == me["id"]

    cand_after_approve = client.get(
        f"/api/v1/ai/candidates/{candidate_id}", headers=auth_headers
    ).json()
    assert cand_after_approve["review_status"] == "approved"

    # Export now succeeds
    ok_export = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert ok_export.status_code == 201

    # Editing the approved wall resets both wall and linked observation back to needs_review
    edited = client.put(
        f"/api/v1/walls/{wid}",
        headers=auth_headers,
        json={"height_mm": 2750, "version": approved_wall.json()["version"]},
    )
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "needs_review"
    assert (
        client.get(f"/api/v1/ai/candidates/{candidate_id}", headers=auth_headers).json()[
            "review_status"
        ]
        == "needs_review"
    )


def test_concurrent_idempotency_race_produces_single_export_and_delivery(
    tmp_path, monkeypatch
):
    import concurrent.futures
    import threading

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base, get_db
    from app.main import app

    db_file = tmp_path / "concurrent_idempotency.sqlite"
    race_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=race_engine)
    SessionLocal = sessionmaker(bind=race_engine, autocommit=False, autoflush=False)

    def override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    monkeypatch.setattr(settings, "telegram_worker_secret", "race-worker-secret-0123456789")
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as setup_client:
            setup_client.post(
                "/api/v1/auth/register",
                json={
                    "email": "race@example.com",
                    "password": "RacePassword123!",
                    "display_name": "Race Tester",
                },
            )
            token = setup_client.post(
                "/api/v1/auth/login",
                json={"email": "race@example.com", "password": "RacePassword123!"},
            ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            pid, _, _, _ = _create_approved_closed_room(setup_client, headers)

            code = setup_client.post("/api/v1/telegram/pairing-code", headers=headers).json()[
                "code"
            ]
            assert (
                setup_client.post(
                    "/api/v1/telegram/verify-pairing",
                    headers={"X-Webhook-Secret": settings.telegram_worker_secret},
                    json={"code": code, "telegram_chat_id": "777001"},
                ).status_code
                == 200
            )

        workers = 6
        export_barrier = threading.Barrier(workers)

        def call_export(_idx: int) -> tuple[int, dict]:
            with TestClient(app) as worker_client:
                export_barrier.wait(timeout=10)
                resp = worker_client.post(
                    f"/api/v1/exports/{pid}",
                    headers={**headers, "Idempotency-Key": "race-export-key-001"},
                    json={"format": "pdf", "layout": "A4"},
                )
                return resp.status_code, resp.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            export_outcomes = list(pool.map(call_export, range(workers)))

        assert [code for code, _ in export_outcomes] == [201] * workers
        export_ids = {body["id"] for _, body in export_outcomes}
        assert len(export_ids) == 1
        single_export_id = next(iter(export_ids))

        send_barrier = threading.Barrier(workers)

        def call_telegram_send(_idx: int) -> tuple[int, dict]:
            with TestClient(app) as worker_client:
                send_barrier.wait(timeout=10)
                resp = worker_client.post(
                    "/api/v1/telegram/send",
                    headers={**headers, "Idempotency-Key": "race-tg-key-001"},
                    json={"export_job_id": single_export_id},
                )
                return resp.status_code, resp.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            send_outcomes = list(pool.map(call_telegram_send, range(workers)))

        assert [code for code, _ in send_outcomes] == [200] * workers
        delivery_ids = {body["delivery_id"] for _, body in send_outcomes}
        assert len(delivery_ids) == 1

        with SessionLocal() as check_db:
            assert (
                check_db.query(ExportJob).filter(ExportJob.project_id == pid).count() == 1
            )
            assert (
                check_db.query(TelegramDelivery)
                .filter(TelegramDelivery.export_job_id == single_export_id)
                .count()
                == 1
            )
    finally:
        app.dependency_overrides.clear()
        race_engine.dispose()


def test_element_approve_unapprove_edit_and_delete_sync_linked_observation(
    client, auth_headers
):
    pid = client.post(
        "/api/v1/projects", headers=auth_headers, json={"title": "Element Provenance"}
    ).json()["id"]
    rid = client.post(
        f"/api/v1/projects/{pid}/rooms", headers=auth_headers, json={"label": "Kitchen"}
    ).json()["id"]
    wid = client.post(
        f"/api/v1/rooms/{rid}/walls",
        headers=auth_headers,
        json={
            "label": "North Wall",
            "length_mm": 4000,
            "height_mm": 2700,
            "start_x_mm": 0,
            "start_y_mm": 0,
            "end_x_mm": 4000,
            "end_y_mm": 0,
        },
    ).json()["id"]

    parsed = client.post(
        "/api/v1/ai/parse-text",
        headers=auth_headers,
        data={"project_id": pid, "text": "window width 120 cm"},
    )
    assert parsed.status_code == 200
    obs_rest_id = parsed.json()["observations"][0]["candidate_id"]

    elem_resp = client.post(
        f"/api/v1/walls/{wid}/elements",
        headers=auth_headers,
        json={
            "label": "Kitchen Window",
            "kind": "window",
            "offset_mm": 500,
            "width_mm": 1200,
            "height_mm": 1000,
            "sill_mm": 900,
            "source": "voice_ai",
            "confidence": 0.96,
            "source_observation_id": obs_rest_id,
        },
    )
    assert elem_resp.status_code == 201
    eid = elem_resp.json()["id"]
    assert elem_resp.json()["review_status"] == "needs_review"

    def obs_status(cid: str) -> dict:
        r = client.get(f"/api/v1/ai/candidates/{cid}", headers=auth_headers)
        assert r.status_code == 200
        return r.json()

    assert obs_status(obs_rest_id)["review_status"] == "needs_review"
    assert obs_status(obs_rest_id)["linked_entity_type"] == "element"
    assert obs_status(obs_rest_id)["linked_entity_id"] == eid

    # 1. REST approve -> linked Observation becomes approved
    approved = client.post(f"/api/v1/elements/{eid}/approve", headers=auth_headers)
    assert approved.status_code == 200
    assert approved.json()["review_status"] == "approved"
    assert obs_status(obs_rest_id)["review_status"] == "approved"

    # 2. REST un-approve (explicit review_status='needs_review') -> linked Observation resets
    unapproved = client.put(
        f"/api/v1/elements/{eid}",
        headers=auth_headers,
        json={"review_status": "needs_review", "version": approved.json()["version"]},
    )
    assert unapproved.status_code == 200
    assert unapproved.json()["review_status"] == "needs_review"
    assert unapproved.json()["approved_by"] is None
    assert obs_status(obs_rest_id)["review_status"] == "needs_review"

    # Re-approve via REST, then 3. REST edit-after-approval -> linked Observation resets
    reapproved = client.post(f"/api/v1/elements/{eid}/approve", headers=auth_headers)
    assert reapproved.status_code == 200
    assert obs_status(obs_rest_id)["review_status"] == "approved"

    edited = client.put(
        f"/api/v1/elements/{eid}",
        headers=auth_headers,
        json={"offset_mm": 650, "version": reapproved.json()["version"]},
    )
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "needs_review"
    assert obs_status(obs_rest_id)["review_status"] == "needs_review"

    # Re-approve via REST, then 4. REST delete -> linked Observation resets to needs_review
    approved_before_del = client.post(
        f"/api/v1/elements/{eid}/approve", headers=auth_headers
    )
    assert approved_before_del.status_code == 200
    assert obs_status(obs_rest_id)["review_status"] == "approved"

    deleted = client.delete(f"/api/v1/elements/{eid}", headers=auth_headers)
    assert deleted.status_code == 200
    assert obs_status(obs_rest_id)["review_status"] == "needs_review"

    # Now verify all 4 transitions through /api/v1/sync/push as well
    parsed_sync = client.post(
        "/api/v1/ai/parse-text",
        headers=auth_headers,
        data={"project_id": pid, "text": "door width 90 cm"},
    )
    assert parsed_sync.status_code == 200
    obs_sync_id = parsed_sync.json()["observations"][0]["candidate_id"]
    sync_eid = str(uuid.uuid4())

    create_op = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_eid,
                    "operation": "create",
                    "payload": {
                        "wall_id": wid,
                        "label": "Sync Door",
                        "kind": "door",
                        "offset_mm": 1800,
                        "width_mm": 900,
                        "height_mm": 2100,
                        "sill_mm": 0,
                        "source": "voice_ai",
                        "confidence": 0.94,
                        "source_observation_id": obs_sync_id,
                    },
                }
            ]
        },
    )
    assert create_op.json()["results"][0]["status"] == "applied"
    assert obs_status(obs_sync_id)["review_status"] == "needs_review"
    assert obs_status(obs_sync_id)["linked_entity_id"] == sync_eid

    # 1b. Sync approve
    sync_approve = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_eid,
                    "operation": "update",
                    "base_version": 1,
                    "payload": {"review_status": "approved"},
                }
            ]
        },
    )
    assert sync_approve.json()["results"][0]["status"] == "applied"
    assert obs_status(obs_sync_id)["review_status"] == "approved"

    # 2b. Sync un-approve
    sync_unapprove = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_eid,
                    "operation": "update",
                    "base_version": 2,
                    "payload": {"review_status": "needs_review"},
                }
            ]
        },
    )
    assert sync_unapprove.json()["results"][0]["status"] == "applied"
    assert obs_status(obs_sync_id)["review_status"] == "needs_review"

    # Re-approve, then 3b. Sync edit-after-approval
    assert (
        client.post(
            "/api/v1/sync/push",
            headers=auth_headers,
            json={
                "operations": [
                    {
                        "id": str(uuid.uuid4()),
                        "entity_type": "element",
                        "entity_id": sync_eid,
                        "operation": "update",
                        "base_version": 3,
                        "payload": {"review_status": "approved"},
                    }
                ]
            },
        ).json()["results"][0]["status"]
        == "applied"
    )
    assert obs_status(obs_sync_id)["review_status"] == "approved"

    sync_edit = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_eid,
                    "operation": "update",
                    "base_version": 4,
                    "payload": {"offset_mm": 1900},
                }
            ]
        },
    )
    assert sync_edit.json()["results"][0]["status"] == "applied"
    assert obs_status(obs_sync_id)["review_status"] == "needs_review"

    # Re-approve, then 4b. Sync delete
    assert (
        client.post(
            "/api/v1/sync/push",
            headers=auth_headers,
            json={
                "operations": [
                    {
                        "id": str(uuid.uuid4()),
                        "entity_type": "element",
                        "entity_id": sync_eid,
                        "operation": "update",
                        "base_version": 5,
                        "payload": {"review_status": "approved"},
                    }
                ]
            },
        ).json()["results"][0]["status"]
        == "applied"
    )
    assert obs_status(obs_sync_id)["review_status"] == "approved"

    sync_delete = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_eid,
                    "operation": "delete",
                    "base_version": 6,
                    "payload": {},
                }
            ]
        },
    )
    assert sync_delete.json()["results"][0]["status"] == "applied"
    assert obs_status(obs_sync_id)["review_status"] == "needs_review"


def test_ai_rate_limit_sliding_window_blocks_double_quota_across_minute_boundary(
    client, auth_headers, db_session, monkeypatch
):
    from sqlalchemy import delete

    import app.core.throttle as throttle_mod
    from app.models.db_models import AuthThrottle

    db_session.execute(delete(AuthThrottle))
    db_session.commit()
    monkeypatch.setattr(settings, "rate_limit_ai_per_minute", 3)

    clock = {"now": 1079.0}  # 1 second before minute boundary 1080 (18 * 60)
    monkeypatch.setattr(throttle_mod.time, "time", lambda: clock["now"])

    for _ in range(3):
        res = client.post(
            "/api/v1/ai/parse-text",
            headers=auth_headers,
            data={"text": "wall length 300 cm"},
        )
        assert res.status_code == 200

    # Advance 2 seconds across the 60-second clock boundary (1079 -> 1081):
    # sliding window must still count all 3 requests from t=1079 and reject with 429.
    clock["now"] = 1081.0
    across_boundary = client.post(
        "/api/v1/ai/parse-text",
        headers=auth_headers,
        data={"text": "wall length 300 cm"},
    )
    assert across_boundary.status_code == 429
    assert across_boundary.headers["Retry-After"] == "58"

    # At t=1138 (59s elapsed since 1079), still blocked with Retry-After=1.
    clock["now"] = 1138.0
    nearly_expired = client.post(
        "/api/v1/ai/parse-text",
        headers=auth_headers,
        data={"text": "wall length 300 cm"},
    )
    assert nearly_expired.status_code == 429
    assert nearly_expired.headers["Retry-After"] == "1"

    # At t=1139 (full 60s elapsed since 1079), quota reopens cleanly.
    clock["now"] = 1139.0
    allowed_again = client.post(
        "/api/v1/ai/parse-text",
        headers=auth_headers,
        data={"text": "wall length 300 cm"},
    )
    assert allowed_again.status_code == 200

