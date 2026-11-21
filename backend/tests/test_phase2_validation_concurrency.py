import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.db_models import Customer, Element, Project, Room, User, Wall


def _setup_hierarchy(client, auth_headers):
    cust = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={"name": "Workshop Client", "phone": "09120000000"},
    ).json()
    proj = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"title": "Phase 2 Kitchen", "customer_id": cust["id"]},
    ).json()
    room = client.post(
        f"/api/v1/projects/{proj['id']}/rooms",
        headers=auth_headers,
        json={"label": "Main Kitchen", "room_type": "rectangular"},
    ).json()
    wall = client.post(
        f"/api/v1/rooms/{room['id']}/walls",
        headers=auth_headers,
        json={
            "label": "Wall North",
            "length_mm": 4000,
            "height_mm": 2700,
            "start_x_mm": 0,
            "start_y_mm": 0,
            "end_x_mm": 4000,
            "end_y_mm": 0,
        },
    ).json()
    elem = client.post(
        f"/api/v1/walls/{wall['id']}/elements",
        headers=auth_headers,
        json={
            "label": "North Window",
            "kind": "window",
            "offset_mm": 500,
            "width_mm": 1200,
            "height_mm": 1100,
            "sill_mm": 900,
            "depth_mm": 150,
        },
    ).json()
    return cust, proj, room, wall, elem


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("height_mm", "2100"),
        ("sill_mm", "900"),
        ("depth_mm", "600"),
        ("offset_mm", "500"),
        ("width_mm", "1200"),
        ("height_mm", True),
        ("sill_mm", False),
        ("depth_mm", 1.5),
        ("height_mm", 0),
        ("height_mm", -10),
        ("sill_mm", -1),
        ("depth_mm", -1),
    ],
)
def test_element_update_rejects_string_2100_non_strict_and_negative_bounds(
    client, auth_headers, field, bad_value
):
    _, _, _, _, elem = _setup_hierarchy(client, auth_headers)
    resp = client.put(
        f"/api/v1/elements/{elem['id']}",
        headers=auth_headers,
        json={field: bad_value, "version": elem["version"]},
    )
    assert resp.status_code == 422
    unchanged = client.get(
        f"/api/v1/elements/{elem['id']}", headers=auth_headers
    ).json()
    assert unchanged["height_mm"] == 1100
    assert unchanged["sill_mm"] == 900
    assert unchanged["depth_mm"] == 150


@pytest.mark.parametrize("invalid_kind", ["fridge", "dishwasher", "WINDOW", "", 123])
def test_element_kind_restricted_to_enum_across_create_update_and_sync(
    client, auth_headers, invalid_kind
):
    _, _, _, wall, elem = _setup_hierarchy(client, auth_headers)

    create_resp = client.post(
        f"/api/v1/walls/{wall['id']}/elements",
        headers=auth_headers,
        json={
            "label": "Invalid Kind",
            "kind": invalid_kind,
            "offset_mm": 2000,
            "width_mm": 600,
        },
    )
    assert create_resp.status_code == 422

    update_resp = client.put(
        f"/api/v1/elements/{elem['id']}",
        headers=auth_headers,
        json={"kind": invalid_kind, "version": elem["version"]},
    )
    assert update_resp.status_code == 422

    sync_resp = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "element",
                    "entity_id": elem["id"],
                    "operation": "update",
                    "base_version": elem["version"],
                    "payload": {"kind": invalid_kind},
                }
            ]
        },
    )
    assert sync_resp.json()["results"][0]["status"] == "failed"


