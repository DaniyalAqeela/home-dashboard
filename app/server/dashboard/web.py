"""HTTP API for the settings site and the display."""
import functools
import io
from datetime import timedelta

from flask import Flask, abort, jsonify, request, send_from_directory, session

from . import config as config_mod

MUTATING = {"POST", "PUT", "DELETE", "PATCH"}


def is_local() -> bool:
    return request.remote_addr in ("127.0.0.1", "::1")


def err(msg, code):
    return jsonify({"error": msg}), code


def create_app(rt) -> Flask:
    web_dir = rt.app_dir / "web"
    app = Flask(__name__, static_folder=None)
    app.secret_key = rt.auth.secret_key()
    app.config.update(SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_HTTPONLY=True,
                      PERMANENT_SESSION_LIFETIME=timedelta(days=30), MAX_CONTENT_LENGTH=300 * 1024 * 1024)
    app.rt = rt
    last_good = {"shot": None}

    def logged_in() -> bool:
        return bool(rt.auth.is_set() and session.get("epoch") and session.get("epoch") == rt.auth.epoch())

    def login_required(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not logged_in():
                return err("Not logged in", 401)
            return fn(*a, **kw)
        return wrapper

    def local_only(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not is_local():
                abort(403)
            return fn(*a, **kw)
        return wrapper

    def local_or_login(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not (is_local() or logged_in()):
                return err("Not logged in", 401)
            return fn(*a, **kw)
        return wrapper

    app.login_required, app.local_only, app.local_or_login = login_required, local_only, local_or_login

    @app.before_request
    def csrf_guard():
        if request.method in MUTATING and request.path.startswith("/api/") and request.headers.get("X-Dashboard") != "1":
            return err("Missing X-Dashboard header", 403)

    def start_session():
        session.clear()
        session.permanent = True
        session["epoch"] = rt.auth.epoch()

    # --- pages -------------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(web_dir, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(web_dir, name)

    @app.get("/api/health")
    def health():
        return jsonify(ok=True, version=rt.version)

    # --- auth --------------------------------------------------------------
    @app.get("/api/auth/status")
    def auth_status():
        return jsonify({"set": rt.auth.is_set(), "loggedIn": logged_in()})

    @app.post("/api/auth/setup")
    def auth_setup():
        if rt.auth.is_set():
            return err("Password already set", 409)
        try:
            rt.auth.set_password((request.get_json(silent=True) or {}).get("password"))
        except ValueError as e:
            return err(str(e), 400)
        start_session()
        rt.state.bump()  # the screen leaves the setup screen
        return jsonify(ok=True)

    @app.post("/api/auth/login")
    def auth_login():
        import time
        if not rt.auth.verify((request.get_json(silent=True) or {}).get("password")):
            time.sleep(1)  # slow down guessing
            return err("Wrong password", 401)
        start_session()
        return jsonify(ok=True)

    @app.post("/api/auth/logout")
    def auth_logout():
        session.clear()
        return jsonify(ok=True)

    @app.post("/api/auth/password")
    @login_required
    def auth_password():
        body = request.get_json(silent=True) or {}
        if not rt.auth.verify(body.get("old")):
            return err("Current password is wrong", 401)
        try:
            rt.auth.set_password(body.get("new"))
        except ValueError as e:
            return err(str(e), 400)
        start_session()
        return jsonify(ok=True)

    # --- config ------------------------------------------------------------
    @app.get("/api/config")
    @login_required
    def get_config():
        return jsonify(rt.config)

    @app.put("/api/config")
    @login_required
    def put_config():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err("Expected a JSON object", 400)
        return jsonify(rt.update_config(body))

    @app.get("/api/schema")
    @login_required
    def schema():
        return jsonify(widgets=config_mod.WIDGET_TYPES, common=config_mod.COMMON_STYLE, sections=config_mod.SECTIONS)

    # --- display -----------------------------------------------------------
    @app.get("/api/display/state")
    @local_only
    def display_state():
        try:
            since = int(request.args.get("since", -1))
        except ValueError:
            since = -1
        rt.state.wait(since, 10.0)
        return jsonify(rt.build_display_state())

    @app.get("/api/screenshot")
    @login_required
    def screenshot():
        from PIL import Image
        rt.state.want_screenshot()
        try:
            data = rt.screenshot_path.read_bytes()
            Image.open(io.BytesIO(data)).load()  # skip a half-written file
            last_good["shot"] = data
        except Exception:
            data = last_good["shot"]
        if not data:
            return "", 204
        return app.response_class(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    return app
