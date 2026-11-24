# Home Dashboard

A flashable Raspberry Pi 3B system that boots straight into a family dashboard:
Google Drive photo slideshow, clock with Hijri date, RSS news, weather and Shalat
times. Everything is set up from a password-protected settings website on the LAN
(`http://dashboard.local`) with a live, drag-and-drop preview of the real screen.

**Using it:** see [docs/USER-GUIDE.md](docs/USER-GUIDE.md).

## How it's built

| Part | Where | What |
|---|---|---|
| OS | `os/` | Buildroot external tree. aarch64, read-only root, `/data` partition for settings and photos, systemd, mDNS. |
| Server | `app/server/dashboard/` | Python + Flask on port 80. Settings, Drive sync, feeds, weather, prayer times, updates. |
| Screen | `app/display/` | Qt Quick (QML) on EGLFS/KMS. No browser. Draws `/api/display/state`. |
| Settings site | `app/web/` | Vanilla JS. No build step, no CDN. |

The app (`app/`) updates independently of the OS. Releases live in
`/data/app/releases/<version>`, and a boot-attempt counter rolls a bad update back
automatically.

## Developing on a PC

```powershell
pip install -r requirements-dev.txt     # Flask, Pillow, pytest, PySide6
python -m pytest tests -q
.\scripts\dev.ps1                       # server on http://localhost:8080 + the screen in a window
```

`--dev` mode logs system actions (Wi-Fi, reboot, display mode) instead of running them.

## Building the SD-card image

Use Linux or WSL2 (Ubuntu) with about 25 GB free. The first build takes a few hours.

```bash
bash scripts/build-image.sh          # → dist/dashboard-<version>.img.xz
```

## Releasing an update

1. Bump `app/VERSION`.
2. Run `bash scripts/make-update.sh` to build `dist/dashboard-app-<version>.tar.gz`. It self-checks the bundle.
3. Run `bash scripts/release.sh <version>` to create a GitHub release. Dashboards offer it under Settings → Updates.

## Licences

The dashboard code is MIT. It bundles adhanpy (MIT), hijridate (MIT), Inter and Noto
Naskh Arabic (SIL OFL 1.1) and Roboto Slab (Apache 2.0). Their licence files are in
`app/display/fonts/` and next to the vendored packages.
