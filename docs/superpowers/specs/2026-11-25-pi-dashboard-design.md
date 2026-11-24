# Home Dashboard for Raspberry Pi 3B — Design

Date: 2026-11-25
Status: draft for approval

## 1. Intent

A Raspberry Pi 3B, flashed with one image file, that boots straight into a
full-screen family dashboard and runs it 24/7. Family photos fill most of the
screen; a clock, RSS headlines, weather and Shalat (prayer) times sit around
them. Everything is set up and designed from a settings website served by the
Pi on the home network, with a live picture of the real screen. Fixes ship as
small update files (uploaded in the browser, or one click from GitHub) without
reflashing.

The owner is the only admin; viewers are family in the room. Success = it
boots to a good-looking dashboard with no keyboard attached, keeps running for
months, and every design tweak is done from a browser.

## 2. Goals

- One `.img.xz` file, flashed with Raspberry Pi Imager / balenaEtcher, that
  boots only the dashboard: no desktop, no browser, no login prompt, no boot
  text.
- Widgets: **Photos**, **Clock** (with optional Hijri date), **News (RSS)**,
  **Weather**, **Shalat times**. Each is an independent widget instance with
  its own position, size, layer order, style and options. More than one
  instance of a type is allowed. New widget types arrive via app updates.
- Settings website on port 80 (`http://dashboard.local`, IP also shown on
  screen during setup), password protected.
- Live preview in the settings site: a picture of the actual Pi screen,
  refreshed about once a second, with outlines to select, drag and resize
  widgets.
- Display orientation (0/90/180/270), resolution, UI scale and edge padding
  (TV overscan) editable in the settings site.
- Network: Ethernet works out of the box (DHCP). Wi-Fi is added later from the
  settings site (scan, connect, forget). Ethernet keeps working regardless.
- Photos from a **public** Google Drive folder link ("Anyone with the link"),
  300–1,500 photos expected, plus photos uploaded in the settings site.
- Screen off on a nightly schedule.
- Updates: upload an update file in the browser, or one-click install of the
  latest release from a **public** GitHub repo. Automatic rollback if an update
  fails to start.
- Screen language: English.

## 3. Non-goals

- No web browser on the Pi, no SSH, no desktop, no general-purpose OS use.
  For debugging on real hardware, the settings site shows the system logs.
- No over-the-air updates of the OS layer (kernel, Qt, drivers). Those need a
  reflash. The design puts as much as possible into the updatable app layer,
  including all screen-drawing code, so a reflash is rare (see §7.6).
- No private Google Drive access, no Google sign-in, no API keys.
- No audio or adhan sound, no touch input, no other languages, no access from
  outside the home network.

## 4. Anti-goals (would be a failure even if it "works")

- After a power cut or an internet outage, the screen shows a blank page, an
  error or a login prompt. It must keep showing cached photos and news, the
  correct local clock and prayer times.
- An update leaves the Pi unreachable or unusable with no way back short of
  reflashing.
- The SD card corrupts from 24/7 writes or power cuts.
- The preview shows something other than what the real screen shows.
- All the design work is lost when a reflash is needed.

## 5. Constraints

- Hardware: Raspberry Pi 3B with 4× Cortex-A53, **1 GB RAM**, VideoCore IV
  GPU (Mesa `vc4`, **GLES 2.0 only**), 100 Mbit Ethernet, 2.4 GHz Wi-Fi, HDMI.
- Screen: any HDMI screen (monitor or TV, landscape or portrait).
- Power and internet can drop at any time.
- Build machine: the owner's Windows 11 PC with WSL2 Ubuntu 26.04 (12 cores,
  ~7 GB RAM to WSL, ~900 GB free). Root in WSL via `wsl -u root`. No Docker.
- GitHub CLI is logged in as the owner. The repo will be public, so it must
  never contain secrets, photos or personal config.

## 6. Approaches considered

