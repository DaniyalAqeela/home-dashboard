#!/bin/bash
# Runs after all packages are installed into TARGET_DIR, before the rootfs image
# is made. Copies the factory app and wires the read-only root to /data.
set -eu

BOARD_DIR="$(dirname "$0")"
APP_SRC="${BR2_EXTERNAL_DASHBOARD_PATH}/../app"
FACTORY="${TARGET_DIR}/usr/share/dashboard/factory"

# Factory copy of the app (the fallback that can never be broken by an update).
rm -rf "${FACTORY}"
mkdir -p "${FACTORY}"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "${APP_SRC}/" "${FACTORY}/"
"${HOST_DIR}/bin/python3" -m compileall -q -j 0 "${FACTORY}/server" || true

# Writable bits of /etc live on /data.
ln -sfn /data/etc/localtime "${TARGET_DIR}/etc/localtime"
mkdir -p "${TARGET_DIR}/etc/wpa_supplicant" "${TARGET_DIR}/data" "${TARGET_DIR}/boot"
ln -sfn /data/etc/wpa_supplicant-wlan0.conf "${TARGET_DIR}/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"

# Launchers must be executable whatever the checkout did to modes.
chmod 0755 "${TARGET_DIR}"/usr/libexec/dashboard/*

# Enable our units.
WANTS="${TARGET_DIR}/etc/systemd/system/multi-user.target.wants"
mkdir -p "${WANTS}"
for u in dashboard-prepare.service dashboard.service display.service; do
	ln -sfn "../${u}" "${WANTS}/${u}"
done
ln -sfn /usr/lib/systemd/system/wpa_supplicant@.service "${WANTS}/wpa_supplicant@wlan0.service"

# No consoles or logins anywhere.
rm -f "${TARGET_DIR}"/etc/systemd/system/getty.target.wants/*
ln -sfn /dev/null "${TARGET_DIR}/etc/systemd/system/getty@tty1.service"
ln -sfn /dev/null "${TARGET_DIR}/etc/systemd/system/serial-getty@ttyAMA0.service"
ln -sfn /dev/null "${TARGET_DIR}/etc/systemd/system/serial-getty@ttyS0.service"
