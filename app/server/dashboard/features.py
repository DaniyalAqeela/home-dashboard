"""Wires each feature (widgets data, background jobs, config side effects and
HTTP routes) into the runtime and the Flask app."""
import functools
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import abort, jsonify, request, send_file, send_from_directory

import logging
from pathlib import Path

from . import backup, drive, feeds, fsutil, photos, prayer, system, updates, weather

log = logging.getLogger("dashboard")

# shortcut: fixed 1920px long side (Pi 3 tops out at 1080p); derive from the display mode if 4K panels matter.
PHOTO_LONG_SIDE = 1920


def _tz(rt):
    try:
        return ZoneInfo(rt.config["location"]["timezone"])
    except Exception:
        return ZoneInfo("UTC")


@functools.lru_cache(maxsize=64)
def _times_cached(lat, lon, tz, day, method, madhab, adjust_items, fajr, isha):
    return prayer.prayer_times(lat, lon, tz, day, method, madhab, dict(adjust_items), fajr, isha)


def shalat_data(rt, widget, now: float) -> dict:
    loc = rt.config["location"]
    if loc["lat"] is None or loc["lon"] is None:
        return {"error": "Set your location in Settings → Location"}
    o = widget["options"]
    tz = loc["timezone"]
    today = datetime.fromtimestamp(now, _tz(rt)).date()
    adjust = tuple((k, o["adj" + k.title()]) for k in ("fajr", "dhuhr", "asr", "maghrib", "isha"))
    args = (loc["lat"], loc["lon"], tz)
    rest = (o["method"], o["madhab"], adjust, o["fajrAngle"], o["ishaAngle"])
    t_today = _times_cached(*args, today, *rest)
    t_tomorrow = _times_cached(*args, today + timedelta(days=1), *rest)
    hidden = {"imsak"} if not o["showImsak"] else set()
    if not o["showSunrise"]:
        hidden.add("sunrise")
    return {"times": [t for t in t_today if t["key"] not in hidden],
            "next": prayer.next_prayer(t_today, t_tomorrow, int(now * 1000))}


def clock_data(rt, widget, now: float) -> dict:
    o = widget["options"]
    if not o["hijri"]:
        return {}
    today = datetime.fromtimestamp(now, _tz(rt)).date()
    return {"hijri": prayer.hijri(today, o["hijriAdjust"])}


def _day_signature(rt):
    """Changes when the date or any widget's 'next prayer' changes, so the screen updates."""
    now = time.time()
    sig = [datetime.fromtimestamp(now, _tz(rt)).date().isoformat()]
    for w in rt.config["widgets"]:
        if w["type"] == "shalat":
            sig.append(shalat_data(rt, w, now).get("next", {}).get("ts"))
    return tuple(sig)


def _install_weather(rt):
    path = rt.data_dir / "cache" / "weather.json"
    rt.weather = fsutil.read_json(path)
    rt.weather_error = None

    def refresh_weather(http=None):
        loc = rt.config["location"]
        if loc["lat"] is None or loc["lon"] is None:
            return
        try:
            data = weather.fetch_forecast(loc["lat"], loc["lon"], http)
        except Exception as e:  # offline etc.: keep the last forecast
            rt.weather_error = str(e)
            return
        data.update(lat=loc["lat"], lon=loc["lon"])
        rt.weather, rt.weather_error = data, None
        fsutil.atomic_write_json(path, data)
        rt.state.bump()

    def weather_data(w, now):
        loc = rt.config["location"]
        if loc["lat"] is None or loc["lon"] is None:
            return {"error": "Set your location in Settings → Location"}
        if not rt.weather:
            return {"error": "Loading weather…"}
        return {**rt.weather, "place": loc["name"]}

    rt.refresh_weather = refresh_weather
    rt.providers["weather"] = weather_data
    job = rt.every(1800, refresh_weather, first_delay=3, background=True)

    def on_location(old, new):
        if (old["location"]["lat"], old["location"]["lon"]) != (new["location"]["lat"], new["location"]["lon"]):
            rt.trigger(job)
    rt.config_hooks.append(on_location)


