"""Wires each feature (widgets data, background jobs, config side effects and
HTTP routes) into the runtime and the Flask app."""
import functools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import prayer


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
    import time
    now = time.time()
    sig = [datetime.fromtimestamp(now, _tz(rt)).date().isoformat()]
    for w in rt.config["widgets"]:
        if w["type"] == "shalat":
            sig.append(shalat_data(rt, w, now).get("next", {}).get("ts"))
    return tuple(sig)


def install(rt) -> None:
    rt.providers["shalat"] = lambda w, now: shalat_data(rt, w, now)
    rt.providers["clock"] = lambda w, now: clock_data(rt, w, now)
    last = {"sig": None}

    def tick_day():
        sig = _day_signature(rt)
        if sig != last["sig"]:
            if last["sig"] is not None:
                rt.state.bump()
            last["sig"] = sig

    rt.every(20, tick_day)


def install_routes(app, rt) -> None:
    pass
