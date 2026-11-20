import io
import uuid
import pytest
from pypdf import PdfReader
from app.models.db_models import Element, MeasurementRevision


def _create_closed_room(client, auth_headers, title="Integrity Kitchen"):
    pid = client.post(
        "/api/v1/projects", headers=auth_headers, json={"title": title}
    ).json()["id"]
    rid = client.post(
        f"/api/v1/projects/{pid}/rooms",
        headers=auth_headers,
        json={"label": "Kitchen", "room_type": "rectangular"},
    ).json()["id"]
    walls_spec = [
        ("Wall A", 4000, 0, 0, 4000, 0),
        ("Wall B", 3000, 4000, 0, 4000, 3000),
        ("Wall C", 4000, 4000, 3000, 0, 3000),
        ("Wall D", 3000, 0, 3000, 0, 0),
    ]
    wall_ids = []
    for label, length, sx, sy, ex, ey in walls_spec:
        resp = client.post(
            f"/api/v1/rooms/{rid}/walls",
            headers=auth_headers,
            json={
                "label": label,
                "length_mm": length,
                "height_mm": 2700,
                "start_x_mm": sx,
                "start_y_mm": sy,
                "end_x_mm": ex,
                "end_y_mm": ey,
                "source": "manual",
            },
        )
        assert resp.status_code == 201
        wall_ids.append(resp.json()["id"])
    return pid, rid, wall_ids


def test_manual_create_is_never_auto_approved_rest_and_sync(client, auth_headers):
    pid, rid, wall_ids = _create_closed_room(client, auth_headers)

    # REST manual wall starts as needs_review with no approval metadata
    wall_a = client.get(f"/api/v1/walls/{wall_ids[0]}", headers=auth_headers).json()
    assert wall_a["source"] == "manual"
    assert wall_a["review_status"] == "needs_review"
    assert wall_a["approved_by"] is None
    assert wall_a["approved_at"] is None

    # REST manual element with all required dimensions starts as needs_review
    complete_elem = client.post(
        f"/api/v1/walls/{wall_ids[0]}/elements",
        headers=auth_headers,
        json={
            "label": "Window",
            "kind": "window",
            "offset_mm": 500,
            "width_mm": 1200,
            "height_mm": 1000,
            "sill_mm": 900,
            "source": "manual",
        },
    )
    assert complete_elem.status_code == 201
    assert complete_elem.json()["review_status"] == "needs_review"
    assert complete_elem.json()["approved_by"] is None
    assert complete_elem.json()["approved_at"] is None

    # REST manual element missing height_mm or sill_mm starts as incomplete
    missing_height = client.post(
        f"/api/v1/walls/{wall_ids[1]}/elements",
        headers=auth_headers,
        json={
            "label": "Vent",
            "kind": "ventilation",
            "offset_mm": 200,
            "width_mm": 200,
            "sill_mm": 2100,
            "source": "manual",
        },
    )
    assert missing_height.status_code == 201
    assert missing_height.json()["review_status"] == "incomplete"

    missing_sill = client.post(
        f"/api/v1/walls/{wall_ids[2]}/elements",
        headers=auth_headers,
        json={
            "label": "Socket",
            "kind": "socket",
            "offset_mm": 300,
            "width_mm": 100,
            "height_mm": 80,
            "source": "manual",
        },
    )
    assert missing_sill.status_code == 201
    assert missing_sill.json()["review_status"] == "incomplete"

    # Sync manual create for wall & complete/incomplete elements also never auto-approves
    sync_wall_id = str(uuid.uuid4())
    sync_elem_complete_id = str(uuid.uuid4())
    sync_elem_incomplete_id = str(uuid.uuid4())
    push_resp = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "wall",
                    "entity_id": sync_wall_id,
                    "operation": "create",
                    "payload": {
                        "room_id": rid,
                        "label": "Sync Manual Wall",
                        "length_mm": 2500,
                        "height_mm": 2700,
                        "source": "manual",
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_elem_complete_id,
                    "operation": "create",
                    "payload": {
                        "wall_id": sync_wall_id,
                        "label": "Sync Door",
                        "kind": "door",
                        "offset_mm": 200,
                        "width_mm": 900,
                        "height_mm": 2100,
                        "sill_mm": 0,
                        "source": "manual",
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": sync_elem_incomplete_id,
                    "operation": "create",
                    "payload": {
                        "wall_id": sync_wall_id,
                        "label": "Sync Pipe",
                        "kind": "gas_pipe",
                        "offset_mm": 1500,
                        "width_mm": 60,
                        "source": "manual",
                    },
                },
            ]
        },
    )
    assert push_resp.status_code == 200
    assert [r["status"] for r in push_resp.json()["results"]] == [
        "applied",
        "applied",
        "applied",
    ]
    assert (
        client.get(f"/api/v1/walls/{sync_wall_id}", headers=auth_headers).json()[
            "review_status"
        ]
        == "needs_review"
    )
    assert (
        client.get(
            f"/api/v1/elements/{sync_elem_complete_id}", headers=auth_headers
        ).json()["review_status"]
        == "needs_review"
    )
    assert (
        client.get(
            f"/api/v1/elements/{sync_elem_incomplete_id}", headers=auth_headers
        ).json()["review_status"]
        == "incomplete"
    )


