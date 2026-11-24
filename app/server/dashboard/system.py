"""Everything that touches the Pi's OS. Every command is an argv list (never a
shell). DevSystem stands in on a PC: it logs actions and returns canned data."""
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import fsutil

log = logging.getLogger("dashboard.system")
WPA = ["wpa_cli", "-i", "wlan0"]
MODE_RE = r"\d{3,5}x\d{3,5}(@\d{2,3})?"
TZ_RE = r"[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}"


def in_off_window(now, off: str, on: str) -> bool:
    """True when `now` (a datetime.time) is in [off, on), wrapping midnight."""
    o, n = (tuple(map(int, s.split(":"))) for s in (off, on))
    t = (now.hour, now.minute)
    if o == n:
        return False
    return o <= t < n if o < n else (t >= o or t < n)


def _unescape_ssid(s: str) -> str:
    """wpa_cli prints SSIDs printf-escaped (\\xNN, \\\\, \\")."""
    out, i = bytearray(), 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            if s[i + 1] == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", s[i + 2:i + 4]):
                out.append(int(s[i + 2:i + 4], 16))
                i += 4
                continue
            out += s[i + 1].encode()
            i += 2
            continue
        out += s[i].encode()
        i += 1
    return out.decode("utf-8", "replace")


class System:
    def __init__(self, data_dir: Path, boot_dir: Path, run=subprocess.run):
        self.data_dir = Path(data_dir)
        self.boot_dir = Path(boot_dir)
        self.etc = self.data_dir / "etc"
        self.run = run
        self.sys_root = Path("/sys")
        self.zoneinfo = Path("/usr/share/zoneinfo")
        self.sleep = time.sleep

    def _out(self, *argv, timeout=15, check=False) -> str:
        r = self.run(list(argv), capture_output=True, text=True, timeout=timeout)
        if check and (r.returncode != 0 or r.stdout.strip().endswith("FAIL")):
            raise RuntimeError(f"{argv[0]} failed: {(r.stdout or r.stderr).strip()[:200]}")
        return r.stdout if r.returncode == 0 else ""

    def _quiet(self, *argv):
        try:
            self.run(list(argv), capture_output=True, text=True, timeout=10)
        except Exception as e:  # e.g. no CEC adapter
            log.info("%s: %s", argv[0], e)

    # --- network -------------------------------------------------------------
    def ips(self, ifname=None) -> list:
        try:
            data = json.loads(self._out("ip", "-j", "-4", "addr") or "[]")
        except ValueError:
            return []
        return [a["local"] for i in data if i.get("ifname") != "lo" and (ifname is None or i.get("ifname") == ifname)
                for a in i.get("addr_info", []) if a.get("local")]

    def urls(self) -> list:
        return ["http://dashboard.local"] + [f"http://{ip}" for ip in self.ips()]

    def wifi_scan(self) -> list:
        self._out(*WPA, "scan")
        self.sleep(3)
        best = {}
        for line in self._out(*WPA, "scan_results").splitlines()[1:]:
            parts = line.split("\t", 4)
            if len(parts) < 5:
                continue
            ssid = _unescape_ssid(parts[4])
            if not ssid:
                continue  # hidden network
            try:
                signal = int(parts[2])
            except ValueError:
                continue
            if ssid not in best or signal > best[ssid]["signal"]:
                best[ssid] = {"ssid": ssid, "signal": signal, "secure": any(k in parts[3] for k in ("WPA", "WEP", "SAE"))}
        return sorted(best.values(), key=lambda n: -n["signal"])

    def wifi_status(self) -> dict:
        st = dict(line.split("=", 1) for line in self._out(*WPA, "status").splitlines() if "=" in line)
        connected = st.get("wpa_state") == "COMPLETED"
        return {"ssid": _unescape_ssid(st.get("ssid", "")) if connected else None,
                "ip": (self.ips("wlan0") or [None])[0], "eth_ip": (self.ips("eth0") or [None])[0]}

    def _network_ids(self, ssid) -> list:
        ids = []
        for line in self._out(*WPA, "list_networks").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 2 and _unescape_ssid(parts[1]) == ssid:
                ids.append(parts[0])
        return ids

    def wifi_connect(self, ssid: str, password: str) -> None:
        raw = (ssid or "").encode("utf-8")
        if not 1 <= len(raw) <= 32:
            raise ValueError("Wi-Fi name must be 1 to 32 bytes")
        if password and not 8 <= len(password) <= 63:
            raise ValueError("Wi-Fi password must be 8 to 63 characters")
        for nid in self._network_ids(ssid):
            self._out(*WPA, "remove_network", nid)
        nid = self._out(*WPA, "add_network", check=True).strip().splitlines()[-1].strip()
        if not nid.isdigit():
            raise RuntimeError("wpa_supplicant isn't running (is there a Wi-Fi adapter?)")
        self._out(*WPA, "set_network", nid, "ssid", raw.hex(), check=True)  # unquoted = hex SSID
        if password:
            psk = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), raw, 4096, 32).hex()
            self._out(*WPA, "set_network", nid, "psk", psk, check=True)  # 64 hex = raw PSK, no quoting issues
        else:
            self._out(*WPA, "set_network", nid, "key_mgmt", "NONE", check=True)
        self._out(*WPA, "enable_network", nid, check=True)
        self._out(*WPA, "save_config", check=True)

    def wifi_forget(self, ssid: str) -> None:
        for nid in self._network_ids(ssid):
            self._out(*WPA, "remove_network", nid)
        self._out(*WPA, "save_config")

    def set_country(self, cc: str) -> None:
        cc = (cc or "").upper()
        if not re.fullmatch(r"[A-Z]{2}", cc):
            raise ValueError("Country must be a two-letter code")
        conf = self.etc / "wpa_supplicant-wlan0.conf"
        lines = [ln for ln in (conf.read_text().splitlines() if conf.exists() else []) if not ln.startswith("country=")]
        at = next((i + 1 for i, ln in enumerate(lines) if ln.startswith("update_config")), 0)
        lines.insert(at, f"country={cc}")
        fsutil.atomic_write_bytes(conf, ("\n".join(lines) + "\n").encode())
        self._out(*WPA, "set", "country", cc)

    # --- display -------------------------------------------------------------
    def _hdmi_connectors(self):
        return sorted((self.sys_root / "class" / "drm").glob("card*-HDMI-A-*"))

    def display_modes(self) -> list:
        modes = []
        for c in self._hdmi_connectors():
            try:
                modes += (c / "modes").read_text().split()
            except OSError:
                pass
        return list(dict.fromkeys(modes))

    def set_display_mode(self, mode: str) -> None:
        path = self.etc / "eglfs.json"
        if mode == "auto":
            path.unlink(missing_ok=True)
        else:
            if not re.fullmatch(MODE_RE, mode or ""):
                raise ValueError("Resolution must look like 1920x1080")
            conns = self._hdmi_connectors()
            name = conns[0].name if conns else "card0-HDMI-A-1"
            card, num = re.match(r"(card\d+)-HDMI-A-(\d+)", name).groups()
            fsutil.atomic_write_json(path, {"device": f"/dev/dri/{card}", "hwcursor": False,
                                            "outputs": [{"name": f"HDMI{num}", "mode": mode}]})
        self._out("systemctl", "restart", "display.service")

    def set_timezone(self, tz: str) -> None:
        if not re.fullmatch(TZ_RE, tz or "") or not (self.zoneinfo / tz).is_file():
            raise ValueError(f"Unknown timezone {tz!r}")
        link, tmp = self.etc / "localtime", self.etc / ".localtime.tmp"
        tmp.unlink(missing_ok=True)
        os.symlink(self.zoneinfo / tz, tmp)
        os.replace(tmp, link)
        self._out("systemctl", "restart", "display.service")  # Qt reads the zone at start

    def _blank(self, value: str):
        try:
            (self.sys_root / "class" / "graphics" / "fb0" / "blank").write_text(value)
        except OSError as e:
            log.info("fb blank: %s", e)

    def screen_power(self, on: bool) -> None:
        if on:
            self._quiet("cec-ctl", "--playback", "--to", "0", "--image-view-on")
            self._blank("0")
            self._out("systemctl", "start", "display.service")
        else:
            self._out("systemctl", "stop", "display.service")
            self._blank("4")
            self._quiet("cec-ctl", "--playback", "--to", "0", "--standby")

    # --- maintenance -----------------------------------------------------------
    def restart_app(self) -> None:
        # a transient timer outlives dashboard.service, so the restart isn't killed with us
        self._out("systemd-run", "--on-active=1", "systemctl", "restart", "dashboard.service", "display.service")

    def reboot(self) -> None:
        self._out("systemd-run", "--on-active=1", "systemctl", "reboot")

    def logs(self, lines=200) -> str:
        n = max(1, min(int(lines), 2000))
        return self._out("journalctl", "-n", str(n), "--no-pager", "-o", "short-iso", timeout=20)

    def clock_synced(self) -> bool:
        return Path("/run/systemd/timesync/synchronized").exists()

    def free_space(self) -> int:
        return shutil.disk_usage(self.data_dir).free

    @contextlib.contextmanager
    def boot_rw(self):
        self._out("mount", "-o", "remount,rw", str(self.boot_dir))
        try:
            yield
        finally:
            os.sync()
            self._out("mount", "-o", "remount,ro", str(self.boot_dir))


