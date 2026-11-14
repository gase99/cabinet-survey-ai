def test_room_wall_element_full_flow(client, auth_headers):
    # Create project
    p = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Kitchen Test"})
    pid = p.json()["id"]
    # Create room
    r = client.post(f"/api/v1/projects/{pid}/rooms", headers=auth_headers, json={"label": "Main Kitchen", "room_type":"rectangular"})
    assert r.status_code == 201
    rid = r.json()["id"]
    # Create 4 walls forming rectangle with explicit coordinates
    walls_data = [
        {"label":"Wall A","length_mm":4000,"height_mm":2700,"start_x_mm":0,"start_y_mm":0,"end_x_mm":4000,"end_y_mm":0},
        {"label":"Wall B","length_mm":3000,"height_mm":2700,"start_x_mm":4000,"start_y_mm":0,"end_x_mm":4000,"end_y_mm":3000},
        {"label":"Wall C","length_mm":4000,"height_mm":2700,"start_x_mm":4000,"start_y_mm":3000,"end_x_mm":0,"end_y_mm":3000},
        {"label":"Wall D","length_mm":3000,"height_mm":2700,"start_x_mm":0,"start_y_mm":3000,"end_x_mm":0,"end_y_mm":0},
    ]
    wall_ids=[]
    for wd in walls_data:
        w = client.post(f"/api/v1/rooms/{rid}/walls", headers=auth_headers, json=wd)
        assert w.status_code == 201
        wall_ids.append(w.json()["id"])
    # List walls
    lst=client.get(f"/api/v1/rooms/{rid}/walls", headers=auth_headers)
    assert len(lst.json())==4
    # Add window on Wall A
    win = client.post(f"/api/v1/walls/{wall_ids[0]}/elements", headers=auth_headers, json={"label":"Window 1","kind":"window","offset_mm":800,"width_mm":1200,"height_mm":1000,"sill_mm":900})
    assert win.status_code == 201
    # Add door that overlaps should fail
    overlap = client.post(f"/api/v1/walls/{wall_ids[0]}/elements", headers=auth_headers, json={"label":"Door","kind":"door","offset_mm":1000,"width_mm":900,"height_mm":2100})
    assert overlap.status_code == 400
    # Out of bounds should fail
    oob = client.post(f"/api/v1/walls/{wall_ids[0]}/elements", headers=auth_headers, json={"label":"Too big","kind":"window","offset_mm":3500,"width_mm":1000})
    assert oob.status_code == 400
    # Add gas pipe correctly
    gas = client.post(f"/api/v1/walls/{wall_ids[1]}/elements", headers=auth_headers, json={"label":"Gas pipe","kind":"gas_pipe","offset_mm":100,"width_mm":50})
    assert gas.status_code == 201
    # Verify drawing generation
    plan = client.get(f"/api/v1/drawings/{pid}/plan", headers=auth_headers)
    assert plan.status_code == 200
    assert plan.json()["area_mm2"] == 12000000
    assert plan.json()["perimeter_mm"] == 14000
    assert len(plan.json()["elevations"]) == 4
    assert plan.json()["errors"] == []
    # Create drawing version
    ver = client.post(f"/api/v1/drawings/{pid}/versions", headers=auth_headers)
    assert ver.status_code == 201
    # List versions
    vers = client.get(f"/api/v1/drawings/{pid}/versions", headers=auth_headers)
    assert len(vers.json()) == 1


def test_svg_cannot_read_room_from_another_project(client, auth_headers):
    own = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Own"}).json()["id"]
    client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "AnotherPass123!", "display_name": "Other"})
    token = client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "AnotherPass123!"}).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}
    other = client.post("/api/v1/projects", headers=other_headers, json={"title": "Private"}).json()["id"]
    room = client.post(f"/api/v1/projects/{other}/rooms", headers=other_headers, json={"label": "Private room", "room_type": "rectangular"}).json()["id"]
    result = client.get(f"/api/v1/drawings/{own}/plan.svg", params={"room_id": room}, headers=auth_headers)
    assert result.status_code == 404


def test_missing_height_is_not_invented(client,auth_headers):
    project=client.post('/api/v1/projects',headers=auth_headers,json={'title':'Missing height'}).json()['id']
    room=client.post(f'/api/v1/projects/{project}/rooms',headers=auth_headers,json={'label':'Kitchen'}).json()['id']
    response=client.post(f'/api/v1/rooms/{room}/walls',headers=auth_headers,json={'label':'A','length_mm':3000,'source':'sketch_ai'})
    assert response.status_code==422
