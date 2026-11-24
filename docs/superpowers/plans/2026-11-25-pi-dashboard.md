# Pi Home Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A flashable Buildroot image for a Raspberry Pi 3B that boots into a native Qt
full-screen family dashboard, configured from a password-protected settings website,
with browser-upload and GitHub app updates.

**Architecture:** A read-only Buildroot OS layer (kernel, systemd, Mesa vc4, Qt 6.9
eglfs, Python 3.14 + Flask + Pillow, tiny launchers) runs an updatable app folder.
That folder holds a Python server (state, sync, settings site, system actions), the
display written in QML (loaded at runtime by a 20-line C++ launcher), and a
vanilla-JS settings site. The display long-polls the server on 127.0.0.1. It writes
screenshots to a tmpfs file, which the settings site shows as the live preview.

**Tech Stack:** Buildroot 2026.02.3 (LTS), aarch64, Qt 6.9.1 (qt6base eglfs +
GLES2, qt6declarative, qt6svg), Python 3.14 (dev on Windows Python 3.12), Flask 3.1,
Pillow 12, vendored `adhanpy` 1.0.5 (MIT) and `hijridate` 2.6.0 (MIT), pytest,
PySide6 6.9.1 (dev-only QML runner).

**Spec:** `docs/superpowers/specs/2026-11-25-pi-dashboard-design.md`

## Global Constraints

- Hardware: Raspberry Pi 3B, 1 GB RAM, vc4, **GLES 2.0 only**. Any QML must run on Qt 6.9 with GLES2.
- Root filesystem mounted **read-only**. Every write goes to `/data` (or tmpfs). State writes are atomic (temp, fsync, rename).
- Settings site on port 80, hostname `dashboard` (`dashboard.local`). The display only talks to `127.0.0.1`.
- Every state-changing endpoint, plus screenshots and photo listing, requires login. Display endpoints are allowed only from `127.0.0.1`.
- Mutating API calls must carry the header `X-Dashboard: 1` (CSRF guard). The session cookie uses `SameSite=Strict`.
- Screen language: English. No browser on the Pi, no SSH, no getty or login on any console.
- Public repo: never commit secrets, photos, personal config or the owner's Drive folder ID. Test fixtures are synthetic.
- Server code must run on Python 3.12 (dev) and 3.14 (Pi). Python stdlib plus Flask, Werkzeug and Pillow only; other libraries are vendored pure-Python.
- Layout coordinates are percentages (0–100) of the logical (post-rotation) screen. Font sizes are px at a 1080-line screen, times `scale`.
- Update file name: `dashboard-app-<version>.tar.gz`. Its root contains `VERSION`, `server/`, `display/`, `web/` and an optional `post-install.sh`.
- Version strings match `^[0-9A-Za-z._-]{1,32}$`.

## Review Focus

1. **Drive folder not public, or link pasted wrong** (sign-in redirect / 401 / bad URL). Expect a clear message telling the owner to set "Anyone with the link". Cached photos keep showing. Test: Task 6 `test_list_folder_not_public`.
2. **Malicious or broken update file** (symlink, `../`, absolute path, missing VERSION, not a tarball, huge). Expect it rejected with nothing changed on disk. Test: Task 8 `test_install_rejects_*`.
3. **Corrupt or hand-edited config.json, or a config PUT with wrong types** (strings for numbers, unknown widget type, a widget off-screen). Expect it normalized to sane values; the display never breaks. Test: Task 1 `test_normalize_*`.
4. **No internet at boot** (feeds, weather and Drive all fail). Expect the last cache served, prayer times and Hijri still computed, and the display state still valid. Test: Task 5 `test_refresh_keeps_cache_on_error` and Task 4 (offline by construction).
5. **Wi-Fi password or SSID with quotes, spaces or unicode.** Expect it passed safely (hex SSID, PBKDF2 PSK), never through a shell. Test: Task 7 `test_wifi_connect_commands_are_safe`.

---

## File Structure

```
app/VERSION                         app version, e.g. 0.1.0
app/server/dashboard/__main__.py    CLI entry: python -m dashboard --data DIR --port N [--dev] [--boot DIR] [--appdir DIR]
app/server/dashboard/config.py      DEFAULTS, normalize(), load(), save(), WIDGET_TYPES schema
app/server/dashboard/fsutil.py      atomic_write_bytes/json, safe_name()
app/server/dashboard/auth.py        password hash/verify, reset-file check, login_required, csrf check
app/server/dashboard/state.py       DisplayState (rev counter, long-poll wait, screenshot wanted)
app/server/dashboard/prayer.py      prayer_times(), hijri_today()
app/server/dashboard/weather.py     fetch_forecast(), search_places(), WMO code map
app/server/dashboard/feeds.py       parse_feed(), FeedCache
app/server/dashboard/drive.py       folder_id_from_url(), list_folder(), DriveSync
app/server/dashboard/photos.py      PhotoLibrary (drive + uploads), add_upload(), Slideshow
app/server/dashboard/system.py      System (real) / DevSystem (stub): wifi, display modes, timezone, screen power, restart, logs
app/server/dashboard/updates.py     install_bundle(), rollback(), github_latest(), mark_healthy()
app/server/dashboard/backup.py      make_backup(), restore_backup()
app/server/dashboard/runtime.py     Runtime: wires everything, background loop, build_display_state()
app/server/dashboard/web.py         create_app(runtime) Flask routes
app/server/dashboard/vendor/        adhanpy/, hijridate/ (+ LICENSE files)
app/display/Main.qml                window, rotation/scale/padding, long-poll, screenshot, widget repeater
app/display/WidgetFrame.qml         common style wrapper
app/display/widgets/{Photos,Clock,News,Weather,Shalat}Widget.qml
app/display/SetupScreen.qml         first-boot "open http://dashboard.local" screen
app/display/fonts/, app/display/icons/   bundled fonts (OFL), hand-made weather SVGs
app/web/index.html, app.js, style.css    settings site (single page)
os/external.desc, os/external.mk, os/Config.in
os/configs/dashboard_rpi3_defconfig
os/board/rpi3/{config.txt,cmdline.txt,genimage.cfg,post-build.sh,post-image.sh,users.txt}
os/board/rpi3/overlay/...           systemd units, launchers, networkd, fstab, tmpfiles, journald/resolved conf
os/package/dashboard-display/       C++ QML launcher (Config.in, .mk, src/main.cpp, src/CMakeLists.txt)
scripts/build-image.sh              WSL: fetch pinned Buildroot, build, output dist/dashboard-<ver>.img.xz
scripts/make-update.sh              pack app/ -> dist/dashboard-app-<ver>.tar.gz
scripts/release.sh                  gh release create v<ver> with both files
scripts/dev.ps1                     run dev server + optional QML window on Windows
tests/                              pytest, one file per server module
docs/USER-GUIDE.md                  flash, first setup, Drive sharing, Wi-Fi, updates, backup, password reset
```