def test_approve_flow_records_who_and_when_and_rejects_incomplete(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    _, _, wall_ids = _create_closed_room(client, auth_headers)
    wall_id = wall_ids[0]

    # Create incomplete element -> approval must fail on both REST and sync
    elem_resp = client.post(
        f"/api/v1/walls/{wall_id}/elements",
        headers=auth_headers,
        json={
            "label": "Unmeasured Window",
            "kind": "window",
            "offset_mm": 400,
            "width_mm": 1000,
            "source": "manual",
        },
    )
    elem_id = elem_resp.json()["id"]
    assert elem_resp.json()["review_status"] == "incomplete"

    rest_approve_incomplete = client.post(
        f"/api/v1/elements/{elem_id}/approve", headers=auth_headers
    )
    assert rest_approve_incomplete.status_code == 409
    assert "missing required dimensions" in rest_approve_incomplete.json()["detail"]

    sync_approve_incomplete = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": elem_id,
                    "operation": "update",
                    "base_version": 1,
                    "payload": {"review_status": "approved"},
                }
            ]
        },
    )
    assert sync_approve_incomplete.json()["results"][0]["status"] == "failed"

    # Fill missing dimensions -> transitions from incomplete to needs_review
    updated = client.put(
        f"/api/v1/elements/{elem_id}",
        headers=auth_headers,
        json={"height_mm": 1100, "sill_mm": 850, "version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["review_status"] == "needs_review"

    # PUT with review_status='approved' must be rejected (422); approval only via POST /approve
    put_wall_approve = client.put(
        f"/api/v1/walls/{wall_id}",
        headers=auth_headers,
        json={"review_status": "approved", "version": 1},
    )
    assert put_wall_approve.status_code == 422
    assert (
        client.get(f"/api/v1/walls/{wall_id}", headers=auth_headers).json()[
            "review_status"
        ]
        == "needs_review"
    )

    put_elem_approve = client.put(
        f"/api/v1/elements/{elem_id}",
        headers=auth_headers,
        json={"review_status": "approved", "version": updated.json()["version"]},
    )
    assert put_elem_approve.status_code == 422
    assert (
        client.get(f"/api/v1/elements/{elem_id}", headers=auth_headers).json()[
            "review_status"
        ]
        == "needs_review"
    )

    # Explicit approve records approved_by and approved_at
    approved_wall = client.post(
        f"/api/v1/walls/{wall_id}/approve", headers=auth_headers
    )
    assert approved_wall.status_code == 200
    assert approved_wall.json()["review_status"] == "approved"
    assert approved_wall.json()["approved_by"] == me["id"]
    assert approved_wall.json()["approved_at"] is not None

    approved_elem = client.post(
        f"/api/v1/elements/{elem_id}/approve", headers=auth_headers
    )
    assert approved_elem.status_code == 200
    assert approved_elem.json()["review_status"] == "approved"
    assert approved_elem.json()["approved_by"] == me["id"]
    assert approved_elem.json()["approved_at"] is not None


def test_editing_approved_measurement_appends_revision_and_preserves_approved_history(
    client, auth_headers, db_session
):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    _, _, wall_ids = _create_closed_room(client, auth_headers)
    wall_id = wall_ids[0]

    # Approve Wall A (4000 mm)
    approved = client.post(
        f"/api/v1/walls/{wall_id}/approve", headers=auth_headers
    ).json()
    original_approved_at = approved["approved_at"]
    assert approved["review_status"] == "approved"
    assert approved["approved_by"] == me["id"]

    # Edit approved Wall A via PUT -> active status resets, approved metadata cleared, new revision appended
    edited = client.put(
        f"/api/v1/walls/{wall_id}",
        headers=auth_headers,
        json={"length_mm": 4150, "end_x_mm": 4150, "version": approved["version"]},
    )
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "needs_review"
    assert edited.json()["approved_by"] is None
    assert edited.json()["approved_at"] is None
    assert edited.json()["length_mm"] == 4150

    revisions = client.get(
        f"/api/v1/walls/{wall_id}/revisions", headers=auth_headers
    ).json()
    assert [r["revision_number"] for r in revisions] == [1, 2, 3]
    assert [r["change_reason"] for r in revisions] == ["create", "approve", "update"]

    # Revision #2 (approved) is untouched and preserves original 4000 mm + approver + timestamp
    approved_rev = revisions[1]
    assert approved_rev["review_status"] == "approved"
    assert approved_rev["payload"]["length_mm"] == 4000
    assert approved_rev["approved_by"] == me["id"]
    assert approved_rev["approved_at"] is not None
    assert approved_rev["previous_revision_id"] == revisions[0]["id"]

    # Revision #3 links to Revision #2 and records the unapproved 4150 mm proposal
    edit_rev = revisions[2]
    assert edit_rev["previous_revision_id"] == approved_rev["id"]
    assert edit_rev["review_status"] == "needs_review"
    assert edit_rev["payload"]["length_mm"] == 4150
    assert edit_rev["approved_by"] is None
    assert edit_rev["approved_at"] is None
    assert edit_rev["changed_by"] == me["id"]

    # Sync edits on approved elements also append revisions and reset approval
    elem = client.post(
        f"/api/v1/walls/{wall_ids[1]}/elements",
        headers=auth_headers,
        json={
            "label": "Door 1",
            "kind": "door",
            "offset_mm": 300,
            "width_mm": 900,
            "height_mm": 2100,
            "sill_mm": 0,
        },
    ).json()
    elem_id = elem["id"]
    sync_app = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": elem_id,
                    "operation": "update",
                    "base_version": 1,
                    "payload": {"review_status": "approved"},
                }
            ]
        },
    )
    assert sync_app.json()["results"][0]["status"] == "applied"
    sync_edit = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": elem_id,
                    "operation": "update",
                    "base_version": 2,
                    "payload": {"width_mm": 950, "height_mm": None},
                }
            ]
        },
    )
    assert sync_edit.json()["results"][0]["status"] == "applied"
    elem_after = client.get(f"/api/v1/elements/{elem_id}", headers=auth_headers).json()
    assert elem_after["review_status"] == "incomplete"
    assert elem_after["approved_by"] is None

    elem_revs = client.get(
        f"/api/v1/elements/{elem_id}/revisions", headers=auth_headers
    ).json()
    assert [r["change_reason"] for r in elem_revs] == [
        "create",
        "sync_approve",
        "sync_update",
    ]
    assert elem_revs[1]["payload"]["width_mm"] == 900
    assert elem_revs[1]["payload"]["height_mm"] == 2100
    assert elem_revs[1]["review_status"] == "approved"
    assert elem_revs[1]["approved_by"] == me["id"]
    assert elem_revs[2]["payload"]["width_mm"] == 950
    assert elem_revs[2]["payload"]["height_mm"] is None
    assert elem_revs[2]["review_status"] == "incomplete"

    # Revision table rows cannot be mutated or deleted in place
    with pytest.raises(ValueError, match="immutable"):
        with db_session.begin_nested():
            orm_rev = db_session.get(MeasurementRevision, approved_rev["id"])
            orm_rev.review_status = "needs_review"
            db_session.flush()

    with pytest.raises(ValueError, match="immutable"):
        with db_session.begin_nested():
            orm_rev = db_session.get(MeasurementRevision, approved_rev["id"])
            db_session.delete(orm_rev)
            db_session.flush()


