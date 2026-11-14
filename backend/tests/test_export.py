import os

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
    for wd in walls:
        client.post(f"/api/v1/rooms/{rid}/walls", headers=auth_headers, json=wd)

    # PDF A4
    exp = client.post(f"/api/v1/exports/{pid}", headers=auth_headers, json={"format":"pdf","layout":"A4"})
    assert exp.status_code == 201
    job_id = exp.json()["id"]
    # Download
    dl = client.get(f"/api/v1/exports/{job_id}/download", headers=auth_headers)
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
    assert len(dl.content) > 1000

    # PNG A3
    exp2 = client.post(f"/api/v1/exports/{pid}", headers=auth_headers, json={"format":"png","layout":"A3"})
    assert exp2.status_code == 201
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
    assert client.post(f'/api/v1/exports/{project}',headers=auth_headers,json={}).status_code==201
    client.put(f'/api/v1/walls/{ids[0]}',headers=auth_headers,json={'length_mm':2500})
    assert client.post(f'/api/v1/exports/{project}',headers=auth_headers,json={}).status_code==400


def _rect_room(client, auth_headers, project_id, label, x=0, y=0, w=4000, h=3000, sketch_wall=False):
    room = client.post(f"/api/v1/projects/{project_id}/rooms", headers=auth_headers,
                       json={"label": label, "room_type": "rectangular"}).json()["id"]
    corners = [(x, y, x + w, y), (x + w, y, x + w, y + h), (x + w, y + h, x, y + h), (x, y + h, x, y)]
    for index, (sx, sy, ex, ey) in enumerate(corners):
        source = "sketch_ai" if (index == 0 and sketch_wall) else "manual"
        client.post(f"/api/v1/rooms/{room}/walls", headers=auth_headers, json={
            "label": f"{label}-W{index}", "length_mm": (w if index % 2 == 0 else h),
            "height_mm": 2700, "start_x_mm": sx, "start_y_mm": sy, "end_x_mm": ex, "end_y_mm": ey,
            "source": source})
    return room


def test_export_includes_every_room_not_only_the_first(client, auth_headers, tmp_path):
    import re
    project = client.post("/api/v1/projects", headers=auth_headers,
                          json={"title": "Two rooms"}).json()["id"]
    _rect_room(client, auth_headers, project, "Kitchen")
    _rect_room(client, auth_headers, project, "Living", x=5000)

    response = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                           json={"format": "pdf", "layout": "A4"})
    assert response.status_code == 201
    download = client.get(f"/api/v1/exports/{response.json()['id']}/download", headers=auth_headers)
    assert download.status_code == 200
    pdf = download.content
    # Two plans plus eight wall elevations: every room must appear.
    pages = len(re.findall(rb"/Type\s*/Page(?![s])", pdf))
    assert pages == 10, f"expected 10 pages (2 rooms x (plan + 4 elevations)), got {pages}"

    png_response = client.post(f"/api/v1/exports/{project}", headers=auth_headers,
                               json={"format": "png", "layout": "A3"})
    assert png_response.status_code == 201
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