---

### Task 1: Scaffold, config model and atomic storage

**Files:** Create `app/VERSION` (`0.1.0`), `app/server/dashboard/{__init__,fsutil,config}.py`, `requirements-dev.txt` (flask, pillow, tzdata, pytest, PySide6==6.9.1), `pytest.ini` (pythonpath = app/server), `.gitignore` (devdata/, dist/, __pycache__, *.img*), `tests/test_config.py`.

**Interfaces — Produces:**
- `fsutil.atomic_write_bytes(path: Path, data: bytes) -> None` and `atomic_write_json(path, obj)`: write a temp file in the same dir, fsync, `os.replace`.
- `fsutil.safe_name(name: str) -> str`: `[A-Za-z0-9._-]`, max 80 chars, never empty or starting with `.`.
- `config.WIDGET_TYPES: dict[str, dict]`, type → `{"label", "options": [field…]}`. A field is `{"key","label","type": "number|text|bool|select|color|list|time","default", "min","max","choices"}`. Shared by normalize() and the settings UI (`/api/schema`).
- `config.COMMON_STYLE: list[field]`: background (`#RRGGBBAA`), radius, padding, font, fontSize, color, align (`left|center|right`), shadow (bool).
- `config.default_config() -> dict` with keys `schema, theme{background,font,color}, display{rotation,mode,scale,padding{top,right,bottom,left},schedule{enabled,off,on}}, location{name,lat,lon,timezone,country}, photos{driveUrl,apiKey,syncMinutes}, news{} , updates{repo:"DaniyalAqeela/home-dashboard"}, widgets[]`. The default widgets follow the spec §7.3 layout: photos 0,0,70,88; clock 70,0,30,30; shalat 70,30,30,40; weather 70,70,30,18; news 0,88,100,12 (rotate layout). Default font `Inter`.
- `config.normalize(raw: Any) -> dict`: never raises. Unknown keys dropped; numbers clamped; enums coerced to defaults. Widgets: unknown type dropped, missing `id` assigned, `x,y` clamped to [0,100), `w,h` clamped to [1,100] and to `x+w≤100`. Rotation ∈ {0,90,180,270}, scale ∈ [0.5,2.0], times `HH:MM`.
- `config.load(path) -> dict` (missing or corrupt → defaults) and `config.save(path, cfg) -> dict` (normalizes, then writes atomically and returns the normalized config).

- [ ] **Step 1:** Write `tests/test_config.py`: `test_defaults_roundtrip` (normalize(default_config()) == default_config()), `test_normalize_bad_types` (`{"display":{"rotation":"45","scale":"x"}}` → rotation 0, scale 1.0), `test_normalize_drops_unknown_widget`, `test_normalize_clamps_widget_geometry` (x=95,w=50 → w=5), `test_load_corrupt_file_gives_defaults`, `test_save_is_atomic_and_normalized`, `test_safe_name` (`"../a b?.jpg"` → `"a_b_.jpg"`, `""` → non-empty).
- [ ] **Step 2:** `pip install -r requirements-dev.txt`, then run `pytest tests/test_config.py -q`. Expect FAIL (module missing).
- [ ] **Step 3:** Implement fsutil.py and config.py with the interfaces above.
- [ ] **Step 4:** Run `pytest tests/test_config.py -q`. Expect all pass.
- [ ] **Step 5:** Commit `feat: config model and atomic storage`.

### Task 2: Auth, display state, Flask skeleton, runtime wiring

**Files:** Create `auth.py`, `state.py`, `runtime.py`, `web.py`, `__main__.py`, `tests/test_web.py`, `tests/test_state.py`, plus placeholder `app/web/index.html`.

