
def test_export_pdf_and_png(client, auth_headers):
    p = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Export Kitchen"})
    pid = p.json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/rooms", headers=auth_headers, json={"label": "Kitchen", "room_type":"rectangular"})
    rid = r.json()["id"]
    walls = [
        {"label":"Wall A","length_mm":4000,"height_mm":2700,"start_x_mm":0,"start_y_mm":0,"end_x_mm":4000,"end_y_mm":0},
        {"label":"Wall B","length_mm":3000,"height_mm":2700,"start_x_mm":4000,"start_y_mm":0,"end_x_mm":4000,"end_y_mm":3000},
        {"label":"Wall C","length_mm":4000,"height_mm":2700,"start_x_mm":4000,"start_y_mm":3000,"end_x_mm":0,"end_y_mm":3000},
        {"label":"Wall D","length_mm":3000,"height_mm":2700,"start_x_mm":0,"start_y_mm":3000,"end_x_mm":0,"end_y_mm":0},
    ]
    wall_ids = []
    for wd in walls:
        created = client.post(f"/api/v1/rooms/{rid}/walls", headers=auth_headers, json=wd)
        assert created.json()["review_status"] == "needs_review"
        wall_ids.append(created.json()["id"])
    # Unapproved manual walls cannot be exported without explicit approval
    assert client.post(f"/api/v1/exports/{pid}", headers=auth_headers, json={"format":"pdf","layout":"A4"}).status_code == 409
    for wid in wall_ids:
        assert client.post(f"/api/v1/walls/{wid}/approve", headers=auth_headers).status_code == 200

    # PDF A4
    exp = client.post(f"/api/v1/exports/{pid}", headers=auth_headers, json={"format":"pdf","layout":"A4"})
    assert exp.status_code == 202
    job_id = exp.json()["id"]
    # Download
    dl = client.get(f"/api/v1/exports/{job_id}/download", headers=auth_headers)
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
    assert len(dl.content) > 1000

    # PNG A3
    exp2 = client.post(f"/api/v1/exports/{pid}", headers=auth_headers, json={"format":"png","layout":"A3"})
    assert exp2.status_code == 202
    dl2 = client.get(f"/api/v1/exports/{exp2.json()['id']}/download", headers=auth_headers)
    assert dl2.status_code == 200
    assert "image/png" in dl2.headers["content-type"]

def test_export_list(client, auth_headers):
    lst = client.get("/api/v1/exports", headers=auth_headers)
    assert lst.status_code == 200


def test_export_rejects_invalid_or_unapproved_geometry(client, auth_headers):
    project=client.post('/api/v1/projects',headers=auth_headers,json={'title':'Approval gate'}).json()['id']
    room=client.post(f'/api/v1/projects/{project}/rooms',headers=auth_headers,json={'label':'Kitchen'}).json()['id']
    coords=[(0,0,3000,0,3000),(3000,0,3000,2000,2000),(3000,2000,0,2000,3000),(0,2000,0,0,2000)]
    ids=[]
    for index,(x,y,xx,yy,length) in enumerate(coords):
        ids.append(client.post(f'/api/v1/rooms/{room}/walls',headers=auth_headers,json={
            'label':str(index),'length_mm':length,'height_mm':2700,'start_x_mm':x,'start_y_mm':y,
            'end_x_mm':xx,'end_y_mm':yy,'source':'sketch_ai'}).json()['id'])
    assert client.post(f'/api/v1/exports/{project}',headers=auth_headers,json={}).status_code==409
    assert client.post(f'/api/v1/drawings/{project}/versions',headers=auth_headers).status_code==409
    for wall in ids:
        assert client.post(f'/api/v1/walls/{wall}/approve',headers=auth_headers).status_code==200
    assert client.post(f'/api/v1/exports/{project}',headers=auth_headers,json={}).status_code==202
    client.put(f'/api/v1/walls/{ids[0]}',headers=auth_headers,json={'length_mm':2500,'version':2})
    assert client.post(f'/api/v1/exports/{project}',headers=auth_headers,json={}).status_code==400