def test_optimistic_concurrency_version_and_if_match_on_all_rest_puts(
    client, auth_headers, db_session, monkeypatch
):
    from cryptography.fernet import Fernet

    from app.core.config import settings

    cust, proj, room, wall, elem = _setup_hierarchy(client, auth_headers)

    # 1. Missing version / If-Match is rejected (422) on all domain PUT endpoints
    assert (
        client.put(
            f"/api/v1/customers/{cust['id']}",
            headers=auth_headers,
            json={"name": "No Version"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/v1/projects/{proj['id']}",
            headers=auth_headers,
            json={"title": "No Version"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/v1/rooms/{room['id']}",
            headers=auth_headers,
            json={"label": "No Version"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/v1/walls/{wall['id']}",
            headers=auth_headers,
            json={"length_mm": 4100},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/v1/elements/{elem['id']}",
            headers=auth_headers,
            json={"height_mm": 1200},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={"display_name": "No Version"},
        ).status_code
        == 422
    )

    # 2. Valid version updates succeed (200), bump version to 2, and emit ETag;
    #    replaying stale version 1 returns 409 Conflict!
    c_ok = client.put(
        f"/api/v1/customers/{cust['id']}",
        headers=auth_headers,
        json={"name": "Updated Client", "version": 1},
    )
    assert c_ok.status_code == 200 and c_ok.json()["version"] == 2
    assert c_ok.headers.get("etag") == '"2"'
    assert (
        client.put(
            f"/api/v1/customers/{cust['id']}",
            headers=auth_headers,
            json={"name": "Stale Client", "version": 1},
        ).status_code
        == 409
    )

    # If-Match header also works and rejects stale ETag with 409
    p_ok = client.put(
        f"/api/v1/projects/{proj['id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"title": "Updated Kitchen"},
    )
    assert p_ok.status_code == 200 and p_ok.json()["version"] == 2
    assert (
        client.put(
            f"/api/v1/projects/{proj['id']}",
            headers={**auth_headers, "If-Match": '"1"'},
            json={"title": "Stale Kitchen"},
        ).status_code
        == 409
    )

    r_ok = client.put(
        f"/api/v1/rooms/{room['id']}",
        headers={**auth_headers, "If-Match": 'W/"1"'},
        json={"label": "Updated Room"},
    )
    assert r_ok.status_code == 200 and r_ok.json()["version"] == 2
    assert (
        client.put(
            f"/api/v1/rooms/{room['id']}",
            headers=auth_headers,
            json={"label": "Stale Room", "version": 1},
        ).status_code
        == 409
    )

    w_ok = client.put(
        f"/api/v1/walls/{wall['id']}",
        headers=auth_headers,
        json={"length_mm": 4200, "end_x_mm": 4200, "version": 1},
    )
    assert w_ok.status_code == 200 and w_ok.json()["version"] == 2
    assert (
        client.put(
            f"/api/v1/walls/{wall['id']}",
            headers=auth_headers,
            json={"length_mm": 4300, "end_x_mm": 4300, "version": 1},
        ).status_code
        == 409
    )

    e_ok = client.put(
        f"/api/v1/elements/{elem['id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"height_mm": 1200},
    )
    assert e_ok.status_code == 200 and e_ok.json()["version"] == 2
    assert (
        client.put(
            f"/api/v1/elements/{elem['id']}",
            headers={**auth_headers, "If-Match": '"1"'},
            json={"height_mm": 1300},
        ).status_code
        == 409
    )
    assert (
        client.get(f"/api/v1/elements/{elem['id']}", headers=auth_headers).json()[
            "height_mm"
        ]
        == 1200
    )

    # Admin & profile PUT endpoints also enforce stale version -> 409
    me_ok = client.put(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"display_name": "Surveyor v2", "version": 1},
    )
    assert me_ok.status_code == 200 and me_ok.json()["version"] == 2
    assert (
        client.put(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={"display_name": "Stale Surveyor", "version": 1},
        ).status_code
        == 409
    )

    user_row = db_session.query(User).filter_by(email="test@example.com").one()
    user_row.role = "admin"
    db_session.commit()

    monkeypatch.setattr(
        settings, "secret_encryption_key", Fernet.generate_key().decode()
    )
    cfg_create = client.put(
        "/api/v1/admin/ai-config",
        headers=auth_headers,
        json={"provider": "local", "enabled": True},
    )
    assert cfg_create.status_code == 200 and cfg_create.json()["version"] == 1
    assert (
        client.put(
            "/api/v1/admin/ai-config",
            headers=auth_headers,
            json={"provider": "local", "enabled": False},
        ).status_code
        == 422
    )
    cfg_update = client.put(
        "/api/v1/admin/ai-config",
        headers=auth_headers,
        json={"provider": "local", "enabled": False, "version": 1},
    )
    assert cfg_update.status_code == 200 and cfg_update.json()["version"] == 2
    assert (
        client.put(
            "/api/v1/admin/ai-config",
            headers=auth_headers,
            json={"provider": "local", "enabled": True, "version": 1},
        ).status_code
        == 409
    )


def test_soft_deletes_preserve_rows_and_sync_as_tombstones(
    client, auth_headers, db_session
):
    cust, proj, room, wall, elem = _setup_hierarchy(client, auth_headers)

    # 1. Soft-delete element via REST DELETE -> row persists as tombstone, no longer blocks overlap
    del_elem = client.delete(f"/api/v1/elements/{elem['id']}", headers=auth_headers)
    assert del_elem.status_code == 200
    assert del_elem.json()["is_deleted"] is True

    db_elem = db_session.get(Element, elem["id"])
    assert db_elem is not None
    assert db_elem.is_deleted is True
    assert db_elem.deleted_at is not None

    assert (
        client.get(f"/api/v1/elements/{elem['id']}", headers=auth_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/elements/{elem['id']}",
            params={"include_deleted": True},
            headers=auth_headers,
        ).json()["is_deleted"]
        is True
    )
    assert (
        client.get(
            f"/api/v1/walls/{wall['id']}/elements", headers=auth_headers
        ).json()
        == []
    )
    # Revision history remains accessible and records delete
    elem_revs = client.get(
        f"/api/v1/elements/{elem['id']}/revisions", headers=auth_headers
    ).json()
    assert elem_revs[-1]["change_reason"] == "delete"
    assert elem_revs[-1]["payload"]["is_deleted"] is True

    # New element at the exact same offset succeeds because deleted element is ignored
    replacement = client.post(
        f"/api/v1/walls/{wall['id']}/elements",
        headers=auth_headers,
        json={
            "label": "Replacement Door",
            "kind": "door",
            "offset_mm": 500,
            "width_mm": 900,
            "height_mm": 2100,
            "sill_mm": 0,
        },
    )
    assert replacement.status_code == 201
    replacement_id = replacement.json()["id"]

    # 2. Soft-delete wall via sync/push (operation='delete') -> stale base_version conflicts, valid version tombstones wall & cascades to child element
    bad_sync_del = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "wall",
                    "entity_id": wall["id"],
                    "operation": "delete",
                    "base_version": 99,
                    "payload": {},
                }
            ]
        },
    )
    assert bad_sync_del.json()["results"][0]["status"] == "conflict"

    good_sync_del = client.post(
        "/api/v1/sync/push",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": "wall",
                    "entity_id": wall["id"],
                    "operation": "delete",
                    "base_version": wall["version"],
                    "payload": {},
                }
            ]
        },
    )
    assert good_sync_del.json()["results"][0]["status"] == "applied"
    assert good_sync_del.json()["results"][0]["is_deleted"] is True
    assert db_session.get(Wall, wall["id"]).is_deleted is True
    assert db_session.get(Element, replacement_id).is_deleted is True

    # 3. Soft-delete room and customer via REST DELETE -> rows remain as tombstones
    assert (
        client.delete(f"/api/v1/rooms/{room['id']}", headers=auth_headers).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/customers/{cust['id']}", headers=auth_headers
        ).status_code
        == 200
    )

    db_session.expire_all()
    assert db_session.get(Room, room["id"]).is_deleted is True
    assert db_session.get(Customer, cust["id"]).is_deleted is True
    assert (
        client.get(
            f"/api/v1/projects/{proj['id']}/rooms", headers=auth_headers
        ).json()
        == []
    )
    assert client.get("/api/v1/customers", headers=auth_headers).json() == []

    # 4. Sync pull exposes all deleted rows as tombstones and delete operations
    pull = client.get("/api/v1/sync/pull", headers=auth_headers).json()
    tombstone_keys = {
        (t["entity_type"], t["entity_id"]) for t in pull["tombstones"]
    }
    assert ("customer", cust["id"]) in tombstone_keys
    assert ("room", room["id"]) in tombstone_keys
    assert ("wall", wall["id"]) in tombstone_keys
    assert ("element", elem["id"]) in tombstone_keys
    assert ("element", replacement_id) in tombstone_keys
    assert all(t["is_deleted"] is True and t["deleted_at"] for t in pull["tombstones"])

    delete_ops = {
        (op["entity_type"], op["entity_id"])
        for op in pull["operations"]
        if op["operation"] == "delete" and op["status"] == "applied"
    }
    assert ("customer", cust["id"]) in delete_ops
    assert ("room", room["id"]) in delete_ops
    assert ("wall", wall["id"]) in delete_ops
    assert ("element", elem["id"]) in delete_ops
    assert ("element", replacement_id) in delete_ops


def test_sqlite_foreign_keys_are_enabled_and_violations_fail(db_session):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Room(
                project_id="non-existent-project",
                label="Orphan Room",
                room_type="rectangular",
            )
        )
        db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Wall(
                room_id="non-existent-room",
                label="Orphan Wall",
                length_mm=3000,
                height_mm=2700,
            )
        )
        db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Element(
                wall_id="non-existent-wall",
                label="Orphan Window",
                kind="window",
                offset_mm=100,
                width_mm=800,
            )
        )
        db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Project(
                owner_id="non-existent-user",
                title="Orphan Project",
            )
        )
        db_session.flush()