**Interfaces:**
- Consumes: config.load/save/normalize, fsutil.
- Produces:
  - `auth.Auth(data_dir: Path, boot_dir: Path)` with `.is_set() -> bool`, `.set_password(pw: str) -> None` (min 6 chars, else ValueError; scrypt n=2**14,r=8,p=1, 16-byte salt, stored in `auth.json`), `.verify(pw) -> bool` (constant-time), `.check_reset_file() -> bool` (if `boot_dir/reset-password` exists: delete auth.json, try to delete the file, return True), `.secret_key() -> bytes` (`secret.key`, 32 random bytes, created once).
  - `state.DisplayState` with `.rev: int`, `.bump() -> None`, `.wait(since: int, timeout: float) -> int` (threading.Condition), `.want_screenshot() -> None` (sets `wanted_until=now+5s`, bumps on rising edge), `.screenshot_wanted() -> bool`.
  - `runtime.Runtime(data_dir, boot_dir, app_dir, dev: bool)` holds `.config`, `.state`, `.auth`, `.system`, `.photos`, `.feeds`, `.weather_cache`, `.drive`, `.version`, and `.screenshot_path` (`/run/dashboard/screen.jpg`, dev: `data_dir/screen.jpg`). Methods: `.update_config(new: dict) -> dict` (save + bump), `.build_display_state() -> dict`, `.start_background() -> None` (one daemon thread ticking each second; later tasks register jobs with `.every(seconds, fn)`).
  - `web.create_app(rt: Runtime) -> Flask`. Routes:
    - `GET /` → `app/web/index.html`; `/static/<path>` → `app/web`.
    - `GET /api/auth/status` → `{set, loggedIn}`; `POST /api/auth/setup {password}` (only when not set); `POST /api/auth/login {password}`; `POST /api/auth/logout`; `POST /api/auth/password {old,new}`.
    - `GET /api/config`; `PUT /api/config` (normalized config echoed back); `GET /api/schema` → `{widgets: WIDGET_TYPES, common: COMMON_STYLE}`.
    - `GET /api/display/state?since=N` (localhost only, long-poll ≤25 s): returns `build_display_state()`.
    - `GET /api/screenshot` (login): calls `want_screenshot()` and serves the screenshot file (`Cache-Control: no-store`), or 204 if none yet.
    - `GET /api/health` → `{ok, version}`.
  - `@login_required` returns 401 JSON. A mutating method without `X-Dashboard: 1` returns 403.
  - `__main__`: argparse `--data --port --dev --boot --appdir`. Runs `check_reset_file()`, builds Runtime, then `start_background()` and `app.run(host="0.0.0.0", port, threaded=True)`.
- `build_display_state()` returns at least `{rev, version, config, setup: {needed: not auth.is_set(), urls: [...]}, screenshot: {wanted, path}, clockSynced, widgets: {<id>: {...per-widget data...}}}`.

- [ ] **Step 1:** Write `tests/test_web.py` using the Flask test client with a tmp data dir:
  - `test_setup_then_login`
  - `test_api_requires_login` (PUT /api/config → 401)
  - `test_mutation_requires_csrf_header` (403 without the header)
  - `test_display_state_localhost_only` (remote_addr 10.0.0.5 → 403)
  - `test_reset_file_clears_password`
  - `test_put_config_normalizes`

  Write `tests/test_state.py`: `test_wait_returns_immediately_when_newer`, `test_wait_times_out`, `test_screenshot_wanted_expires` (monkeypatch time).
- [ ] **Step 2:** Run `pytest tests/test_web.py tests/test_state.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement the modules.
- [ ] **Step 4:** Tests pass. Smoke test: `python -m dashboard --dev --data devdata --port 8080`, then `curl localhost:8080/api/health` returns `{"ok":true,...}`.
- [ ] **Step 5:** Commit `feat: server skeleton with auth and display state`.

### Task 3: Prayer times and Hijri date

**Files:** Vendor `app/server/dashboard/vendor/adhanpy/` and `vendor/hijridate/` with their LICENSE files (from the wheels). Create `prayer.py` and `tests/test_prayer.py`.

**Interfaces — Produces:**
- `prayer.METHODS: dict[str, str]` (key → label): `mwl, isna, egypt, ummalqura, karachi, singapore` (label "Singapore / Kemenag / JAKIM"), `turkey, tehran, dubai, kuwait, qatar, moonsighting, custom`.
- `prayer.prayer_times(lat, lon, tz: str, day: date, method: str, madhab: "shafi"|"hanafi", adjust: dict[str,int], fajr_angle=None, isha_angle=None) -> list[{"key","name","ts"}]`. Keys in order are `imsak, fajr, sunrise, dhuhr, asr, maghrib, isha`, with English names `Imsak, Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha`. `ts` is epoch milliseconds. Imsak = Fajr − 10 min.
- `prayer.next_prayer(times_today, times_tomorrow, now_ms) -> {"key","name","ts"}`, skipping imsak and sunrise.
- `prayer.hijri(day: date, adjust_days: int) -> {"day","month","monthName","monthNameAr","year"}`.

- [ ] **Step 1:** Write the tests:
  - `test_mecca_ummalqura_known_day`: Mecca (21.4225, 39.8262), Asia/Riyadh, 2026-01-15, ummalqura. Fajr and Maghrib within ±2 min of the library's published reference values; compute the reference once from adhanpy and cross-check against a public timetable.
  - `test_order_and_imsak`
  - `test_next_prayer_after_isha_is_tomorrow_fajr`
  - `test_hijri_known_date`: 2026-02-18 → 1 Ramadan 1447 ±1 day; the assert allows 1447/9 day 1 or 30 Sha'ban.
  - `test_hijri_adjust`: +1 shifts the day by 1.
  - `test_custom_angles`
- [ ] **Step 2:** Run them and expect FAIL.
- [ ] **Step 3:** Implement on top of adhanpy `PrayerTimes((lat, lon), datetime, calculation_parameters=..., time_zone=ZoneInfo(tz))`. Methods map to `CalculationMethod` members. `custom` uses `CalculationParameters(fajr_angle=…, isha_angle=…)`. Madhab is set on the params; minute adjustments go through `PrayerAdjustments`. Hijri uses `hijridate.Gregorian(...).to_hijri()` after shifting the date by `adjust_days`.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat: prayer times and hijri date`.

