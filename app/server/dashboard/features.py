"""Wires each feature (widgets data, background jobs, config side effects and
HTTP routes) into the runtime and the Flask app."""
import functools
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify, request

from . import feeds, fsutil, prayer, weather


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
    job = rt.every(1800, refresh_weather, first_delay=3)

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
    job = rt.every(900, refresh_feeds, first_delay=2)
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


def install(rt) -> None:
    rt.providers["shalat"] = lambda w, now: shalat_data(rt, w, now)
    rt.providers["clock"] = lambda w, now: clock_data(rt, w, now)
    _install_weather(rt)
    _install_news(rt)

    def rotate_tick():
        if _rotate_news(rt, time.time()):
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