def test_export_excludes_or_flags_unapproved_and_unknown_dimension_elements(
    client, auth_headers, db_session
):
    pid, _, wall_ids = _create_closed_room(client, auth_headers, title="Export Safety")
    for wid in wall_ids:
        assert (
            client.post(f"/api/v1/walls/{wid}/approve", headers=auth_headers).status_code
            == 200
        )

    # 1. Approved complete element
    approved_win = client.post(
        f"/api/v1/walls/{wall_ids[0]}/elements",
        headers=auth_headers,
        json={
            "label": "ApprovedWindow",
            "kind": "window",
            "offset_mm": 400,
            "width_mm": 1000,
            "height_mm": 1000,
            "sill_mm": 900,
        },
    ).json()["id"]
    assert (
        client.post(
            f"/api/v1/elements/{approved_win}/approve", headers=auth_headers
        ).status_code
        == 200
    )

    # 2. Unapproved (needs_review) element
    unapproved_door = client.post(
        f"/api/v1/walls/{wall_ids[1]}/elements",
        headers=auth_headers,
        json={
            "label": "DraftDoor",
            "kind": "door",
            "offset_mm": 200,
            "width_mm": 900,
            "height_mm": 2100,
            "sill_mm": 0,
        },
    ).json()["id"]

    # 3. Incomplete element with unknown height_mm and sill_mm
    incomplete_pipe = client.post(
        f"/api/v1/walls/{wall_ids[2]}/elements",
        headers=auth_headers,
        json={
            "label": "MysteryPipe",
            "kind": "gas_pipe",
            "offset_mm": 300,
            "width_mm": 80,
        },
    ).json()["id"]

    # Default strict export rejects and identifies both unapproved and incomplete items
    strict_resp = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert strict_resp.status_code == 409
    assert "DraftDoor" in strict_resp.json()["detail"]
    assert "MysteryPipe" in strict_resp.json()["detail"]

    # Exclude mode omits unapproved/incomplete elements while keeping ApprovedWindow
    excl_resp = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4", "exclude_unapproved": True},
    )
    assert excl_resp.status_code == 201
    excl_body = excl_resp.json()
    excluded_labels = {item["label"] for item in excl_body["excluded_items"]}
    assert excluded_labels == {"DraftDoor", "MysteryPipe"}
    excl_pdf = client.get(
        f"/api/v1/exports/{excl_body['id']}/download", headers=auth_headers
    ).content
    excl_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(excl_pdf)).pages
    )
    assert "ApprovedWindow" in excl_text
    assert "Excluded unapproved/incomplete elements" in excl_text

    # Flag mode renders preliminary export with explicit UNAPPROVED / INCOMPLETE warnings
    flag_resp = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4", "flag_unapproved": True},
    )
    assert flag_resp.status_code == 201
    flag_body = flag_resp.json()
    flagged_by_label = {
        item["label"]: item["reasons"] for item in flag_body["flagged_items"]
    }
    assert "DraftDoor" in flagged_by_label
    assert "needs_review" in flagged_by_label["DraftDoor"]
    assert "MysteryPipe" in flagged_by_label
    assert any("unknown" in r for r in flagged_by_label["MysteryPipe"])

    flag_pdf = client.get(
        f"/api/v1/exports/{flag_body['id']}/download", headers=auth_headers
    ).content
    flag_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(flag_pdf)).pages
    )
    assert "WARNING" in flag_text
    assert "DraftDoor [UNAPPROVED" in flag_text
    assert "MysteryPipe [INCOMPLETE" in flag_text

    # Stored DB labels were not mutated by flag_unapproved rendering
    assert (
        client.get(f"/api/v1/elements/{unapproved_door}", headers=auth_headers).json()[
            "label"
        ]
        == "DraftDoor"
    )
    assert (
        client.get(f"/api/v1/elements/{incomplete_pipe}", headers=auth_headers).json()[
            "label"
        ]
        == "MysteryPipe"
    )

    # Even if a legacy row in DB had review_status='approved' with missing sill_mm, strict export blocks it
    legacy_elem = db_session.get(Element, incomplete_pipe)
    legacy_elem.review_status = "approved"
    db_session.commit()
    tampered_strict = client.post(
        f"/api/v1/exports/{pid}",
        headers=auth_headers,
        json={"format": "pdf", "layout": "A4"},
    )
    assert tampered_strict.status_code == 409
    assert "MysteryPipe" in tampered_strict.json()["detail"]
    assert "unknown" in tampered_strict.json()["detail"]
