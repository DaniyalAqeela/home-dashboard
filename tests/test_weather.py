import io
import json
import urllib.parse

from dashboard import weather

FORECAST = {
    "current": {"temperature_2m": 31.4, "weather_code": 2, "is_day": 1, "relative_humidity_2m": 70,
                "wind_speed_10m": 11.2},
    "daily": {"time": ["2026-11-25", "2026-11-26"], "weather_code": [61, 95],
              "temperature_2m_max": [32.0, 30.5], "temperature_2m_min": [24.1, 23.9]},
}
PLACES = {"results": [{"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia", "country_code": "ID",
                       "latitude": -6.21, "longitude": 106.85, "timezone": "Asia/Jakarta"}]}


class FakeHttp:
    def __init__(self, payload):
        self.payload, self.urls = payload, []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        return io.BytesIO(json.dumps(self.payload).encode())


def test_fetch_forecast_parses():
    http = FakeHttp(FORECAST)
    f = weather.fetch_forecast(-6.21, 106.85, http=http)
    assert f["current"] == {"temp": 31.4, "code": 2, "isDay": True, "humidity": 70, "wind": 11.2,
                            "icon": "partly-day", "label": "Partly cloudy"}
    assert f["daily"][1] == {"date": "2026-11-26", "code": 95, "max": 30.5, "min": 23.9, "icon": "storm",
                             "label": "Thunderstorm"}
    q = urllib.parse.parse_qs(urllib.parse.urlparse(http.urls[0]).query)
    assert q["latitude"] == ["-6.21"] and "weather_code" in q["daily"][0]


def test_search_places_parses():
    http = FakeHttp(PLACES)
    r = weather.search_places("Jakarta", http=http)
    assert r == [{"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia", "countryCode": "ID",
                  "lat": -6.21, "lon": 106.85, "timezone": "Asia/Jakarta"}]
    assert weather.search_places("", http=http) == []


def test_search_places_no_results():
    assert weather.search_places("zzzz", http=FakeHttp({})) == []


def test_wmo_mapping():
    assert weather.wmo(0, True)["icon"] == "clear-day"
    assert weather.wmo(0, False)["icon"] == "clear-night"
    assert weather.wmo(95, True)["icon"] == "storm"
    assert weather.wmo(61, True)["icon"] == "rain"
    assert weather.wmo(12345, True)["icon"] == "cloudy"


def _with_location(rt):
    cfg = dict(rt.config)
    cfg["location"] = {"name": "Jakarta", "lat": -6.21, "lon": 106.85, "timezone": "Asia/Jakarta", "country": "ID"}
    rt.update_config(cfg)
    return next(w for w in rt.config["widgets"] if w["type"] == "weather")["id"]


def test_weather_refresh_keeps_cache_on_error(rt):
    wid = _with_location(rt)
    rt.refresh_weather(http=FakeHttp(FORECAST))
    assert rt.build_display_state()["widgets"][wid]["current"]["temp"] == 31.4

    def offline(url, timeout=None):
        raise OSError("no internet")
    rt.refresh_weather(http=offline)
    assert rt.build_display_state()["widgets"][wid]["current"]["temp"] == 31.4
    # survives a restart: cache is on disk
    from dashboard import features
    from dashboard.runtime import Runtime
    rt2 = Runtime(rt.data_dir, rt.boot_dir, rt.app_dir, dev=True)
    features.install(rt2)
    assert rt2.build_display_state()["widgets"][wid]["current"]["temp"] == 31.4


def test_weather_without_location(rt):
    wid = next(w for w in rt.config["widgets"] if w["type"] == "weather")["id"]
    assert "location" in rt.build_display_state()["widgets"][wid]["error"]


def test_location_search_route(admin, monkeypatch):
    from conftest import REMOTE
    monkeypatch.setattr(weather, "search_places", lambda q, http=None: [{"name": q}])
    assert admin.get("/api/location/search?q=Paris", environ_overrides=REMOTE).json == [{"name": "Paris"}]