def _feed_urls(cfg):
    return [u for w in cfg["widgets"] if w["type"] == "news" for u in w["options"]["feeds"]]


def _install_news(rt):
    rt.feeds = feeds.FeedCache(rt.data_dir)
    rt.news_pos = {}  # widget id -> [index, next change time]

    def refresh_feeds():
        rt.feeds.refresh(_feed_urls(rt.config))
        rt.state.bump()

    def news_data(w, now):
        items = rt.feeds.items(w["options"]["feeds"], 30)
        if not items:
            errs = [rt.feeds.errors[u] for u in w["options"]["feeds"] if u in rt.feeds.errors]
            return {"items": [], "index": 0, "error": "Couldn't load news" if errs else "Loading news…"}
        n = w["options"]["descLength"]
        pos = rt.news_pos.get(w["id"], [0, 0])
        return {"items": [{**i, "summary": feeds.clean(i["summary"], n) if n else ""} for i in items],
                "index": pos[0] % len(items)}

    rt.refresh_feeds = refresh_feeds
    rt.providers["news"] = news_data
    job = rt.every(900, refresh_feeds, first_delay=2, background=True)
    rt.config_hooks.append(lambda old, new: _feed_urls(old) != _feed_urls(new) and rt.trigger(job))


def _rotate_news(rt, now) -> bool:
    changed = False
    for w in rt.config["widgets"]:
        if w["type"] != "news" or w["options"]["layout"] != "rotate":
            continue
        interval = w["options"]["interval"]
        pos = rt.news_pos.setdefault(w["id"], [0, now + interval])
        if now >= pos[1]:
            if len(rt.feeds.items(w["options"]["feeds"], 30)) > 1:
                pos[0] += 1
                changed = True
            pos[1] = now + interval
    return changed


def _install_photos(rt):
    rt.photos = photos.PhotoLibrary(rt.data_dir)
    rt.slideshow = photos.Slideshow()
    rt.drive = drive.DriveSync(rt.photos.drive_dir)
    rt.drive_status = {"count": len(rt.photos.all("drive")), "lastSync": None, "error": None,
                       "added": 0, "removed": 0}

    def sync_drive():
        p = rt.config["photos"]
        if not p["driveUrl"]:
            rt.drive_status.update(error=None, count=len(rt.photos.all("drive")))
            return
        r = rt.drive.sync(p["driveUrl"], p["apiKey"], PHOTO_LONG_SIDE)
        rt.drive_status.update(r, lastSync=time.time())

    def photos_data(w, now):
        cur = rt.slideshow.current(w["id"])
        if cur is None:
            return {"photo": None, "error": "No photos yet. Add a Google Drive link or upload photos in Settings."}
        source = "drive" if cur.parent == rt.photos.drive_dir else "uploads"
        return {"photo": f"/photo/{source}/{cur.name}"}

    rt.providers["photos"] = photos_data
    rt.drive_job = rt.every(lambda: rt.config["photos"]["syncMinutes"] * 60, sync_drive, first_delay=5,
                            background=True)

    def on_drive_change(old, new):
        if (old["photos"]["driveUrl"], old["photos"]["apiKey"]) != (new["photos"]["driveUrl"], new["photos"]["apiKey"]):
            rt.trigger(rt.drive_job)
    rt.config_hooks.append(on_drive_change)


SYSTEM_SETTINGS = ((("display", "mode"), "set_display_mode"), (("location", "timezone"), "set_timezone"),
                   (("location", "country"), "set_country"))


def _install_system(rt):
    rt.screen_off = False

    def screen_tick():
        sch = rt.config["display"]["schedule"]
        now = datetime.now(_tz(rt)).time()
        want_off = bool(sch["enabled"]) and system.in_off_window(now, sch["off"], sch["on"])
        if want_off != rt.screen_off:
            rt.system.screen_power(not want_off)
            rt.screen_off = want_off

    rt.screen_tick = screen_tick
    job = rt.every(30, screen_tick, first_delay=10)

    def on_change(old, new):
        for (section, key), method in SYSTEM_SETTINGS:
            value = new[section][key]
            if value != old[section][key] and value:
                try:
                    getattr(rt.system, method)(value)
                except Exception:
                    log.exception("%s(%r) failed", method, value)
        if old["display"]["schedule"] != new["display"]["schedule"]:
            rt.trigger(job)
    rt.config_hooks.append(on_change)


