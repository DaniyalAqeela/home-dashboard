from conftest import H, REMOTE


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json["ok"] is True and r.json["version"]


def test_setup_then_login(client):
    assert client.get("/api/auth/status").json == {"set": False, "loggedIn": False}
    assert client.post("/api/auth/setup", json={"password": "short"}, headers=H).status_code == 400
    assert client.post("/api/auth/setup", json={"password": "secret1"}, headers=H).status_code == 200
    assert client.get("/api/auth/status").json == {"set": True, "loggedIn": True}
    assert client.post("/api/auth/logout", headers=H).status_code == 200
    assert client.get("/api/auth/status").json["loggedIn"] is False
    assert client.post("/api/auth/login", json={"password": "nope123"}, headers=H).status_code == 401
    assert client.post("/api/auth/login", json={"password": "secret1"}, headers=H).status_code == 200
    assert client.get("/api/auth/status").json["loggedIn"] is True


def test_setup_only_once(admin):
    assert admin.post("/api/auth/setup", json={"password": "other123"}, headers=H).status_code == 409


def test_change_password_logs_out_other_sessions(admin, rt):
    from dashboard.web import create_app
    other = create_app(rt).test_client()
    assert other.post("/api/auth/login", json={"password": "secret1"}, headers=H).status_code == 200
    r = admin.post("/api/auth/password", json={"old": "secret1", "new": "secret2"}, headers=H)
    assert r.status_code == 200
    assert other.get("/api/config", environ_overrides=REMOTE).status_code == 401
    assert admin.get("/api/config", environ_overrides=REMOTE).status_code == 200


def test_api_requires_login(client):
    assert client.put("/api/config", json={}, headers=H, environ_overrides=REMOTE).status_code == 401
    assert client.get("/api/config", environ_overrides=REMOTE).status_code == 401


def test_mutation_requires_csrf_header(admin):
    assert admin.put("/api/config", json={}, environ_overrides=REMOTE).status_code == 403
    assert admin.put("/api/config", json={}, headers=H, environ_overrides=REMOTE).status_code == 200


def test_put_config_normalizes(admin, rt):
    r = admin.put("/api/config", json={"display": {"rotation": "90", "scale": "huge"}}, headers=H,
                  environ_overrides=REMOTE)
    assert r.status_code == 200
    assert r.json["display"]["rotation"] == 90 and r.json["display"]["scale"] == 1.0
    assert rt.config["display"]["rotation"] == 90


def test_schema(admin):
    s = admin.get("/api/schema", environ_overrides=REMOTE).json
    assert "clock" in s["widgets"] and s["common"][0]["key"] == "background"


def test_display_state_localhost_only(client):
    assert client.get("/api/display/state?since=0", environ_overrides=REMOTE).status_code == 403
    r = client.get("/api/display/state?since=0")
    assert r.status_code == 200
    body = r.json
    assert body["rev"] >= 0 and body["config"]["widgets"] and body["setup"]["needed"] is True
    assert set(body["widgets"]) == {w["id"] for w in body["config"]["widgets"]}


def test_screenshot_requires_login_and_marks_wanted(client, admin, rt):
    from dashboard.web import create_app
    anon = create_app(rt).test_client()
    assert anon.get("/api/screenshot", environ_overrides=REMOTE).status_code == 401
    assert rt.state.screenshot_wanted() is False
    r = admin.get("/api/screenshot", environ_overrides=REMOTE)
    assert r.status_code == 204
    assert rt.state.screenshot_wanted() is True


def test_screenshot_serves_last_good_image(admin, rt):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "JPEG")
    rt.screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    rt.screenshot_path.write_bytes(buf.getvalue())
    r = admin.get("/api/screenshot", environ_overrides=REMOTE)
    assert r.status_code == 200 and r.data == buf.getvalue()
    rt.screenshot_path.write_bytes(buf.getvalue()[:20])  # half-written file
    r = admin.get("/api/screenshot", environ_overrides=REMOTE)
    assert r.status_code == 200 and r.data == buf.getvalue()


def test_reset_file_clears_password(rt):
    rt.auth.set_password("secret1")
    (rt.boot_dir / "reset-password").write_text("")
    assert rt.auth.check_reset_file() is True
    assert rt.auth.is_set() is False
    assert not (rt.boot_dir / "reset-password").exists()
    assert rt.auth.check_reset_file() is False