class DevSystem(System):
    """Logs actions instead of doing them, so the server runs on a PC."""

    def __init__(self, data_dir, boot_dir, port=8080):
        super().__init__(data_dir, boot_dir, run=self._fake_run)
        self.port = port
        self.calls = []

    def _fake_run(self, argv, **kw):
        self.calls.append(argv)
        log.info("dev: would run %s", argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def _log(self, *what):
        self.calls.append(list(what))
        log.info("dev: %s", what)

    def urls(self):
        return [f"http://localhost:{self.port}"]

    def clock_synced(self):
        return True

    def wifi_scan(self):
        return [{"ssid": "Home Wi-Fi", "signal": -48, "secure": True}, {"ssid": "Neighbour", "signal": -77, "secure": True}]

    def wifi_status(self):
        return {"ssid": None, "ip": None, "eth_ip": "127.0.0.1"}

    def wifi_connect(self, ssid, password):
        if password and not 8 <= len(password) <= 63:
            raise ValueError("Wi-Fi password must be 8 to 63 characters")
        self._log("wifi_connect", ssid)

    def wifi_forget(self, ssid):
        self._log("wifi_forget", ssid)

    def set_country(self, cc):
        self._log("set_country", cc)

    def display_modes(self):
        return ["1920x1080", "1280x720"]

    def set_display_mode(self, mode):
        self._log("set_display_mode", mode)

    def set_timezone(self, tz):
        self._log("set_timezone", tz)

    def screen_power(self, on):
        self._log("screen_power", on)

    def logs(self, lines=200):
        return "(dev mode: no system journal)\n"

    @contextlib.contextmanager
    def boot_rw(self):
        yield