FACTORY_DIR = Path("/usr/share/dashboard/factory")
BIG_UPLOAD = 2200 * 1024 * 1024  # backups with many photos


def _install_updates(rt):
    rt.app_root = rt.data_dir / "app"
    rt.factory_dir = None if rt.dev else FACTORY_DIR
    rt.latest = {"latest": None, "checked": None, "error": None}

    def check_github():
        try:
            rt.latest.update(latest=updates.github_latest(rt.config["updates"]["repo"]), error=None)
        except Exception as e:
            rt.latest["error"] = str(e)
        rt.latest["checked"] = time.time()

    rt.check_github = check_github
    job = rt.every(86400, check_github, first_delay=60, background=True)
    rt.config_hooks.append(lambda old, new: old["updates"] != new["updates"] and rt.trigger(job))
    # app-launcher counts boots in `attempts`; staying up 30 s means this release works
    rt.every(10 ** 9, lambda: updates.mark_healthy(rt.app_root), first_delay=30)


def install(rt) -> None:
    rt.providers["shalat"] = lambda w, now: shalat_data(rt, w, now)
    rt.providers["clock"] = lambda w, now: clock_data(rt, w, now)
    _install_weather(rt)
    _install_news(rt)
    _install_photos(rt)
    _install_system(rt)
    _install_updates(rt)

    def rotate_tick():
        now = time.time()
        news = _rotate_news(rt, now)
        slides = rt.slideshow.tick(rt.config["widgets"], rt.photos, now)
        if news or slides:
            rt.state.bump()

    rt.rotate_tick = rotate_tick
    rt.every(1, rotate_tick)
    last = {"sig": None}

    def tick_day():
        sig = _day_signature(rt)
        if sig != last["sig"]:
            if last["sig"] is not None:
                rt.state.bump()
            last["sig"] = sig

    rt.every(20, tick_day)