def _rect_room(client, auth_headers, project_id, label, x=0, y=0, w=4000, h=3000, sketch_wall=False):
    room = client.post(f"/api/v1/projects/{project_id}/rooms", headers=auth_headers,
                       json={"label": label, "room_type": "rectangular"}).json()["id"]
    corners = [(x, y, x + w, y), (x + w, y, x + w, y + h), (x + w, y + h, x, y + h), (x, y + h, x, y)]
    for index, (sx, sy, ex, ey) in enumerate(corners):
        unapproved_wall = index == 0 and sketch_wall
        source = "sketch_ai" if unapproved_wall else "manual"
        created = client.post(f"/api/v1/rooms/{room}/walls", headers=auth_headers, json={
            "label": f"{label}-W{index}", "length_mm": (w if index % 2 == 0 else h),
            "height_mm": 2700, "start_x_mm": sx, "start_y_mm": sy, "end_x_mm": ex, "end_y_mm": ey,
            "source": source})
        if not unapproved_wall:
            assert client.post(f"/api/v1/walls/{created.json()['id']}/approve", headers=auth_headers).status_code == 200
    return room


def test_export_includes_every_room_not_only_the_first(client, auth_headers, tmp_path):
    import re
    project = client.post("/api/v1/projects", headers=auth_headers,
                          json={"title": "Two rooms"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    _rect_room(client, auth_headers, project, "Living", x=5000)

    response = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                           json={"format": "pdf", "layout": "A4"})
    assert response.status_code == 202
    download = client.get(f"/api/v1/exports/{response.json()['id']}/download", headers=auth_headers)
    assert download.status_code == 200
    pdf = download.content
    # Two plans plus eight wall elevations: every room must appear.
    pages = len(re.findall(rb"/Type\s*/Page(?![s])", pdf))
    assert pages == 10, f"expected 10 pages (2 rooms x (plan + 4 elevations)), got {pages}"

    png_response = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                               json={"format": "png", "layout": "A3"})
    assert png_response.status_code == 202
    png_download = client.get(f"/api/v1/exports/{png_response.json()['id']}/download",
                              headers=auth_headers)
    assert png_download.status_code == 200
    assert len(png_download.content) > 1000


def test_export_fails_when_any_room_has_unapproved_measurements(client, auth_headers):
    project = client.post("/api/v1/projects", headers=auth_headers,
                          json={"title": "Approval across rooms"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    # One AI-sourced wall in the second room is unapproved: the whole export fails.
    _rect_room(client, auth_headers, project, "Living", x=5000, sketch_wall=True)
    response = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                           json={"format": "pdf", "layout": "A4"})
    assert response.status_code == 409
    assert "Living" in response.json()["detail"]


def _element(client, auth_headers, wall_id, label, approve, offset_mm=500):
    created = client.post(f"/api/v1/walls/{wall_id}/elements", headers=auth_headers, json={
        "label": label, "kind": "window", "offset_mm": offset_mm, "width_mm": 900, "height_mm": 1200,
        "sill_mm": 900, "depth_mm": 100})
    assert created.status_code == 201, created.text
    if approve:
        assert client.post(f"/api/v1/elements/{created.json()['id']}/approve",
                           headers=auth_headers).status_code == 200
    return created.json()["id"]


def _room_walls(client, auth_headers, room_id):
    return client.get(f"/api/v1/rooms/{room_id}/walls", headers=auth_headers).json()


def _pdf_pages(pdf: bytes) -> int:
    import re
    return len(re.findall(rb"/Type\s*/Page(?![s])", pdf))


def test_export_response_is_a_queued_job_with_status_and_download_urls(client, auth_headers):
    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Async"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    response = client.post(f"/api/v1/exports/{project}", headers=auth_headers, json={"format": "pdf"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"] == f"/api/v1/exports/{body['id']}"
    assert body["download_url"] == f"/api/v1/exports/{body['id']}/download"
    # TestClient runs background tasks before returning; the job has now finished.
    status = client.get(body["status_url"], headers=auth_headers).json()
    assert status["status"] == "done" and status["error_message"] is None
    assert client.get(body["download_url"], headers=auth_headers).status_code == 200


