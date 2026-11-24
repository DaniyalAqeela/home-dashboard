#!/usr/bin/env bash
# Publish a GitHub release that dashboards can install with one click (Settings → Updates).
# Usage: scripts/release.sh <version> [notes-file]   — app/VERSION must already say <version>.
set -euo pipefail
cd "$(dirname "$0")/.."
ver=${1:?usage: release.sh <version> [notes-file]}
[ "$(tr -d '[:space:]' < app/VERSION)" = "$ver" ] || { echo "app/VERSION is not $ver" >&2; exit 1; }
bash scripts/make-update.sh
assets=("dist/dashboard-app-$ver.tar.gz")
[ -f "dist/dashboard-$ver.img.xz" ] && assets+=("dist/dashboard-$ver.img.xz")
notes=${2:-}
if [ -z "$notes" ]; then notes=$(mktemp); echo "Dashboard version $ver" > "$notes"; fi
gh release create "v$ver" "${assets[@]}" --title "Dashboard $ver" --notes-file "$notes"
