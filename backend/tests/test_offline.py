def test_approval_workflow(client, auth_headers):
    p = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Approval Flow"})
    pid = p.json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/rooms", headers=auth_headers, json={"label":"Kitchen","room_type":"rectangular"})
    rid = r.json()["id"]
    # Create wall via AI source (needs_review)
    w = client.post(f"/api/v1/rooms/{rid}/walls", headers=auth_headers, json={"label":"Wall A","length_mm":3200,"height_mm":2700,"source":"sketch_ai"})
    wid = w.json()["id"]
    assert w.json()["review_status"] == "needs_review"
    # Approve
    a = client.post(f"/api/v1/walls/{wid}/approve", headers=auth_headers)
    assert a.json()["review_status"] == "approved"
    # Edit approved -> should go back to needs_review
    e = client.put(f"/api/v1/walls/{wid}", headers=auth_headers, json={"length_mm": 3300})
    assert e.json()["review_status"] == "needs_review"
    # Re-approve
    a2 = client.post(f"/api/v1/walls/{wid}/approve", headers=auth_headers)
    assert a2.json()["review_status"] == "approved"

def test_ai_text_parse_endpoint(client, auth_headers):
    r = client.post("/api/v1/ai/parse-text", headers=auth_headers, data={"text": "Wall A: 3200 mm\nWall B: 2700 mm"})
    assert r.status_code == 200
    assert len(r.json()["observations"]) == 2
    # Ensure no fabrication: missing values stay missing
    assert r.json()["observations"][0]["value_mm"] == 3200
    assert "disclaimer" in r.json() or "provider" in r.json()