### Task 4: Weather and places

**Files:** Create `weather.py` and `tests/test_weather.py`.

**Interfaces — Produces:**
- `weather.wmo(code: int, is_day: bool) -> {"icon","label"}`. Icons: `clear-day, clear-night, partly-day, partly-night, cloudy, fog, drizzle, rain, snow, storm`.
- `weather.fetch_forecast(lat, lon, http=urlopen) -> dict` returns `{current: {temp, code, isDay, humidity, wind}, daily: [{date, code, max, min}] ×7, fetchedAt}`, always in Celsius. It calls `https://api.open-meteo.com/v1/forecast` with `current=temperature_2m,weather_code,is_day,relative_humidity_2m,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=7`.
- `weather.search_places(q, http=urlopen) -> list[{name, admin1, country, countryCode, lat, lon, timezone}]` via `https://geocoding-api.open-meteo.com/v1/search?name=…&count=8&language=en`.
- The `http` parameter is injectable for tests. Timeout is 10 s and responses are capped at 1 MB.

- [ ] **Step 1:** Write the tests with a fake `http` returning recorded-shaped JSON: `test_fetch_forecast_parses`, `test_search_places_parses`, `test_wmo_mapping` (0 day → clear-day, 95 → storm, 61 → rain).
- [ ] **Step 2:** Run them and expect FAIL. **Step 3:** Implement. **Step 4:** Pass.
- [ ] **Step 5:** Commit `feat: open-meteo weather and place search`.

### Task 5: News feeds

**Files:** Create `feeds.py` and `tests/test_feeds.py`.

