"""Prayer times (adhanpy) and Hijri date (hijridate, Umm al-Qura), computed on
the Pi so they work without internet."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.calculation.CalculationParameters import CalculationParameters
from adhanpy.calculation.Madhab import Madhab
from adhanpy.calculation.PrayerAdjustments import PrayerAdjustments
from adhanpy.PrayerTimes import PrayerTimes
from hijridate import Gregorian

METHODS = {
    "mwl": CalculationMethod.MUSLIM_WORLD_LEAGUE,
    "isna": CalculationMethod.NORTH_AMERICA,
    "egypt": CalculationMethod.EGYPTIAN,
    "ummalqura": CalculationMethod.UMM_AL_QURA,
    "karachi": CalculationMethod.KARACHI,
    "singapore": CalculationMethod.SINGAPORE,
    "dubai": CalculationMethod.DUBAI,
    "kuwait": CalculationMethod.KUWAIT,
    "qatar": CalculationMethod.QATAR,
    "moonsighting": CalculationMethod.MOON_SIGHTING_COMMITTEE,
}
ORDER = [("imsak", "Imsak"), ("fajr", "Fajr"), ("sunrise", "Sunrise"), ("dhuhr", "Dhuhr"),
         ("asr", "Asr"), ("maghrib", "Maghrib"), ("isha", "Isha")]
IMSAK_BEFORE_FAJR = timedelta(minutes=10)


def _entry(key, name, t: datetime):
    return {"key": key, "name": name, "ts": int(t.timestamp() * 1000),
            "time24": t.strftime("%H:%M"), "time12": t.strftime("%I:%M %p").lstrip("0")}


def prayer_times(lat, lon, tz, day: date, method="mwl", madhab="shafi", adjust=None,
                 fajr_angle=None, isha_angle=None) -> list:
    if method in METHODS:
        params = CalculationParameters(method=METHODS[method])
    else:  # "custom" (or anything unknown) uses the given angles
        params = CalculationParameters(fajr_angle=float(fajr_angle or 18), isha_angle=float(isha_angle or 17))
    params.madhab = Madhab.HANAFI if madhab == "hanafi" else Madhab.SHAFI
    a = adjust or {}
    params.adjustments = PrayerAdjustments(fajr=int(a.get("fajr", 0)), dhuhr=int(a.get("dhuhr", 0)),
                                           asr=int(a.get("asr", 0)), maghrib=int(a.get("maghrib", 0)),
                                           isha=int(a.get("isha", 0)))
    zone = ZoneInfo(tz)
    pt = PrayerTimes((lat, lon), datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
                     calculation_parameters=params, time_zone=zone)
    times = {k: getattr(pt, k) for k, _ in ORDER if k != "imsak"}
    times["imsak"] = times["fajr"] - IMSAK_BEFORE_FAJR
    return [_entry(k, name, times[k]) for k, name in ORDER]


def next_prayer(times_today, times_tomorrow, now_ms) -> dict:
    for t in list(times_today) + list(times_tomorrow):
        if t["key"] not in ("imsak", "sunrise") and t["ts"] > now_ms:
            return t
    return times_tomorrow[1]


def hijri(day: date, adjust_days: int = 0) -> dict:
    d = day + timedelta(days=int(adjust_days))
    h = Gregorian(d.year, d.month, d.day).to_hijri()
    return {"day": h.day, "month": h.month, "year": h.year,
            "monthName": h.month_name("en"), "monthNameAr": h.month_name("ar")}
