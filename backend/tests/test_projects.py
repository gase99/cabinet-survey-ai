def test_project_crud(client, auth_headers):
    # Create customer first
    c = client.post("/api/v1/customers", headers=auth_headers, json={"name": "Ali Rezai", "phone": "09123456789", "address": "Tehran"})
    assert c.status_code == 201
    cust_id = c.json()["id"]

    # Create project
    p = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Kitchen Remodel", "customer_id": cust_id, "site_notes": "2nd floor"})
    assert p.status_code == 201
    pid = p.json()["id"]
    assert p.json()["title"] == "Kitchen Remodel"

    # List
    lst = client.get("/api/v1/projects", headers=auth_headers)
    assert lst.status_code == 200
    assert any(x["id"]==pid for x in lst.json())

    # Search
    s = client.get("/api/v1/projects", headers=auth_headers, params={"q": "Kitchen"})
    assert any(x["id"]==pid for x in s.json())

    # Update
    u = client.put(f"/api/v1/projects/{pid}", headers=auth_headers, json={"title": "Kitchen Remodel Updated", "status": "in_progress"})
    assert u.status_code == 200
    assert u.json()["title"] == "Kitchen Remodel Updated"
    assert u.json()["version"] == 2

    # Archive
    a = client.post(f"/api/v1/projects/{pid}/archive", headers=auth_headers)
    assert a.status_code == 200

    # Delete (soft)
    d = client.delete(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert d.status_code == 200

    # Not in list without include_deleted
    lst2 = client.get("/api/v1/projects", headers=auth_headers)
    assert not any(x["id"]==pid for x in lst2.json())

    # Restore
    r = client.post(f"/api/v1/projects/{pid}/restore", headers=auth_headers)
    assert r.status_code == 200

    # History
    h = client.get(f"/api/v1/projects/{pid}/history", headers=auth_headers)
    assert h.status_code == 200
    assert len(h.json()) >= 1

def test_project_ownership(client):
    # Two users isolated
    h1 = client.post("/api/v1/auth/register", json={"email": "owner1@example.com", "password": "Password123", "display_name":"Owner1"})
    t1 = client.post("/api/v1/auth/login", json={"email": "owner1@example.com", "password": "Password123"}).json()["access_token"]
    h1h = {"Authorization": f"Bearer {t1}"}
    p = client.post("/api/v1/projects", headers=h1h, json={"title": "Private Project"})
    pid = p.json()["id"]

    # Second user
    client.post("/api/v1/auth/register", json={"email": "owner2@example.com", "password": "Password123", "display_name":"Owner2"})
    t2 = client.post("/api/v1/auth/login", json={"email": "owner2@example.com", "password": "Password123"}).json()["access_token"]
    h2h = {"Authorization": f"Bearer {t2}"}
    # Should not see first user's project
    r = client.get(f"/api/v1/projects/{pid}", headers=h2h)
    assert r.status_code in (403,404)


def test_project_update_rejects_foreign_customer(client,auth_headers):
    client.post('/api/v1/auth/register',json={'email':'foreign@example.com','password':'ForeignPass123!','display_name':'Foreign'})
    token=client.post('/api/v1/auth/login',json={'email':'foreign@example.com','password':'ForeignPass123!'}).json()['access_token']
    foreign={'Authorization':f'Bearer {token}'}
    customer=client.post('/api/v1/customers',headers=foreign,json={'name':'Private fixture'}).json()['id']
    project=client.post('/api/v1/projects',headers=auth_headers,json={'title':'Owned'}).json()['id']
    assert client.put(f'/api/v1/projects/{project}',headers=auth_headers,json={'customer_id':customer}).status_code==400
    assert client.get(f'/api/v1/projects/{project}',headers=auth_headers).json()['customer_id'] is None