def test_job_status_flow_queued_running_done(client, auth_headers, db_session, monkeypatch):
    from app.models.db_models import ExportJob
    from app.services import export_jobs

    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Flow"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    _rect_room(client, auth_headers, project, "Living", x=5000)
    seen: list[str] = []
    real_render = export_jobs.render

    def observing_render(spec):
        # Status observed through the public API while the renderer is working.
        job = db_session.query(ExportJob).filter(ExportJob.project_id == project).one()
        seen.append(client.get(f"/api/v1/exports/{job.id}", headers=auth_headers).json()["status"])
        assert len(spec.views) == 10  # 2 rooms x (plan + 4 elevations)
        return real_render(spec)

    monkeypatch.setattr(export_jobs, "render", observing_render)
    response = client.post(f"/api/v1/exports/{project}", headers=auth_headers, json={"format": "pdf"})
    assert response.status_code == 202 and response.json()["status"] == "queued"
    assert seen == ["running"]
    job_id = response.json()["id"]
    assert client.get(f"/api/v1/exports/{job_id}", headers=auth_headers).json()["status"] == "done"
    pdf = client.get(f"/api/v1/exports/{job_id}/download", headers=auth_headers).content
    assert _pdf_pages(pdf) == 10
    from app.models.db_models import AuditEvent
    actions = [e.action for e in db_session.query(AuditEvent).filter(AuditEvent.entity_id == job_id)]
    assert sorted(actions) == ["export.complete", "export.create"]


def test_download_before_completion_is_409_with_status(client, auth_headers, db_session):
    from app.models.db_models import ExportJob

    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Pending"}).json()["id"]
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    job = ExportJob(project_id=project, owner_id=me["id"], format="pdf", layout="A4", status="queued")
    db_session.add(job)
    db_session.commit()
    response = client.get(f"/api/v1/exports/{job.id}/download", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "queued"


def test_render_failure_marks_job_failed_audits_and_allows_retry_with_same_key(
        client, auth_headers, db_session, monkeypatch):
    from app.models.db_models import AuditEvent, ExportJob
    from app.services import export_jobs

    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Fail"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")

    def broken_render(spec):
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(export_jobs, "render", broken_render)
    headers = {**auth_headers, "Idempotency-Key": "export-fail-retry-1"}
    first = client.post(f"/api/v1/exports/{project}", headers=headers, json={"format": "pdf"})
    assert first.status_code == 202
    failed_id = first.json()["id"]
    status = client.get(f"/api/v1/exports/{failed_id}", headers=auth_headers).json()
    assert status["status"] == "failed"
    assert status["error_message"] == "Drawing rendering failed"
    assert "renderer crashed" not in str(status)  # internal error text is not leaked
    download = client.get(f"/api/v1/exports/{failed_id}/download", headers=auth_headers)
    assert download.status_code == 409 and download.json()["detail"]["status"] == "failed"
    fail_events = db_session.query(AuditEvent).filter(
        AuditEvent.entity_id == failed_id, AuditEvent.action == "export.fail").all()
    assert len(fail_events) == 1 and fail_events[0].new_values["status"] == "failed"

    # The same Idempotency-Key now enqueues a fresh attempt instead of replaying a failure.
    monkeypatch.undo()
    retry = client.post(f"/api/v1/exports/{project}", headers=headers, json={"format": "pdf"})
    assert retry.status_code == 202
    assert retry.json()["id"] != failed_id
    assert client.get(f"/api/v1/exports/{retry.json()['id']}", headers=auth_headers).json()["status"] == "done"
    assert db_session.query(ExportJob).filter(ExportJob.project_id == project).count() == 2


