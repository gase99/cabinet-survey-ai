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
