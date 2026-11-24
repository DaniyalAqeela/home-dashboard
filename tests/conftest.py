from pathlib import Path

import pytest

from dashboard import features
from dashboard.runtime import Runtime
from dashboard.web import create_app

APP_DIR = Path(__file__).resolve().parents[1] / "app"
H = {"X-Dashboard": "1"}
REMOTE = {"REMOTE_ADDR": "10.0.0.5"}


@pytest.fixture
def rt(tmp_path):
    (tmp_path / "boot").mkdir()
    r = Runtime(tmp_path / "data", tmp_path / "boot", APP_DIR, dev=True)
    features.install(r)
    return r


@pytest.fixture
def client(rt):
    app = create_app(rt)
    features.install_routes(app, rt)
    app.testing = True
    return app.test_client()


@pytest.fixture
def admin(client):
    """A client that has set the password and is logged in (from a LAN address)."""
    r = client.post("/api/auth/setup", json={"password": "secret1"}, headers=H, environ_overrides=REMOTE)
    assert r.status_code == 200
    return client