def test_idempotent_retry_returns_same_job_without_new_render(client, auth_headers, db_session, monkeypatch):
    from app.models.db_models import ExportJob
    from app.services import export_jobs

    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Idem"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    renders: list[str] = []
    real_render = export_jobs.render

    def counting_render(spec):
        renders.append(spec.format)
        return real_render(spec)

    monkeypatch.setattr(export_jobs, "render", counting_render)
    headers = {**auth_headers, "Idempotency-Key": "export-idem-async-1"}
    first = client.post(f"/api/v1/exports/{project}", headers=headers, json={"format": "png", "layout": "A3"})
    second = client.post(f"/api/v1/exports/{project}", headers=headers, json={"format": "png", "layout": "A3"})
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert renders == ["png"]
    assert db_session.query(ExportJob).filter(ExportJob.project_id == project).count() == 1
    # Reusing the key with a different body is rejected.
    other = client.post(f"/api/v1/exports/{project}", headers=headers, json={"format": "pdf"})
    assert other.status_code == 422


def test_stale_active_job_is_reported_failed(client, auth_headers, db_session):
    from datetime import timedelta

    from app.models.db_models import ExportJob, now_utc

    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Stale"}).json()["id"]
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    old = now_utc() - timedelta(hours=2)
    job = ExportJob(project_id=project, owner_id=me["id"], format="pdf", layout="A4", status="running",
                    created_at=old, updated_at=old)
    db_session.add(job)
    db_session.commit()
    db_session.execute(ExportJob.__table__.update().where(ExportJob.id == job.id).values(updated_at=old))
    db_session.commit()
    status = client.get(f"/api/v1/exports/{job.id}", headers=auth_headers).json()
    assert status["status"] == "failed" and "interrupted" in status["error_message"]


def test_second_room_unapproved_element_is_rejected_excluded_or_flagged_only_explicitly(
        client, auth_headers):
    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Second room"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    living = _rect_room(client, auth_headers, project, "Living", x=5000)
    wall = _room_walls(client, auth_headers, living)[0]["id"]
    _element(client, auth_headers, wall, "ApprovedWin", approve=True)
    _element(client, auth_headers, wall, "DraftWin", approve=False, offset_mm=2000)

    strict = client.post(f"/api/v1/exports/{project}", headers=auth_headers, json={"format": "pdf"})
    assert strict.status_code == 409
    assert "Living" in strict.json()["detail"] and "DraftWin" in strict.json()["detail"]

    excluded = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                           json={"format": "pdf", "exclude_unapproved": True})
    assert excluded.status_code == 202
    items = excluded.json()["excluded_items"]
    assert [(i["room"], i["label"]) for i in items] == [("Living", "DraftWin")]
    status = client.get(f"/api/v1/exports/{excluded.json()['id']}", headers=auth_headers).json()
    assert status["status"] == "done" and status["excluded_items"] == items
    pdf = client.get(f"/api/v1/exports/{excluded.json()['id']}/download", headers=auth_headers).content
    assert _pdf_pages(pdf) == 10  # both rooms are present

    flagged = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                          json={"format": "pdf", "flag_unapproved": True})
    assert flagged.status_code == 202
    assert [(i["room"], i["label"]) for i in flagged.json()["flagged_items"]] == [("Living", "DraftWin")]

    both = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                       json={"format": "pdf", "flag_unapproved": True, "exclude_unapproved": True})
    assert both.status_code == 422


def test_second_room_unapproved_wall_is_409_even_with_exclude(client, auth_headers):
    project = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Second wall"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    _rect_room(client, auth_headers, project, "Living", x=5000, sketch_wall=True)
    excluded = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                           json={"format": "pdf", "exclude_unapproved": True})
    assert excluded.status_code == 409 and "Living" in excluded.json()["detail"]
    flagged = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                          json={"format": "pdf", "flag_unapproved": True})
    assert flagged.status_code == 202
    assert [i["entity_type"] for i in flagged.json()["flagged_items"]] == ["wall"]
    assert flagged.json()["flagged_items"][0]["room"] == "Living"