def install_routes(app, rt) -> None:
    @app.get("/api/location/search")
    @app.login_required
    def location_search():
        try:
            return jsonify(weather.search_places(request.args.get("q", "")))
        except Exception as e:
            return jsonify(error=f"Search failed: {e}"), 502

    @app.get("/api/photos")
    @app.login_required
    def photos_status():
        progress = rt.drive.progress
        return jsonify(drive={**rt.drive_status, "progress": list(progress) if progress else None},
                       uploads=rt.photos.uploads())

    @app.post("/api/photos/sync")
    @app.login_required
    def photos_sync():
        rt.trigger(rt.drive_job)
        return jsonify(ok=True)

    @app.post("/api/photos/upload")
    @app.login_required
    def photos_upload():
        added, errors = [], []
        for f in request.files.getlist("files"):
            try:
                added.append(rt.photos.add_upload(f.filename or "photo", f.read(photos.MAX_UPLOAD + 1),
                                                  PHOTO_LONG_SIDE))
            except (ValueError, OSError) as e:
                errors.append({"name": f.filename, "error": str(e)})
        return jsonify(added=added, errors=errors)

    @app.delete("/api/photos/uploads/<name>")
    @app.login_required
    def photos_delete(name):
        if not rt.photos.delete_upload(name):
            return jsonify(error="No such photo"), 404
        return jsonify(ok=True)

    @app.get("/photo/<source>/<name>")
    @app.local_or_login
    def photo_file(source, name):
        dirs = {"drive": rt.photos.drive_dir, "uploads": rt.photos.upload_dir}
        if source not in dirs or name.startswith("."):
            abort(404)
        return send_from_directory(dirs[source], name, max_age=86400)

    def body():
        return request.get_json(silent=True) or {}

    @app.get("/api/system/info")
    @app.login_required
    def system_info():
        return jsonify(version=rt.version, urls=rt.system.urls(), modes=rt.system.display_modes(),
                       clockSynced=rt.system.clock_synced(), freeSpace=rt.system.free_space(),
                       screenOff=rt.screen_off, uptime=time.monotonic() - rt.started)

    @app.get("/api/wifi/scan")
    @app.login_required
    def wifi_scan():
        try:
            return jsonify(networks=rt.system.wifi_scan(), status=rt.system.wifi_status())
        except Exception as e:
            return jsonify(error=f"Wi-Fi scan failed: {e}"), 502

    @app.post("/api/wifi/connect")
    @app.login_required
    def wifi_connect():
        b = body()
        try:
            rt.system.wifi_connect(str(b.get("ssid", "")), str(b.get("password", "")))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            return jsonify(error=f"Couldn't save Wi-Fi: {e}"), 502
        return jsonify(ok=True)

    @app.post("/api/wifi/forget")
    @app.login_required
    def wifi_forget():
        rt.system.wifi_forget(str(body().get("ssid", "")))
        return jsonify(ok=True)

    @app.post("/api/system/restart")
    @app.login_required
    def system_restart():
        rt.system.restart_app()
        return jsonify(ok=True)

    @app.post("/api/system/reboot")
    @app.login_required
    def system_reboot():
        rt.system.reboot()
        return jsonify(ok=True)

    @app.get("/api/system/logs")
    @app.login_required
    def system_logs():
        try:
            n = int(request.args.get("lines", 200))
        except ValueError:
            n = 200
        return jsonify(text=rt.system.logs(n))

    def install_and_restart(path):
        try:
            version = updates.install_bundle(path, rt.app_root, factory=rt.factory_dir)
        except updates.UpdateError as e:
            return jsonify(error=str(e)), 400
        finally:
            Path(path).unlink(missing_ok=True)
        rt.system.restart_app()
        return jsonify(ok=True, version=version)

    @app.get("/api/update/status")
    @app.login_required
    def update_status():
        if request.args.get("check"):
            rt.check_github()
        cur = updates.resolve_release(rt.app_root, "current")
        prev = updates.resolve_release(rt.app_root, "previous")
        latest = rt.latest["latest"]
        return jsonify(version=rt.version, installed=updates._version_of(cur), previous=updates._version_of(prev),
                       latest=latest, newer=bool(latest and latest["asset_url"]
                                                 and updates.is_newer(latest["version"], rt.version)),
                       checked=rt.latest["checked"], error=rt.latest["error"])

    @app.post("/api/update/upload")
    @app.login_required
    def update_upload():
        f = request.files.get("bundle")
        if not f:
            return jsonify(error="Choose an update file first."), 400
        path = rt.data_dir / "cache" / "update-upload.tar.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        f.save(path)
        return install_and_restart(path)

    @app.post("/api/update/github")
    @app.login_required
    def update_github():
        rt.check_github()
        latest = rt.latest["latest"]
        if not latest or not latest["asset_url"]:
            return jsonify(error=rt.latest["error"] or "No app update found in the GitHub releases."), 404
        path = rt.data_dir / "cache" / "update-github.tar.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            updates.download(latest["asset_url"], path)
        except updates.UpdateError as e:
            return jsonify(error=str(e)), 502
        return install_and_restart(path)

    @app.post("/api/update/rollback")
    @app.login_required
    def update_rollback():
        try:
            version = updates.rollback(rt.app_root)
        except updates.UpdateError as e:
            return jsonify(error=str(e)), 409
        rt.system.restart_app()
        return jsonify(ok=True, version=version)

    @app.get("/api/backup")
    @app.login_required
    def backup_download():
        out = rt.data_dir / "cache" / "backup.zip"
        backup.make_backup(rt.data_dir, out)
        r = send_file(out, as_attachment=True, mimetype="application/zip",
                      download_name=f"dashboard-backup-{datetime.now(_tz(rt)).date().isoformat()}.zip")
        r.call_on_close(lambda: out.unlink(missing_ok=True))
        return r

    @app.post("/api/restore")
    @app.login_required
    def backup_restore():
        request.max_content_length = BIG_UPLOAD
        f = request.files.get("backup")
        if not f:
            return jsonify(error="Choose a backup file first."), 400
        try:
            cfg = backup.restore_backup(f.stream, rt.data_dir)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        rt.update_config(cfg)
        return jsonify(ok=True)
