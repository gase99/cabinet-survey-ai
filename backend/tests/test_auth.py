def test_register_login_and_me(client, auth_headers):
    # Use auth_headers fixture which already registered
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"

def test_register_duplicate(client):
    payload = {"email": "dup@example.com", "password": "Password123", "display_name": "Dup"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 400

def test_login_invalid(client):
    r = client.post("/api/v1/auth/login", json={"email": "nouser@example.com", "password": "badpass123"})
    assert r.status_code == 401

def test_protected_without_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401

def test_update_profile(client, auth_headers):
    r = client.put("/api/v1/auth/me", headers=auth_headers, json={"display_name": "New Name"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "New Name"

def test_change_password(client):
    email="changepass@example.com"
    pw="OldPassword123"
    new_pw="NewPassword123"
    client.post("/api/v1/auth/register", json={"email": email, "password": pw, "display_name":"Changer"})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r2 = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": pw, "new_password": new_pw})
    assert r2.status_code == 200
    # login with new
    r3 = client.post("/api/v1/auth/login", json={"email": email, "password": new_pw})
    assert r3.status_code == 200
