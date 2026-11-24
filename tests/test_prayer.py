from datetime import date, datetime
from zoneinfo import ZoneInfo

from dashboard import prayer

MECCA = (21.4225, 39.8262)
JAKARTA = (-6.2088, 106.8456)


def minutes(entry, tz):
    t = datetime.fromtimestamp(entry["ts"] / 1000, ZoneInfo(tz))
    return t.hour * 60 + t.minute


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def by_key(times):
    return {t["key"]: t for t in times}


def test_mecca_ummalqura_known_day():
    # Published Umm al-Qura times for Makkah, 15 Jan 2026 (+-5 min tolerance)
    t = by_key(prayer.prayer_times(*MECCA, "Asia/Riyadh", date(2026, 1, 15), "ummalqura", "shafi", {}))
    expected = {"fajr": "05:39", "sunrise": "06:59", "dhuhr": "12:28", "asr": "15:34", "maghrib": "17:57"}
    for k, v in expected.items():
        assert abs(minutes(t[k], "Asia/Riyadh") - hm(v)) <= 5, (k, t[k])
    assert minutes(t["isha"], "Asia/Riyadh") - minutes(t["maghrib"], "Asia/Riyadh") == 90
    assert t["fajr"]["time24"] == datetime.fromtimestamp(t["fajr"]["ts"] / 1000, ZoneInfo("Asia/Riyadh")).strftime("%H:%M")


def test_jakarta_singapore_method():
    t = by_key(prayer.prayer_times(*JAKARTA, "Asia/Jakarta", date(2026, 1, 15), "singapore", "shafi", {}))
    for k, v in {"fajr": "04:20", "dhuhr": "12:00", "maghrib": "18:15", "isha": "19:30"}.items():
        assert abs(minutes(t[k], "Asia/Jakarta") - hm(v)) <= 6, (k, t[k])


def test_order_and_imsak():
    times = prayer.prayer_times(*MECCA, "Asia/Riyadh", date(2026, 1, 15), "mwl", "shafi", {})
    assert [t["key"] for t in times] == ["imsak", "fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]
    assert [t["name"] for t in times] == ["Imsak", "Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
    assert all(a["ts"] < b["ts"] for a, b in zip(times, times[1:]))
    assert times[1]["ts"] - times[0]["ts"] == 10 * 60 * 1000


def test_adjustments_and_madhab():
    base = by_key(prayer.prayer_times(*MECCA, "Asia/Riyadh", date(2026, 1, 15), "mwl", "shafi", {}))
    adj = by_key(prayer.prayer_times(*MECCA, "Asia/Riyadh", date(2026, 1, 15), "mwl", "shafi", {"isha": 5}))
    hanafi = by_key(prayer.prayer_times(*MECCA, "Asia/Riyadh", date(2026, 1, 15), "mwl", "hanafi", {}))
    assert adj["isha"]["ts"] - base["isha"]["ts"] == 5 * 60 * 1000
    assert hanafi["asr"]["ts"] > base["asr"]["ts"] + 30 * 60 * 1000


def test_custom_angles():
    a = by_key(prayer.prayer_times(*JAKARTA, "Asia/Jakarta", date(2026, 1, 15), "custom", "shafi", {},
                                   fajr_angle=20, isha_angle=18))
    b = by_key(prayer.prayer_times(*JAKARTA, "Asia/Jakarta", date(2026, 1, 15), "custom", "shafi", {},
                                   fajr_angle=15, isha_angle=15))
    assert a["fajr"]["ts"] < b["fajr"]["ts"] and a["isha"]["ts"] > b["isha"]["ts"]


def test_next_prayer_after_isha_is_tomorrow_fajr():
    tz = "Asia/Riyadh"
    today = prayer.prayer_times(*MECCA, tz, date(2026, 1, 15), "mwl", "shafi", {})
    tomorrow = prayer.prayer_times(*MECCA, tz, date(2026, 1, 16), "mwl", "shafi", {})
    after_isha = today[-1]["ts"] + 60_000
    assert prayer.next_prayer(today, tomorrow, after_isha)["key"] == "fajr"
    assert prayer.next_prayer(today, tomorrow, after_isha)["ts"] == tomorrow[1]["ts"]
    before_dhuhr = today[3]["ts"] - 60_000  # just after sunrise: skips sunrise, gives dhuhr
    assert prayer.next_prayer(today, tomorrow, before_dhuhr)["key"] == "dhuhr"


def test_hijri_known_date():
    h = prayer.hijri(date(2026, 2, 18), 0)
    assert (h["year"], h["month"], h["day"]) in {(1447, 9, 1), (1447, 8, 30)}
    assert h["monthName"] in ("Ramadhan", "Ramadan", "Sha’ban", "Shaban", "Sha'ban")
    assert h["monthNameAr"]


def test_hijri_adjust():
    a = prayer.hijri(date(2026, 3, 10), 0)
    b = prayer.hijri(date(2026, 3, 10), 1)
    assert b["day"] == a["day"] + 1


def test_shalat_provider_in_display_state(rt):
    cfg = dict(rt.config)
    cfg["location"] = {"name": "Makkah", "lat": 21.4225, "lon": 39.8262, "timezone": "Asia/Riyadh", "country": "SA"}
    rt.update_config(cfg)
    st = rt.build_display_state()
    shalat = next(w for w in rt.config["widgets"] if w["type"] == "shalat")
    clock = next(w for w in rt.config["widgets"] if w["type"] == "clock")
    data = st["widgets"][shalat["id"]]
    assert [t["key"] for t in data["times"]] == ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]
    assert data["next"]["key"] in {"fajr", "dhuhr", "asr", "maghrib", "isha"}
    assert st["widgets"][clock["id"]]["hijri"]["year"] >= 1447


def test_shalat_provider_without_location(rt):
    shalat = next(w for w in rt.config["widgets"] if w["type"] == "shalat")
    assert "location" in rt.build_display_state()["widgets"][shalat["id"]]["error"]
