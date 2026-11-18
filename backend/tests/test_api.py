import io

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
FAKE_IMAGE = b"MZ this is really an exe" + b"\x00" * 64


def _report(client, headers, area_id=1, type_="flood", files=None, **extra):
    data = {"area_id": str(area_id), "type": type_, "description": "road under water", **extra}
    return client.post("/api/reports", data=data, files=files, headers=headers)


# ---------- auth ----------
def test_register_login_me(client, make_user):
    headers, user = make_user()
    assert user["role"] == "citizen"
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == user["email"]


def test_duplicate_email_rejected(client, make_user):
    _, user = make_user()
    r = client.post("/api/auth/register", json={"name": "Dup", "email": user["email"], "password": "Password123"})
    assert r.status_code == 409


def test_wrong_password(client, make_user):
    _, user = make_user()
    r = client.post("/api/auth/login", json={"email": user["email"], "password": "nope"})
    assert r.status_code == 401


def test_cannot_register_as_admin(client):
    r = client.post("/api/auth/register", json={
        "name": "Hacker", "email": "hax@test.lk", "password": "Password123", "role": "admin"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "citizen"


def test_invalid_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ---------- areas ----------
def test_areas_seeded(client):
    areas = client.get("/api/areas").json()
    assert len(areas) == 25
    assert {"Colombo", "Kandy", "Ratnapura"} <= {a["name"] for a in areas}


def test_unknown_area_404(client):
    assert client.get("/api/areas/9999").status_code == 404


# ---------- reports ----------
def test_report_requires_login(client):
    assert _report(client, {}).status_code == 401


def test_report_with_photo(client, make_user):
    headers, _ = make_user()
    r = _report(client, headers, files={"photo": ("a.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending" and body["photo_url"].startswith("/uploads/")
    assert client.get(body["photo_url"]).status_code == 200


def test_fake_image_rejected_even_with_png_content_type(client, make_user):
    headers, _ = make_user()
    r = _report(client, headers, files={"photo": ("evil.png", io.BytesIO(FAKE_IMAGE), "image/png")})
    assert r.status_code == 415


def test_oversized_photo_rejected(client, make_user):
    headers, _ = make_user()
    big = PNG + b"\x00" * (6 * 1024 * 1024)
    r = _report(client, headers, files={"photo": ("big.png", io.BytesIO(big), "image/png")})
    assert r.status_code == 413


def test_invalid_type_and_area(client, make_user):
    headers, _ = make_user()
    assert _report(client, headers, type_="earthquake").status_code == 422
    assert _report(client, headers, area_id=9999).status_code == 404


def test_public_sees_only_verified(client, make_user, admin_headers):
    headers, _ = make_user()
    rid = _report(client, headers, area_id=2).json()["id"]
    public_ids = [r["id"] for r in client.get("/api/reports").json()]
    assert rid not in public_ids
    assert client.post(f"/api/reports/{rid}/verify", headers=admin_headers).status_code == 200
    public_ids = [r["id"] for r in client.get("/api/reports").json()]
    assert rid in public_ids


def test_citizen_cannot_moderate(client, make_user):
    headers, _ = make_user()
    rid = _report(client, headers).json()["id"]
    assert client.post(f"/api/reports/{rid}/verify", headers=headers).status_code == 403
    assert client.post(f"/api/reports/{rid}/verify").status_code == 401


def test_admin_can_reject(client, make_user, admin_headers):
    headers, _ = make_user()
    rid = _report(client, headers).json()["id"]
    r = client.post(f"/api/reports/{rid}/reject", headers=admin_headers)
    assert r.json()["status"] == "rejected"


def test_auto_verify_needs_three_distinct_users(client, make_user):
    area = 3
    results = []
    for _ in range(3):
        headers, _ = make_user()
        results.append(_report(client, headers, area_id=area, type_="landslide").json())
    assert results[0]["status"] == "pending"
    mine = client.get("/api/reports", params={"area_id": area}).json()  # public = verified only
    assert sum(1 for r in mine if r["type"] == "landslide" and r["auto_verified"]) == 3


def test_same_user_spam_does_not_auto_verify(client, make_user):
    headers, _ = make_user()
    for _ in range(4):
        r = _report(client, headers, area_id=4, type_="flood")
    assert r.json()["status"] == "pending"


# ---------- subscriptions & alerts ----------
def test_subscription_validation(client, make_user):
    headers, _ = make_user()
    bad = client.post("/api/subscriptions", headers=headers,
                      json={"area_id": 1, "channel": "sms", "contact": "abc"})
    assert bad.status_code == 422
    ok = client.post("/api/subscriptions", headers=headers,
                     json={"area_id": 1, "channel": "sms", "contact": "+94771234567", "language": "si"})
    assert ok.status_code == 201
    assert len(client.get("/api/subscriptions", headers=headers).json()) == 1


def test_cannot_delete_someone_elses_subscription(client, make_user):
    h1, _ = make_user()
    h2, _ = make_user()
    sub = client.post("/api/subscriptions", headers=h1,
                      json={"area_id": 1, "channel": "email", "contact": "a@b.lk"}).json()
    assert client.delete(f"/api/subscriptions/{sub['id']}", headers=h2).status_code == 404
    assert client.delete(f"/api/subscriptions/{sub['id']}", headers=h1).status_code == 204


def test_same_contact_two_users_each_keep_their_own_subscription(client, make_user):
    h1, _ = make_user()
    h2, _ = make_user()
    body = {"area_id": 5, "channel": "sms", "contact": "+94770000001", "language": "si"}
    s1 = client.post("/api/subscriptions", headers=h1, json=body).json()
    s2 = client.post("/api/subscriptions", headers=h2, json={**body, "language": "en"}).json()
    assert s1["id"] != s2["id"]
    assert client.get("/api/subscriptions", headers=h1).json()[0]["language"] == "si"  # not overwritten by user 2
    assert len(client.get("/api/subscriptions", headers=h2).json()) == 1


def test_duplicate_contact_notified_once(client, make_user, admin_headers, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.notify", lambda ch, to, text: sent.append(to))
    h1, _ = make_user()
    h2, _ = make_user()
    for h in (h1, h2):
        client.post("/api/subscriptions", headers=h, json={"area_id": 6, "channel": "sms", "contact": "+94770000002"})
    r = client.post("/api/admin/broadcast", headers=admin_headers, json={"area_id": 6, "level": "High"})
    assert sent.count("+94770000002") == 1 and r.json()["recipients"] >= 1


def test_subscription_limit_per_user(client, make_user):
    headers, _ = make_user()
    codes = [client.post("/api/subscriptions", headers=headers,
                         json={"area_id": (i % 25) + 1, "channel": "email", "contact": f"x{i}@test.lk"}).status_code
             for i in range(12)]
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429]


def test_refresh_requires_admin(client, make_user):
    headers, _ = make_user()
    assert client.post("/api/admin/refresh").status_code == 401
    assert client.post("/api/admin/refresh", headers=headers).status_code == 403


def test_refresh_updates_risk_and_notifies(client, admin_headers, make_user, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.notify", lambda ch, to, text: sent.append((ch, to, text)))
    monkeypatch.setattr("app.services.fetch_rainfall_bulk", lambda coords: [
        __import__("app.weather", fromlist=["Rainfall"]).Rainfall(150, 300, 100, "mock") for _ in coords])

    headers, _ = make_user()
    client.post("/api/subscriptions", headers=headers,
                json={"area_id": 24, "channel": "sms", "contact": "+94711111111", "language": "ta"})

    result = client.post("/api/admin/refresh", headers=admin_headers).json()
    assert len(result) == 25 and all(r["level"] != "Low" for r in result)
    assert any(to == "+94711111111" for _, to, _ in sent)
    # Tamil subscriber got a Tamil message
    assert any(to == "+94711111111" and ("எச்சரிக்கை" in text or "அவசரம்" in text) for _, to, text in sent)

    areas = client.get("/api/areas").json()
    assert areas[0]["risk_score"] >= areas[-1]["risk_score"]  # sorted by risk
    assert client.get("/api/alerts").json()


def test_history_for_charts(client, admin_headers):
    client.post("/api/admin/refresh", headers=admin_headers)
    rows = client.get("/api/areas/24/history", params={"hours": 24}).json()
    assert rows and {"rainfall_24h", "rainfall_72h", "forecast_24h", "recorded_at"} <= set(rows[0])


def test_manual_broadcast(client, admin_headers):
    r = client.post("/api/admin/broadcast", headers=admin_headers,
                    json={"area_id": 1, "level": "Critical", "message": "Evacuate Kelani river banks"})
    assert r.status_code == 201 and r.json()["manual"] is True and r.json()["area_name"] == "Colombo"


# ---------- safe zones ----------
def test_nearest_safe_zone(client):
    zones = client.get("/api/safe-zones/nearest", params={"lat": 7.2906, "lng": 80.6337, "limit": 2}).json()
    assert len(zones) == 2 and zones[0]["name"].startswith("Kandy")
    assert zones[0]["distance_km"] <= zones[1]["distance_km"]


def test_nearest_rejects_coordinates_outside_sri_lanka(client):
    assert client.get("/api/safe-zones/nearest", params={"lat": 51.5, "lng": -0.1}).status_code == 422


def test_admin_adds_and_deletes_safe_zone(client, admin_headers, make_user):
    payload = {"area_id": 1, "name": "Royal College Shelter", "kind": "school", "lat": 6.91, "lng": 79.87, "capacity": 400}
    citizen, _ = make_user()
    assert client.post("/api/safe-zones", json=payload, headers=citizen).status_code == 403
    zone = client.post("/api/safe-zones", json=payload, headers=admin_headers)
    assert zone.status_code == 201 and zone.json()["is_sample"] is False
    assert client.delete(f"/api/safe-zones/{zone.json()['id']}", headers=admin_headers).status_code == 204


def test_public_stats(client):
    s = client.get("/api/stats").json()
    assert s["areas"] == 25 and set(s["by_level"]) == {"Low", "Medium", "High", "Critical"}
