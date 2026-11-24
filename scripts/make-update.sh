#!/usr/bin/env bash
# Build the app update bundle: dist/dashboard-app-<version>.tar.gz
# Upload it in Settings â†’ Updates, or attach it to a GitHub release (scripts/release.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
ver=$(tr -d '[:space:]' < app/VERSION)
mkdir -p dist
out="dist/dashboard-app-$ver.tar.gz"
tar --exclude=__pycache__ --exclude='*.pyc' -czf "$out" -C app VERSION server display web
# self-check: the bundle must pass the same validation the dashboard runs before installing
check='import sys, tempfile; sys.path.insert(0, "app/server")
from dashboard.updates import install_bundle
print("ok, installs as version", install_bundle(sys.argv[1], tempfile.mkdtemp()))'
python3 -c "$check" "$out" 2>/dev/null || python -c "$check" "$out"  # python3 is a Store stub on some Windows PCs
echo "$out"
