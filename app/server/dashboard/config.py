"""The dashboard configuration model.

One spec (field lists below) drives both normalize() and the settings UI forms
(/api/schema), so the two can never disagree. normalize() never raises: any
input, however broken, becomes a config the display can draw."""
import math
import re
import uuid
from pathlib import Path

from . import fsutil

COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")

FONTS = [["", "Theme default"], ["Inter", "Inter"], ["Roboto Slab", "Roboto Slab"],
         ["Noto Naskh Arabic", "Noto Naskh Arabic"], ["DejaVu Sans", "DejaVu Sans"]]


def F(key, label, type, default, **kw):
    return {"key": key, "label": label, "type": type, "default": default, **kw}


COMMON_STYLE = [
    F("background", "Background", "color", "#00000066"),
    F("radius", "Corner radius", "number", 16, min=0, max=200),
    F("padding", "Padding", "number", 16, min=0, max=200),
    F("font", "Font", "select", "", choices=FONTS),
    F("fontSize", "Font size", "number", 32, min=8, max=400),
    F("color", "Text colour", "color", ""),
    F("align", "Alignment", "select", "left",
      choices=[["left", "Left"], ["center", "Centre"], ["right", "Right"]]),
    F("shadow", "Text shadow", "bool", False),
]

PRAYER_METHODS = [
    ["mwl", "Muslim World League"], ["isna", "ISNA (North America)"], ["egypt", "Egyptian General Authority"],
    ["ummalqura", "Umm al-Qura (Makkah)"], ["karachi", "Karachi"],
    ["singapore", "Singapore / Kemenag / JAKIM"],
    ["dubai", "Dubai / Gulf"], ["kuwait", "Kuwait"], ["qatar", "Qatar"],
    ["moonsighting", "Moonsighting Committee"], ["custom", "Custom angles"],
]

WIDGET_TYPES = {
    "photos": {"label": "Photos", "style": {"background": "#00000000", "radius": 0, "padding": 0}, "options": [
        F("interval", "Seconds per photo", "number", 15, min=3, max=3600),
        F("order", "Order", "select", "shuffle",
          choices=[["shuffle", "Shuffle"], ["name", "By name"], ["newest", "Newest first"]]),
        F("fade", "Crossfade (seconds)", "number", 1.5, min=0, max=10, step=0.1),
        F("fit", "Fit", "select", "cover", choices=[["cover", "Fill (crop)"], ["contain", "Whole photo"]]),
        F("fill", "Fill colour (whole photo)", "color", "#000000FF"),
        F("source", "Photos from", "select", "both",
          choices=[["both", "Drive and uploads"], ["drive", "Google Drive"], ["uploads", "Uploads"]]),
    ]},
    "clock": {"label": "Clock", "style": {"fontSize": 96, "align": "center"}, "options": [
        F("hour24", "24-hour clock", "bool", True),
        F("seconds", "Show seconds", "bool", False),
        F("showDate", "Show date", "bool", True),
        F("dateFormat", "Date format", "select", "dddd d MMMM yyyy", choices=[
            ["dddd d MMMM yyyy", "Monday 1 January 2027"], ["ddd d MMM yyyy", "Mon 1 Jan 2027"],
            ["d MMMM yyyy", "1 January 2027"], ["dd/MM/yyyy", "01/01/2027"], ["MM/dd/yyyy", "01/31/2027"]]),
        F("hijri", "Show Hijri date", "bool", True),
        F("hijriAdjust", "Hijri adjustment (days)", "number", 0, min=-2, max=2),
        F("hijriScript", "Hijri month names", "select", "latin", choices=[["latin", "Latin"], ["arabic", "Arabic"]]),
    ]},
    "news": {"label": "News", "style": {"fontSize": 30}, "options": [
        F("feeds", "Feed URLs", "list", ["https://feeds.bbci.co.uk/news/world/rss.xml"]),
        F("layout", "Layout", "select", "rotate",
          choices=[["rotate", "One at a time"], ["list", "List"], ["ticker", "Scrolling ticker"]]),
        F("count", "Items in list", "number", 4, min=1, max=10),
        F("interval", "Seconds per headline", "number", 12, min=3, max=120),
        F("showSource", "Show source", "bool", True),
        F("descLength", "Description length", "number", 160, min=0, max=300),
        F("tickerSpeed", "Ticker speed (px/s)", "number", 80, min=20, max=400),
    ]},
    "weather": {"label": "Weather", "style": {"fontSize": 32}, "options": [
        F("units", "Units", "select", "c", choices=[["c", "°C"], ["f", "°F"]]),
        F("days", "Forecast days", "number", 3, min=0, max=7),
        F("showDetails", "Show humidity and wind", "bool", False),
    ]},
    "shalat": {"label": "Shalat times", "style": {"fontSize": 30}, "options": [
        F("method", "Calculation method", "select", "mwl", choices=PRAYER_METHODS),
        F("madhab", "Asr method", "select", "shafi", choices=[["shafi", "Shafi'i (standard)"], ["hanafi", "Hanafi"]]),
        F("fajrAngle", "Fajr angle (custom)", "number", 20, min=10, max=25, step=0.1),
        F("ishaAngle", "Isha angle (custom)", "number", 18, min=10, max=25, step=0.1),
        F("adjFajr", "Fajr adjust (min)", "number", 0, min=-30, max=30),
        F("adjDhuhr", "Dhuhr adjust (min)", "number", 0, min=-30, max=30),
        F("adjAsr", "Asr adjust (min)", "number", 0, min=-30, max=30),
        F("adjMaghrib", "Maghrib adjust (min)", "number", 0, min=-30, max=30),
        F("adjIsha", "Isha adjust (min)", "number", 0, min=-30, max=30),
        F("showImsak", "Show Imsak", "bool", False),
        F("showSunrise", "Show sunrise", "bool", True),
        F("highlightNext", "Highlight next prayer", "bool", True),
        F("countdown", "Countdown to next prayer", "bool", True),
        F("hour24", "24-hour times", "bool", True),
    ]},
}

