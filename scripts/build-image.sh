#!/bin/bash
# Build the flashable image. Run inside WSL (as your normal user, not root):
#   bash scripts/build-image.sh            # full or incremental build
#   bash scripts/build-image.sh menuconfig # any other Buildroot make target
# Output: dist/dashboard-<version>.img.xz
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BR_VERSION=2026.02.3
WORK="${DASHBOARD_BUILD_DIR:-$HOME/dashboard-build}"
BR="$WORK/buildroot-$BR_VERSION"
OUT="$WORK/out"
JOBS="${JOBS:-6}"   # Qt/Mesa compiles are memory hungry; 6 jobs fit in ~7 GB

mkdir -p "$WORK" "$REPO/dist"
# Buildroot can't handle spaces in paths (and /mnt/c is slow), so build from a copy.
SRC="$WORK/src"
mkdir -p "$SRC"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$REPO/os/" "$SRC/os/"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$REPO/app/" "$SRC/app/"
if [ ! -d "$BR" ]; then
	git clone -q --depth 1 -b "$BR_VERSION" https://gitlab.com/buildroot.org/buildroot.git "$BR"
fi
# Downloads are shared between builds.
export BR2_DL_DIR="$WORK/dl"

if [ ! -f "$OUT/.config" ]; then
	make -C "$BR" BR2_EXTERNAL="$SRC/os" O="$OUT" dashboard_rpi3_defconfig
fi

if [ $# -gt 0 ]; then
	make -C "$BR" O="$OUT" "$@"
	exit 0
fi

make -C "$BR" O="$OUT" BR2_JLEVEL="$JOBS"

VERSION="$(tr -d '[:space:]' < "$REPO/app/VERSION")"
IMG="$REPO/dist/dashboard-$VERSION.img"
cp "$OUT/images/sdcard.img" "$IMG"
rm -f "$IMG.xz"
xz -T0 -6 "$IMG"
echo "Built $IMG.xz"