**Interfaces — Produces:**
- `feeds.parse_feed(xml: bytes, source_url: str) -> list[{"title","summary","source","ts"}]`. Handles RSS 2.0 and Atom. Strips HTML tags and entities from the summary, collapses whitespace, and truncates the summary to 300 chars. A feed-level title becomes `source`. Malformed XML raises `ValueError`.
- `feeds.FeedCache(data_dir, http=urlopen)` with `.refresh(urls: list[str]) -> None` (per-URL: 10 s timeout, 2 MB cap; on error keep that URL's previous items and record `errors[url]`; persist to `data_dir/cache/feeds.json`) and `.items(urls, limit=30) -> list` (merged, newest first, deduplicated by title).

- [ ] **Step 1:** Write the tests: `test_parse_rss`, `test_parse_atom`, `test_summary_html_stripped` (`<p>Hi <b>there</b> &amp; you</p>` → `Hi there & you`), `test_malformed_raises`, `test_refresh_keeps_cache_on_error`, `test_items_sorted_and_deduped`.
- [ ] **Step 2:** Run them and expect FAIL. **Step 3:** Implement with `xml.etree.ElementTree` and `html.unescape` plus a regex tag strip. **Step 4:** Pass.
- [ ] **Step 5:** Commit `feat: rss/atom feed cache`.

### Task 6: Google Drive sync, photo library, uploads, slideshow

**Files:** Create `drive.py`, `photos.py`, `tests/test_drive.py`, `tests/test_photos.py` and `tests/fixtures/embedded_folder.html` (synthetic, in the structure of `embeddedfolderview`: `div.flip-entry#entry-<ID>` > `a[href]` > `div.flip-entry-title`; 3 images, 1 subfolder link `/drive/folders/…`, 1 `.pdf`).

**Interfaces — Produces:**
- `drive.folder_id_from_url(url: str) -> str | None`. Accepts `/folders/<id>`, `?id=<id>` and a bare id; ids match `[A-Za-z0-9_-]{10,}`.
- `drive.DriveError(Exception)` with a user-facing message.
- `drive.list_folder(folder_id, api_key="", http=…) -> list[{"id","name"}]`, images only (by extension: jpg, jpeg, png, webp, heic, heif, gif, bmp, tif, tiff; or mimeType `image/*` on the API path).
  - Without a key: GET `https://drive.google.com/embeddedfolderview?id=<id>`. A 401/403, or a final URL on `accounts.google.com`, raises `DriveError("This folder isn't shared publicly. In Google Drive: Share → General access → Anyone with the link.")`.
  - With a key: Drive API v3 `files.list`, `q='<id>' in parents and trashed=false`, `pageSize=1000`, following `nextPageToken`.
- `drive.DriveSync(photo_dir: Path, http=…)` with `.sync(url, api_key, long_side: int) -> {"count","added","removed","error"}`:
  - Downloads missing files from `https://drive.google.com/thumbnail?id=<id>&sz=s<long_side>` (15 MB cap; must decode with Pillow), saving them as `<id>.jpg` atomically.
  - Removes files no longer listed.
  - Stops with an error when free space on photo_dir is under 500 MB.
  - Keeps the existing files on any listing error.
- `photos.PhotoLibrary(data_dir)` with `.drive_dir`, `.upload_dir`, `.all(source: "drive"|"uploads"|"both") -> list[Path]`, `.add_upload(filename, data: bytes, long_side) -> str` (30 MB cap; Pillow open; `ImageOps.exif_transpose`; RGB; thumbnail to long_side; JPEG q=88; name `<uuid8>__<safe_name>.jpg`; unsupported → ValueError("Use JPEG, PNG or WebP")), `.delete_upload(name) -> bool`, `.uploads() -> list[{name,size}]`.
- `photos.Slideshow` with `.tick(widgets: list[dict], library, now: float) -> bool`. It keeps per-widget `{current: filename, nextAt}`, follows the widget's `interval`, `order` (`shuffle|name|newest`) and `source`, and returns True if anything changed. `.current(widget_id) -> str|None`.
- Photo serving: `GET /photo/<source>/<name>` (localhost or login).

- [ ] **Step 1:** Write the tests:
  - `test_folder_id_from_url` (three forms plus garbage → None)
  - `test_list_folder_parses_fixture` (3 images, folder and pdf skipped)
  - `test_list_folder_not_public` (fake http returning 401 → DriveError message contains "Anyone with the link")
  - `test_list_folder_api_key_pagination`
  - `test_sync_adds_and_removes`
  - `test_sync_keeps_files_on_error`
  - `test_add_upload_resizes_and_rotates` (a 4000×3000 JPEG with EXIF orientation 6 → long side == 1920 and portrait)
  - `test_add_upload_rejects_non_image`
  - `test_slideshow_advances_after_interval`
  - `test_slideshow_empty_library`
- [ ] **Step 2:** Run them and expect FAIL. **Step 3:** Implement, parsing with `html.parser.HTMLParser`. **Step 4:** Pass.
- [ ] **Step 5:** Wire into Runtime and web:
  - jobs: Drive sync every `photos.syncMinutes` and on "Sync now"; slideshow tick each second.
  - routes: `GET /api/photos` (status + uploads), `POST /api/photos/sync`, `POST /api/photos/upload` (multipart, multiple), `DELETE /api/photos/uploads/<name>`.
  - `build_display_state` adds `widgets[id].photo = "/photo/<source>/<name>"`.

  Add web tests `test_upload_requires_login` and `test_photo_route_localhost`.
- [ ] **Step 6:** Commit `feat: drive sync, uploads and slideshow`.

### Task 7: System actions (Wi-Fi, display, timezone, screen power, restart, logs)

**Files:** Create `system.py` and `tests/test_system.py`.

**Interfaces — Produces:** `system.System(data_dir, boot_dir, run=subprocess.run)` and `system.DevSystem(...)`, which has the same methods, logs calls and returns canned data. `Runtime` picks DevSystem when `--dev`. Every command is run as an argv list; nothing goes through a shell.
- `wifi_scan() -> list[{ssid, signal, secure}]` (`wpa_cli -i wlan0 scan` then `scan_results`).
- `wifi_status() -> {ssid, ip, eth_ip}` (`wpa_cli status` and `ip -j -4 addr`).
- `wifi_connect(ssid, password) -> None`. The SSID goes as hex; the PSK is a 64-hex value from `hashlib.pbkdf2_hmac("sha1", pw, ssid, 4096, 32)`; an empty password means `key_mgmt NONE`. Sequence: `add_network`, `set_network`, `enable_network`, `save_config`. The config file is `/data/etc/wpa_supplicant-wlan0.conf`.
- `wifi_forget(ssid) -> None`.
- `set_country(cc)`, which rewrites the `country=` line in the wpa conf.
- `display_modes() -> list[str]`, read from `/sys/class/drm/card*-HDMI-A-*/modes`, deduplicated.
- `set_display_mode(mode: "auto"|"WxH") -> None`. It writes `/data/etc/eglfs.json` (`{"device":"/dev/dri/card?","outputs":[{"name":"HDMI1","mode":mode}]}`, or deletes it for auto) and restarts `display.service`.
- `set_timezone(tz) -> None`. Validates that `/usr/share/zoneinfo/<tz>` exists, replaces the `/data/etc/localtime` symlink, then restarts `display.service`.
- `screen_power(on: bool)`. Off: `systemctl stop display.service`, `echo 4 > /sys/class/graphics/fb0/blank`, then `cec-ctl --to 0 --standby` (errors ignored). On: CEC `--image-view-on`, `echo 0 > blank`, `systemctl start display.service`.
- `restart_app()`, which runs `systemctl restart dashboard.service display.service` detached after 1 s; and `reboot()`.
- `logs(lines=200) -> str` (`journalctl -n N --no-pager`).
- `clock_synced() -> bool`, true when `/run/systemd/timesync/synchronized` exists.
- `boot_rw()`, a context manager that remounts `/boot` rw and then back to ro.
- Runtime schedule job (each 30 s): compute whether now (local) is inside the `[off, on)` window, wrapping midnight. Call `screen_power` only on change. Expose it as the pure function `in_off_window(now: time, off: str, on: str) -> bool`.
- Routes:
  - `GET /api/system/info` (version, ip, modes, clockSynced, freeSpace)
  - `GET /api/wifi/scan`, `POST /api/wifi/connect`, `POST /api/wifi/forget`
  - `POST /api/system/restart`, `POST /api/system/reboot`, `GET /api/system/logs`
  - `GET /api/location/search?q=`
  - `PUT /api/config` side effects:
    - display.mode changed → `set_display_mode`
    - location.timezone changed → `set_timezone`
    - location.country changed → `set_country`

- [ ] **Step 1:** Write the tests with a recording fake `run`:
  - `test_wifi_connect_commands_are_safe` (ssid `My "Home" Wi-Fi ☕`, pw `p@ss "word"` → argv contains a hex ssid and a 64-hex psk, no shell)
  - `test_wifi_scan_parses` (sample `scan_results` text)
  - `test_display_modes_reads_sysfs` (tmp sysfs tree)
  - `test_set_timezone_rejects_bad` (`../../etc/passwd` → ValueError)
  - `test_in_off_window_wraps_midnight` (off 23:00, on 06:00: 23:30 → True, 12:00 → False, 05:59 → True)
- [ ] **Step 2:** Run them and expect FAIL. **Step 3:** Implement. **Step 4:** Pass.
- [ ] **Step 5:** Commit `feat: system actions and screen schedule`.

### Task 8: Updates (upload, GitHub, rollback) and backup/restore

**Files:** Create `updates.py`, `backup.py`, `tests/test_updates.py` and `tests/test_backup.py`.

**Interfaces — Produces:**
- `updates.UpdateError(Exception)`.
- `updates.install_bundle(tar_path: Path, app_root: Path) -> str` returns the installed version. Limits: 200 MB unpacked, 5000 members. Only regular files and dirs; every name must be relative, with no `..` and no drive letter; `VERSION` at the root must match the version regex. It extracts to `app_root/releases/<ver>.tmp`, renames to `releases/<ver>` (replacing an existing one), then sets `app_root/previous` → old current and `app_root/current` → `releases/<ver>`. Both are symlinks on the Pi; in dev on Windows they are a text file holding the relative path, read through `resolve_release(app_root, name) -> Path|None`. Finally it writes `app_root/attempts` = `0`. Any error leaves `current` untouched and removes the `.tmp` dir.
- `updates.prune(app_root)`: keeps only the releases current and previous point at.
- `updates.rollback(app_root) -> str`: swaps current and previous; UpdateError if there is no previous.
- `updates.mark_healthy(app_root)`: deletes `attempts`. Runtime calls it once it has been up for 30 s.
- `updates.github_latest(repo, http=…) -> {"version","notes","asset_url"} | None`: GET `https://api.github.com/repos/<repo>/releases/latest`, strips the leading `v`, and picks the asset named `dashboard-app-*.tar.gz`.
- `updates.is_newer(a, b) -> bool`: compares numeric dot tuples.
- `updates.download(url, dest, http=…, cap=200MB)`.
- `backup.make_backup(data_dir) -> bytes` (zip: `config.json` plus `uploads/*`).
- `backup.restore_backup(data: bytes, data_dir) -> dict`. It validates names (`config.json` or `uploads/<safe_name>` only), the size cap (2 GB total) and the image check per file. The config is normalized. It replaces the uploads dir and returns the config. The password is never included.
- Routes:
  - `GET /api/update/status` (version, previous, latest from a daily cached check)
  - `POST /api/update/upload` (multipart) and `POST /api/update/github`; each installs, responds, then calls `restart_app()`
  - `POST /api/update/rollback`
  - `GET /api/backup` (attachment `dashboard-backup-<date>.zip`) and `POST /api/restore`
- Runtime: a GitHub check every 24 h (errors ignored).

- [ ] **Step 1:** Write the tests, building tarballs in tmp:
  - `test_install_valid_bundle_sets_current_previous`
  - `test_install_rejects_symlink`, `test_install_rejects_dotdot`, `test_install_rejects_absolute`, `test_install_rejects_missing_version`, `test_install_rejects_not_tar` — each asserts current is unchanged and no `.tmp` dir is left
  - `test_rollback_swaps`, `test_prune_keeps_two`
  - `test_is_newer` (`0.10.0` > `0.9.1`)
  - `test_github_latest_picks_asset`
  - `test_backup_roundtrip`
  - `test_restore_rejects_traversal`
- [ ] **Step 2:** Run them and expect FAIL. **Step 3:** Implement, using `tarfile.open(mode="r:gz")`, member checks, and `extractall(filter="data")`. **Step 4:** Pass.
- [ ] **Step 5:** Commit `feat: app updates, rollback, backup and restore`.

### Task 9: Display program (QML)

**Files:** Create `app/display/Main.qml`, `WidgetFrame.qml`, `SetupScreen.qml`, `widgets/*.qml`, `fonts/` (Inter, Noto Naskh Arabic, Roboto Slab, all OFL, with their license files), `icons/*.svg` (10 hand-drawn weather icons) and `scripts/dev.ps1`.

**Interfaces:**
- Consumes: `GET /api/display/state?since=N` and `/photo/...` from Tasks 2–8. The server base URL comes from the context property or env `DASHBOARD_URL` (default `http://127.0.0.1`), passed by the launcher as `Qt.application.arguments[1]` or by an env var read through the `dashboardUrl` context property; the dev runner passes it as a command-line arg.
- Produces: the display behaviour every later task assumes.
  - The **logical stage** is `width × height` = the screen dims swapped for 90/270, rotated about its centre, with padding inset.
  - `scale` multiplies font size and padding by `height/1080 * scale`.
  - Widgets are drawn from `config.widgets`, sorted by `z`, positioned in %.
  - `SetupScreen` shows when `setup.needed`.
  - The "clock not synced" mark shows when `!clockSynced`.
  - Screenshot: while `screenshot.wanted`, every 1 s call `stage.grabToImage(cb, Qt.size(w/2, h/2))` and `result.saveToFile(screenshot.path)`. The server keeps the last bytes that Pillow could decode, and serves those when it reads a half-written file.
  - On connection loss: keep the last state, retry every 2 s.
- Widget specifics, following the spec §7.4 table:
  - Photos: two `Image`s with an opacity crossfade, `asynchronous: true`, `sourceSize` = widget pixel size, `fillMode` from `fit`.
  - Clock: a local `Timer` every 1 s formatting `Qt.formatDateTime`; Hijri from state.
  - News: layouts `rotate` (fades between items from the server index), `list` and `ticker` (a `NumberAnimation` on x). Text uses `textFormat: Text.PlainText`.
  - Weather: icon plus temperature, with `°F` converted in QML.
  - Shalat: rows from state; the next prayer is highlighted; the countdown is `ts - Date.now()`.

- [ ] **Step 1:** Write `scripts/dev.ps1`: starts `python -m dashboard --dev --data devdata --port 8080` and `pyside6-qml app/display/Main.qml -- http://127.0.0.1:8080`.
- [ ] **Step 2:** Implement the QML.
- [ ] **Step 3: Verify visually.** Run the dev server with the default config plus 3 sample photos uploaded, and the QML window at 1920×1080. Open `/api/screenshot` while logged in, then `Read` the screenshot image. Check that every default widget is visible and none overlap wrongly. Repeat with rotation 90 and scale 1.3.
- [ ] **Step 4:** Commit `feat: qml display`.

### Task 10: Settings site

**Files:** Create `app/web/index.html`, `app/web/app.js` and `app/web/style.css`.

**Interfaces:** Consumes every route above. Everything is vanilla JS with no build step and no external CDN, so it works offline on the LAN. `fetch` wrapper `api(method, path, body)` always sends `X-Dashboard: 1` and JSON.

Sections (tabs), per spec §7.5:
- **Login/setup overlay:** setup on first visit, login otherwise.
- **Design:**
  - Preview: an `<img>` refreshing `/api/screenshot?t=` every 1 s while the tab is visible. Overlay boxes are positioned at widget %, select on click, move on pointer-drag, and resize from the corner handle. Snap is 0.5%. During a drag the box moves locally; on release the config PUT is debounced 300 ms.
  - Side panel: a form generated from `/api/schema` (common style + type options), plus add widget (type select), duplicate, delete, bring forward/back, and theme fields.
- **Photos:** Drive link and optional API key ("only needed if not all photos appear"), status, Sync now, upload (multiple), uploads grid with delete.
- **Display:** rotation, resolution select (from `/api/system/info.modes` + auto), scale slider, padding, schedule.
- **Location:** search box → results → pick (sets name/lat/lon/timezone/country), manual lat/lon, timezone field.
- **Network:** status, scan, connect form, forget.
- **Updates:** version, upload, check GitHub + install, rollback, progress text, and a reconnect wait loop after a restart.
- **System:** password change, restart, reboot, logs view, backup download, restore upload.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Verify.** Run the dev server and drive the site with `curl` against every API the page calls. Then check the page loads with no JS syntax errors: `node --check app/web/app.js` if node is present; otherwise load it in PySide6 `QWebEngine`, or skip that check and say so.
- [ ] **Step 3:** Commit `feat: settings site`.

### Task 11: Buildroot OS image

**Files:** Create everything under `os/`, plus `scripts/build-image.sh`.

**Interfaces:**
- Consumes `app/` (copied by post-build into `/usr/share/dashboard/factory`).
- Produces `dist/dashboard-<ver>.img.xz` (MBR: p1 FAT32 64 MB `boot`, p2 ext4 rootfs ~600 MB, p3 ext4 64 MB `data`).

`dashboard_rpi3_defconfig` is derived from `raspberrypi3_64_defconfig`, plus:
- **Init and root:** systemd init (`BR2_INIT_SYSTEMD=y`, `BR2_INIT_SYSTEMD_VAR_FACTORY=y`), networkd, resolved, timesyncd; `BR2_TARGET_GENERIC_HOSTNAME="dashboard"`; root login disabled, no getty (`BR2_TARGET_GENERIC_GETTY` unset); `BR2_ROOTFS_OVERLAY`, post-build and post-image from `os/board/rpi3`; rootfs ext4 768M; `BR2_TARGET_GENERIC_REMOUNT_ROOTFS_RW` unset.
- **Graphics:** Mesa3D gallium vc4 + v3d off, GBM, EGL, GLES; libdrm.
- **Qt:** qt6base (GUI, eglfs, OpenGL ES2, fontconfig, harfbuzz, jpeg, png, network), qt6declarative (Quick), qt6svg, qt6shadertools.
- **Python:** python3 (ssl, zlib, pyexpat, unicodedata, hashlib), python-flask, python-pillow (jpeg, webp, zlib).
- **System packages:** tzdata, ca-certificates, e2fsprogs (resize2fs, e2fsck), util-linux (sfdisk, partx, mount), wpa_supplicant (nl80211, ctrl iface, cli, autoscan), brcmfmac_sdio-firmware-rpi (Wi-Fi), wireless-regdb, libv4l utils (cec-ctl), dejavu fonts.
- **Kernel:** a fragment that keeps the defaults; `CONFIG_DRM_FBDEV_EMULATION=y` is already set in bcm2711.

Board files:
- `config.txt`: `arm_64bit=1`, `kernel=Image`, `dtoverlay=vc4-kms-v3d`, `disable_splash=1`, `gpu_mem=64`, `disable_overscan=1`, `boot_delay=0`.
- `cmdline.txt`: `root=/dev/mmcblk0p2 rootwait ro fsck.repair=yes console=tty3 quiet loglevel=3 logo.nologo vt.global_cursor_default=0 consoleblank=0`.
- `genimage.cfg`: the three partitions above; data is an empty ext4 labelled `data`.

Overlay:
- `/etc/fstab` with `/dev/mmcblk0p3 /data ext4 defaults,noatime,x-systemd.growfs,x-systemd.requires=dashboard-grow.service 0 2` and `/dev/mmcblk0p1 /boot vfat ro,noatime 0 0`.
- `dashboard-grow.service`: oneshot before `data.mount`. If p3 doesn't reach the disk end, runs `sfdisk -N 3 --no-reread` with `,+`, then `partx -u`.
- `dashboard-firstboot.service`: after `data.mount`. Creates `/data/{etc,app,photos,cache,timesync}`, the default wpa conf, and the localtime → UTC link.
- tmpfiles to link `/var/lib/systemd/timesync` → `/data/timesync`.
- Symlinks `/etc/localtime` → `/data/etc/localtime` and `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` → `/data/etc/wpa_supplicant-wlan0.conf`.
- networkd: eth0 (DHCP, `RouteMetric=100`, `MulticastDNS=yes`, `ClientIdentifier=mac`) and wlan0 (`RouteMetric=600`, same).
- `resolved.conf.d` (`MulticastDNS=yes`), `journald.conf.d` (`Storage=volatile`), `system.conf.d` (`RuntimeWatchdogSec=15`).
- `/usr/libexec/dashboard/app-launcher`:
  1. Increment `/data/app/attempts`.
  2. If attempts > 3 and previous exists: roll back via symlink swap and reset attempts. If attempts > 6: use factory.
  3. Pick `DIR` = current if `VERSION` exists, else `/usr/share/dashboard/factory`, and write it to `/run/dashboard/appdir`.
  4. `exec env PYTHONPATH=$DIR/server python3 -m dashboard --data /data --boot /boot --appdir $DIR --port 80`.
- `dashboard.service` (`Restart=always`, `RestartSec=2`).
- `/usr/libexec/dashboard/display-run`: reads appdir; sets `QT_QPA_PLATFORM=eglfs QT_QPA_EGLFS_INTEGRATION=eglfs_kms QT_QPA_EGLFS_HIDECURSOR=1 QT_QPA_EGLFS_DISABLE_INPUT=1 QT_QPA_EGLFS_ALWAYS_SET_MODE=1`, and `QT_QPA_EGLFS_KMS_CONFIG=/data/etc/eglfs.json` if that file exists; runs `dashboard-display $DIR/display/Main.qml http://127.0.0.1`. If that fails within 10 s, it runs the factory QML.
- `display.service` (`After=dashboard.service`, `Restart=always`, `RestartSec=3`).

Package `dashboard-display`: cmake-package, depends on qt6declarative. `main.cpp` creates a `QGuiApplication`, sets the context property `dashboardUrl` = argv[2], loads argv[1], and returns 1 if there are no root objects.

`scripts/build-image.sh` (run as the WSL user, not root):
- clones Buildroot `2026.02.3` to `~/dashboard-build/buildroot` if absent;
- `make BR2_EXTERNAL=<repo>/os O=~/dashboard-build/out dashboard_rpi3_defconfig`, then `make BR2_JLEVEL=6`;
- copies `out/images/sdcard.img` → `dist/dashboard-$(cat app/VERSION).img`, then runs `xz -T0 -9`.

- [ ] **Step 1:** Write the files.
- [ ] **Step 2:** Run `make … dashboard_rpi3_defconfig`, then grep `.config` for each required symbol. Expect each symbol present and `=y`.
- [ ] **Step 3:** Start the full build in the background and log to `~/dashboard-build/build.log`. Expect `out/images/sdcard.img` to exist on completion. Fix any failures and re-run (incremental).
- [ ] **Step 4: Inspect the image.** `sfdisk -l` shows 3 partitions; loop-mount p2 read-only and check that the launchers, units, factory app and `/usr/bin/dashboard-display` exist; `file` on the binary reports aarch64.
- [ ] **Step 5:** Commit `feat: buildroot os image`.

### Task 12: Release tooling, user guide, GitHub

**Files:** Create `scripts/make-update.sh`, `scripts/release.sh`, `docs/USER-GUIDE.md` and `README.md`.

- `make-update.sh`: `tar -czf dist/dashboard-app-<ver>.tar.gz -C app VERSION server display web`, excluding `__pycache__`. Verify it with `install_bundle` into a tmp dir: `python -c` one-liner.
- `release.sh <ver>`: `gh release create v<ver> dist/dashboard-app-<ver>.tar.gz dist/dashboard-<ver>.img.xz --notes-file …`.
- USER-GUIDE covers:
  - flashing with Raspberry Pi Imager ("Use custom")
  - Ethernet first boot
  - opening `http://dashboard.local` and setting the password
  - making the Drive folder public
  - Wi-Fi
  - location
  - design editor
  - updates (upload / GitHub / rollback)
  - backup before reflashing
  - password reset file
  - troubleshooting with the Logs view
- [ ] **Step 1:** Write the files. Run `make-update.sh` and expect the bundle to install cleanly in the tmp check.
- [ ] **Step 2:** `gh repo create home-dashboard --public --source . --push`. Check that `git ls-files` shows no data, photos or Drive id first. Then run `release.sh 0.1.0`.
- [ ] **Step 3:** Commit `docs: user guide and release tooling`.

### Task 13: Final verification

- [ ] Run `pytest -q` and expect all pass.
- [ ] Run the dev server and QML display end-to-end again, and Read a screenshot.
- [ ] Rebuild the image incrementally so it contains the final app; inspect it as in Task 11 Step 4.
- [ ] Dispatch one fresh reviewer (most capable model) over the whole branch, then fix what it finds.
