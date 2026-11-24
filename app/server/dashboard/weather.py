"""Weather and place search via Open-Meteo (no API key)."""
import json
import time
import urllib.parse

from . import net

# WMO weather codes -> (icon, label). Icons are files in app/display/icons/<icon>.svg.
_WMO = [
    ((0,), "clear", "Clear"),
    ((1, 2), "partly", "Partly cloudy"),
    ((3,), "cloudy", "Cloudy"),
    ((45, 48), "fog", "Fog"),
    ((51, 53, 55, 56, 57), "drizzle", "Drizzle"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "rain", "Rain"),
    ((71, 73, 75, 77, 85, 86), "snow", "Snow"),
    ((95, 96, 99), "storm", "Thunderstorm"),
]


def wmo(code, is_day=True) -> dict:
    for codes, icon, label in _WMO:
        if code in codes:
            if icon in ("clear", "partly"):
                icon += "-day" if is_day else "-night"
            return {"icon": icon, "label": label}
    return {"icon": "cloudy", "label": "Cloudy"}


def fetch_forecast(lat, lon, http=None) -> dict:
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
        "current": "temperature_2m,weather_code,is_day,relative_humidity_2m,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
    })
    d = json.loads(net.get_bytes("https://api.open-meteo.com/v1/forecast?" + q, http))
    c = d["current"]
    current = {"temp": c["temperature_2m"], "code": c["weather_code"], "isDay": bool(c["is_day"]),
               "humidity": c.get("relative_humidity_2m"), "wind": c.get("wind_speed_10m"),
               **wmo(c["weather_code"], bool(c["is_day"]))}
    dl = d["daily"]
    daily = [{"date": dl["time"][i], "code": dl["weather_code"][i], "max": dl["temperature_2m_max"][i],
              "min": dl["temperature_2m_min"][i], **wmo(dl["weather_code"][i], True)}
             for i in range(len(dl["time"]))]
    return {"current": current, "daily": daily, "fetchedAt": time.time()}


def search_places(q, http=None) -> list:
    q = (q or "").strip()
    if not q:
        return []
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": q[:100], "count": 8, "language": "en", "format": "json"})
    d = json.loads(net.get_bytes(url, http))
    return [{"name": r.get("name", ""), "admin1": r.get("admin1", ""), "country": r.get("country", ""),
             "countryCode": r.get("country_code", ""), "lat": r["latitude"], "lon": r["longitude"],
             "timezone": r.get("timezone", "UTC")} for r in d.get("results") or []]