SECTIONS = {
    "theme": [
        F("background", "Background", "color", "#000000"),
        F("font", "Font", "select", "Inter", choices=FONTS[1:]),
        F("color", "Text colour", "color", "#FFFFFF"),
    ],
    "display": [
        F("rotation", "Rotation", "select", 0, choices=[[0, "0°"], [90, "90°"], [180, "180°"], [270, "270°"]]),
        F("mode", "Resolution", "mode", "auto"),
        F("scale", "UI scale", "number", 1.0, min=0.5, max=2.0, step=0.05),
        F("padding", "Edge padding (%)", "object", None, fields=[
            F(k, k.title(), "number", 0, min=0, max=10, step=0.5) for k in ("top", "right", "bottom", "left")]),
        F("schedule", "Screen off", "object", None, fields=[
            F("enabled", "Turn screen off at night", "bool", False),
            F("off", "Off at", "time", "23:00"),
            F("on", "On at", "time", "06:00"),
        ]),
    ],
    "location": [
        F("name", "Name", "text", "", maxLength=120),
        F("lat", "Latitude", "coord", None, min=-90, max=90),
        F("lon", "Longitude", "coord", None, min=-180, max=180),
        F("timezone", "Timezone", "tz", "UTC"),
        F("country", "Country code", "country", ""),
    ],
    "photos": [
        F("driveUrl", "Google Drive folder link", "text", "", maxLength=500),
        F("apiKey", "Google API key (optional)", "text", "", maxLength=100),
        F("syncMinutes", "Sync every (minutes)", "number", 30, min=5, max=1440),
    ],
    "updates": [
        F("repo", "GitHub repo", "repo", "DaniyalAqeela/home-dashboard"),
    ],
}

DEFAULT_LAYOUT = [
    ("photos", 0, 0, 70, 88),
    ("clock", 70, 0, 30, 30),
    ("shalat", 70, 30, 30, 40),
    ("weather", 70, 70, 30, 18),
    ("news", 0, 88, 100, 12),
]

_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n", ""}