**Base OS** (owner's choice: Buildroot)

| | Option | Trade-off |
|---|---|---|
| | Customized official Raspberry Pi OS Lite | Best proven, apt available, OS fixes updatable. Bigger, ~30 s boot, writable root needs SD-wear care. |
| **✓** | **Buildroot custom Linux** | Small, fast boot, **read-only root** (power-cut safe). No package manager; OS-layer fixes need a reflash. |

**Screen drawing** (owner's choice: native)

| | Option | Trade-off |
|---|---|---|
| | Browser engine (WPE WebKit, full-screen only) | The settings preview is the identical page running live in the browser. Risky on Pi 3B (GLES2, unproven in Buildroot, possible stutter), and a build of several hours. |
| **✓** | **Native Qt Quick (QML) program drawing straight to the screen (eglfs/KMS)** | Smooth GPU drawing, proven on Pi 3B, faster build. The preview is a picture of the real screen (~1/s), so it can't drift. Edits show within about a second rather than instantly. |
| | Native Python + pygame/SDL | Simplest stack, but weaker text and anti-aliasing and less styling. Qt Quick gives richer looks for the same effort. |

## 7. Design

### 7.1 Overall shape

Two layers, kept strictly apart:

1. **OS layer (read-only; changes only by reflash).** Buildroot image with:
   Pi firmware and kernel, systemd, Mesa vc4, Qt 6 (base with eglfs/KMS,
   declarative/Quick, svg, plus a generous set of standard Quick modules so
   that future QML needs no reflash), Python 3 with Flask and Pillow,
   wpa_supplicant and the Pi Wi-Fi firmware, CA certificates, tzdata and a
   base font. It also holds a few tiny stable pieces:
   - the **display launcher**, a minimal C++ program that loads QML from the
     current app release;
   - the **app launcher**, with rollback;
   - first-boot setup.
2. **App layer (updatable).** One folder containing the Python server, the
   display QML (all widgets), the settings site, vendored pure-Python
   libraries, fonts, icons and an optional post-install hook. It ships in the
   image as the "factory" version and is replaced by update files.

```
HDMI <- display program (Qt Quick, eglfs/KMS, QML from /data/app/current)
              |  long-poll HTTP on 127.0.0.1: config + state; uploads screenshots on request
     Python server (Flask, port 80) -- config.json, photo cache, news/weather cache,
              |                        prayer times, system actions (Wi-Fi, display, schedule, updates)
Phone/PC browser -> http://dashboard.local -> settings site (+ live screen picture)
```

### 7.2 SD card layout

| Partition | Format | Mount | Contents |
|---|---|---|---|
| 1 boot | FAT32 (~64 MB) | `/boot`, read-only (remounted rw only when needed) | Pi firmware, kernel, `config.txt`, `cmdline.txt`. Visible on Windows. Also where the owner can drop a `reset-password` file. |
| 2 root | ext4, **mounted read-only** | `/` | OS layer + factory app copy. |
| 3 data | ext4, grown to fill the card on first boot | `/data` | App releases, `config.json`, photo cache, uploaded photos, Wi-Fi config, persistent machine-id, timezone link, saved clock. |

- Logs: journald volatile (RAM only). `/tmp` and runtime state: tmpfs.
- State writes are atomic (write temp, fsync, rename). `/data` mounted
  `noatime`, fsck on boot.
- machine-id persisted on `/data`, so the DHCP client ID (and the Pi's IP)
  stays the same across reboots.
- `/etc/localtime` is a symlink to `/data/etc/localtime`. timesyncd's saved
  clock lives on `/data`, so after a power cut without internet the time
  resumes from the last known value instead of the build date.

### 7.3 Boot and the screen

- Kernel `quiet`, no rainbow or logo, no console or login on HDMI (getty on
  tty1 masked, console moved off the screen). The hardware watchdog is
  enabled via systemd, so a hard hang reboots the Pi.
- `dashboard.service` (Python server) starts first. Then `display.service`
  runs the display launcher on eglfs/KMS with `Restart=always`.
  - Resolution comes from the display settings via the eglfs KMS config
    (output mode).
  - Input handling is disabled: there is no input.
- **First boot / not yet set up:** the screen shows "Open
  http://dashboard.local or http://<IP> on your phone or PC", updating when
  the IP is known. After the password is set, it shows the default layout.
- **Default layout** (useful before any design work):
  - photos take the left ~70%;
  - on the right: a clock with date and Hijri date, Shalat times with the next
    prayer highlighted, and the weather;
  - a bottom bar showing one headline and its short description at a time,
    fading to the next.

### 7.4 Display program and widgets

- Written in QML (with its built-in JavaScript), loaded at runtime from
  `/data/app/current/display/`, so all screen code is updatable. If the
  current release's QML fails to load, the launcher falls back to the factory
  QML.
- The display gets config and live state from the server by long-polling
  `127.0.0.1`. Changes apply within about a second, without a restart. An app
  update restarts the display program.
- Positions and sizes are stored as **percentages of the screen**, so a
  change of resolution or orientation keeps the layout proportional.
  - Orientation: the QML root is rotated on the GPU, unless eglfs rotation
    proves better on hardware.
  - UI scale multiplies all font sizes and padding.
  - Edge padding insets the whole layout.
- **Server-owned state:** the server picks the current photo and headline
  and computes prayer times and the Hijri date. The display only draws. It
  keeps its last state if the server is briefly away, and draws the clock
  itself every second.
- Photos: two image layers crossfading on the GPU, decoded asynchronously,
  pre-sized to the screen by the server.
- Feed text is always drawn as plain text, never as rich text or HTML.
- **Screenshots for the preview:** only while a settings page is showing the
  preview, the display grabs its own window about once a second. It grabs
  the logical, unrotated layout, so the outlines line up. It sends a
  downscaled JPEG to the server, and the settings page shows the latest one.
  When nobody is watching, no screenshots are taken.

Common options for every widget: position, size, layer order, visible on/off,
background colour and opacity, corner radius, padding, font family, font size,
text colour, alignment, text shadow.

| Widget | Type-specific options |
|---|---|
| Photos | Slide interval, order (shuffle / by name / newest first), crossfade duration, fit (cover / contain + fill colour), sources (Drive, uploads, or both). |
| Clock | 12/24 h, show seconds, date format, show Hijri date (with ±day adjustment for local moon sighting), Hijri in Latin or Arabic script. |
| News | Feed URLs (several). Layout: single rotating item, list of N, or continuous scrolling ticker. Rotation interval, show source name, description length. Headline + short description, HTML stripped. |
| Weather | Current conditions + N-day forecast, °C/°F, location name. Bundled icons. |
| Shalat | Calculation method (MWL, ISNA, Egypt, Umm al-Qura, Karachi, Singapore/Kemenag/JAKIM-style, Turkey, Tehran, Dubai, Kuwait, Qatar, Moonsighting Committee, custom angles), Asr madhab (Shafi'i / Hanafi), per-prayer minute adjustments, which times to show (Imsak, Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha), highlight next prayer + countdown, 12/24 h. |

- **Location is one global setting:** a city search via Open-Meteo
  geocoding, or manual lat/lon. It sets the weather location, the prayer-time
  coordinates, the system timezone and the Wi-Fi country code at once.
- Prayer times and the Hijri date (Umm al-Qura) are computed **on the Pi by
  the server** with vendored pure-Python libraries, so they work with no
  internet.
- Weather: Open-Meteo (no API key), fetched every 30 min, cached on `/data`.
- News: feeds fetched every 15 min, RSS 2.0 and Atom parsed with the Python
  standard library, cached. Feeds are untrusted input: size and time limits,
  text-only output.
- Fonts: a small set bundled in the app (including one with Arabic script
  for the Hijri option), loaded by the QML, so the look doesn't depend on the
  OS layer.

### 7.5 Settings site

A plain web app served by the Python server and used from any phone or PC
browser. The password is set on first visit and stored as a salted hash on
`/data`; login uses a session cookie. Every endpoint that changes anything,
and the screenshot endpoint (it shows family photos), requires login. If the
password is forgotten: put an empty file named `reset-password` on the SD
card's boot partition (visible on Windows) and boot. The Pi clears the
password and deletes the file.

Sections:

- **Design (main screen):**
  - The live screen picture, scaled to fit, with an outline over each widget.
    Click an outline to select it, drag to move, and drag the handles to
    resize. Snap-to-grid helps alignment. The outline moves instantly, and
    the picture catches up within about a second.
  - A side panel edits the selected widget's options.
  - Add, duplicate, delete and reorder widgets.
  - Global theme: background colour, default font.
  - Changes save automatically.
- **Photos:**
  - The Drive folder link, with a status line (photo count, last sync, last
    error), "Sync now" and the sync interval.
  - Upload photos (JPEG/PNG/WebP, EXIF-rotated and resized on upload), and a
    list with delete.
- **Display:** orientation, resolution (the list read from the connected
  screen), UI scale, edge padding, screen-off schedule (off time / on time).
- **Location & time:** city search or lat/lon, timezone (auto-filled from
  location, overridable), the Pi's current time.
- **Network:**
  - The current connection and IP.
  - Wi-Fi: scan, connect with a password, forget.
  - The hostname is fixed as `dashboard`. This is a shortcut and can become a
    setting.
- **Updates:**
  - The current version.
  - Upload an update file.
  - "Check GitHub" shows the latest release and its notes, with an "Install"
    button.
  - "Roll back to previous version".
  - The Pi checks GitHub daily and shows a badge when there's a new version.
    It never installs on its own.
- **System:**
  - Change password, restart dashboard, reboot.
  - Logs: recent system and app log lines.
  - **Backup:** download one file holding the settings and uploaded photos.
  - **Restore:** upload that file, for example after a reflash, so design
    work is never lost.

### 7.6 Updates

**App update file:** `dashboard-app-<version>.tar.gz`, containing the app
folder (server, display QML, settings site), a `VERSION` file and an optional
`post-install.sh` hook. The hook runs once after install and may change things
on `/data` only (for example, extra settings the launchers read from `/data`).
This is how most system-level fixes avoid a reflash.

Install flow (same for upload and GitHub):

1. Validate the file: size limit, real tar.gz, no absolute paths, no `..` or
   links escaping the folder, `VERSION` present.
2. Extract it to `/data/app/releases/<version>`. Switch the `current`
   pointer, remember `previous`, and mark the update "pending".
3. Restart the server and the display. The new version must pass its health
   check and stay up for about 30 s; it then clears "pending".
4. If it crashes repeatedly while pending, the launcher (in the read-only OS
   layer) switches back to `previous` automatically. If no release works at
   all, it runs the **factory** app from the read-only root. The settings
   site stays reachable throughout.

Kept on the card: the current and previous releases, plus factory. Older
releases are deleted.

**GitHub:** a public repo on the owner's account (`home-dashboard`). Releases
carry the app update file and the full `.img.xz` for reflashing. The Pi uses
the public GitHub releases API, so no token is needed.

**OS-layer fixes** (kernel, Qt, drivers): build a new image, attach it to a
release, reflash, then Restore the backup.

### 7.7 Photos from Google Drive

- The owner pastes a folder link shared as "Anyone with the link".
- **Listing:** the server reads the folder's public embedded view
  (`drive.google.com/embeddedfolderview?id=<id>`) and extracts file IDs and
  names, skipping non-images and subfolders. **It must be verified early
  that a ~1,500-file folder lists completely** (pagination). If it doesn't,
  the builder finds another public, keyless listing route before building
  on it.
- **Download:** Drive's public thumbnail endpoint, sized to the screen. It
  returns JPEG for most formats, including iPhone HEIC. New files are
  downloaded; files removed from the folder are removed from the cache.
- **Space:** 300–1,500 photos at screen size is roughly 150–750 MB, which
  fits on any reasonable card. No eviction cycle. As a safety stop, syncing
  pauses with a visible warning if `/data` drops below ~500 MB free.
- **If listing or download fails** (Google changes the page, or the internet
  is down): the slideshow keeps using cached photos, and the Photos section
  shows the error. The fix ships as an app update.

### 7.8 Screen-off schedule

- **At the off time:** stop the display program, turn the HDMI output off
  (DRM DPMS off), and send HDMI-CEC standby if the TV supports it.
- **At the on time:** CEC wake, then start the display program.
- Side effect: the display program restarts daily, which guards against slow
  memory leaks.
- The schedule follows the Pi's local timezone. A reboot inside the off
  window keeps the screen off.
- The exact blanking method needs verifying on real hardware (§9).

### 7.9 Network

- Ethernet: DHCP via systemd-networkd, always on.
- Wi-Fi: wpa_supplicant, with its config on `/data`. The settings site scans
  and connects via `wpa_cli`. When both are connected, Ethernet is preferred.
- mDNS: `dashboard.local`, advertised by systemd-resolved, or by avahi if
  resolved's responder proves unreliable.
- Time: systemd-timesyncd. The display shows a small "clock not synced" mark
  until NTP succeeds after boot.

### 7.10 Security

- The settings site and the screenshots require login. The display program
  talks only to `127.0.0.1`.
- Uploads (photos, update files, backups) are size-limited and validated.
  Archive extraction is path-checked.
- Shortcut: the server runs as root on the Pi, because it needs Wi-Fi,
  display mode, reboot and updates. This is acceptable because an
  authenticated admin can install arbitrary code by design. Upgrade to a
  non-root server with narrow helpers if the Pi is ever exposed beyond the
  home network.
- LAN only, plain HTTP (no certificates on a home LAN).
- The public repo contains no secrets. All personal data lives on `/data`.

### 7.11 Repo layout and build

```
app/        updatable app: server (Python), display (QML), settings site (HTML/JS), vendored libs, fonts, icons
os/         Buildroot external tree: defconfig, board files, rootfs overlay, genimage, post-build,
            display-launcher package (C++)
scripts/    build-image.sh (WSL), make-update.sh, release.sh (gh)
tests/      Python tests
docs/       design, user guide (flash, first setup, Drive sharing, updates, backup, password reset)
```

- `scripts/build-image.sh` runs inside WSL Ubuntu, on the Linux filesystem
  (not `/mnt/c`). It fetches a pinned Buildroot release and builds with
  `BR2_EXTERNAL=os`. The output is `dashboard-<version>.img.xz`.
  - The first build takes an estimated 1–2 hours; later builds are
    incremental.
- `scripts/make-update.sh` packs `app/` into `dashboard-app-<version>.tar.gz`.
  It takes seconds and needs no Buildroot.
- `scripts/release.sh` creates a GitHub release with both files.
- **Dev mode:** the server runs on the PC, with system actions stubbed. The
  same QML runs on the PC with PySide6's `pyside6-qml` (or a desktop build of
  the launcher) against the dev server. The settings site opens in a normal
  browser. Almost all work is testable without the Pi.

## 8. Left to the builder

- **Buildroot release:** prefer the 2026.02.x LTS branch if its Qt 6
  packages support eglfs/KMS on vc4 well; otherwise use the latest stable.
  aarch64 (`raspberrypi3_64`) unless 32-bit proves necessary.
- **Packages and config:** the exact Buildroot packages, the Qt module list,
  and the kernel/firmware config (`vc4-kms-v3d`, CMA size, Mesa vc4 +
  GBM/EGL/GLES2).
- **How the launcher detects "crashes repeatedly":** a systemd restart
  counter, `OnFailure=`, or a counter file.
- **Choice of libraries:** the pure-Python prayer-time and Hijri libraries,
  and the editor's drag/resize code.
- **Look and feel:** default fonts, colours, icon set, and the exact default
  layout.
- **Test scope:**
  - unit tests for the Drive parser (fixture HTML), the feed parser, prayer
    times (against known published times), the update installer (bad
    archives, rollback), config validation and login;
  - a QEMU boot smoke test of the image if feasible (no vc4 GPU in QEMU, so
    server and boot only).

## 9. Risks and validation order

1. **Hardware first.** The plan starts with a small **test image**: Qt
   display with a clock, a photo crossfade, rotation, resolution switch,
   screenshot grab, and screen off/on. The owner flashes it on the Pi 3B and
   reports back before the rest is built on top. If anything there fails
   badly, stop and ask the owner before changing approach (builder's call,
   noted for the owner).
2. **Unofficial Drive listing** can break or truncate. It's verified early
   with a real ~1,500-file folder. Mitigations: cache, visible error,
   app-update fix.
3. **Screen-off method** (DPMS after the display program stops, CEC) needs
   tuning on the owner's screen.
4. **No hardware in the loop:** everything Pi-specific is verified by the
   owner flashing the image and reporting back. Expect a couple of rounds.
5. **The first image build** may hit memory limits in WSL. If it does, limit
   build parallelism or raise WSL memory via `.wslconfig`.