def _norm_value(field, value):
    t, d = field["type"], field["default"]
    if t == "object":
        return _norm_fields(field["fields"], value)
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE
        return d
    if t in ("number", "coord"):
        if isinstance(value, bool) or value is None or value == "":
            return d
        try:
            v = float(value)
        except (TypeError, ValueError):
            return d
        if math.isnan(v) or math.isinf(v):
            return d
        v = min(max(v, field["min"]), field["max"])
        if isinstance(d, int) and "step" not in field:
            return int(round(v))
        return round(v, 6)
    if t == "select":
        values = [c[0] for c in field["choices"]]
        if value in values:
            return value
        for c in values:  # tolerate "90" for 90
            if str(c) == str(value):
                return c
        return d
    if t == "color":
        if isinstance(value, str) and (COLOR_RE.match(value) or (value == "" and d == "")):
            return value.upper() if value else value
        return d
    if t == "text":
        return value.strip()[: field.get("maxLength", 500)] if isinstance(value, str) else d
    if t == "list":
        if not isinstance(value, list):
            return list(d)
        return [s.strip()[:500] for s in value if isinstance(s, str) and s.strip()][:20]
    if t == "time":
        m = re.match(r"^\s*(\d{1,2}):(\d{1,2})\s*$", value) if isinstance(value, str) else None
        if m and int(m[1]) < 24 and int(m[2]) < 60:
            return f"{int(m[1]):02d}:{int(m[2]):02d}"
        return d
    if t == "mode":
        if isinstance(value, str) and re.match(r"^\d{3,5}x\d{3,5}(@\d{2,3})?$", value):
            return value
        return d
    if t == "tz":
        if isinstance(value, str) and re.match(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+){0,2}$", value):
            return value
        return d
    if t == "country":
        if isinstance(value, str) and re.match(r"^[A-Za-z]{2}$", value):
            return value.upper()
        return d
    if t == "repo":
        if isinstance(value, str) and re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", value):
            return value
        return d
    raise AssertionError(f"unknown field type {t}")


def _norm_fields(fields, raw, overrides=None):
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for f in fields:
        if overrides and f["key"] in overrides:
            f = {**f, "default": overrides[f["key"]]}
        out[f["key"]] = _norm_value(f, raw.get(f["key"], f["default"]))
    return out


def _norm_widget(raw, used_ids):
    if not isinstance(raw, dict) or raw.get("type") not in WIDGET_TYPES:
        return None
    spec = WIDGET_TYPES[raw["type"]]
    wid = raw.get("id")
    if not isinstance(wid, str) or not re.match(r"^[A-Za-z0-9_-]{1,40}$", wid) or wid in used_ids:
        wid = uuid.uuid4().hex[:8]
    used_ids.add(wid)
    num = lambda k, d, lo, hi: _norm_value(F(k, k, "number", d, min=lo, max=hi, step=0.01), raw.get(k, d))
    x = num("x", 0, 0, 99)
    y = num("y", 0, 0, 99)
    w = min(num("w", 30, 1, 100), 100 - x)
    h = min(num("h", 30, 1, 100), 100 - y)
    return {
        "id": wid, "type": raw["type"],
        "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2),
        "z": int(num("z", 0, -100, 100)),
        "visible": _norm_value(F("visible", "", "bool", True), raw.get("visible", True)),
        "style": _norm_fields(COMMON_STYLE, raw.get("style"), spec.get("style")),
        "options": _norm_fields(spec["options"], raw.get("options")),
    }


def normalize(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {"schema": 1}
    for name, fields in SECTIONS.items():
        out[name] = _norm_fields(fields, raw.get(name))
    widgets_raw = raw.get("widgets") if isinstance(raw.get("widgets"), list) else None
    if widgets_raw is None:
        widgets_raw = _default_widgets()
    used = set()
    out["widgets"] = [w for w in (_norm_widget(r, used) for r in widgets_raw[:50]) if w]
    return out


def _default_widgets():
    return [{"id": f"{t}1", "type": t, "x": x, "y": y, "w": w, "h": h, "z": i}
            for i, (t, x, y, w, h) in enumerate(DEFAULT_LAYOUT)]


def default_config() -> dict:
    return normalize({})


def load(path) -> dict:
    return normalize(fsutil.read_json(Path(path), {}))


def save(path, cfg) -> dict:
    cfg = normalize(cfg)
    fsutil.atomic_write_json(Path(path), cfg)
    return cfg
