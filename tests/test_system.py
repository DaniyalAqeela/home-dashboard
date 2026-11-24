import json
import re
import subprocess
from datetime import time

import pytest

from conftest import H, REMOTE
from dashboard import system
from dashboard.system import System, in_off_window

SCAN = """bssid / frequency / signal level / flags / ssid
aa:bb:cc:dd:ee:01\t2437\t-71\t[WPA2-PSK-CCMP][ESS]\tHome
aa:bb:cc:dd:ee:02\t5180\t-45\t[WPA2-PSK-CCMP][ESS]\tHome
aa:bb:cc:dd:ee:03\t2412\t-60\t[ESS]\tCafe Free
aa:bb:cc:dd:ee:04\t2412\t-80\t[WPA2-PSK-CCMP][ESS]\t
aa:bb:cc:dd:ee:05\t2412\t-50\t[WPA2-SAE-CCMP][ESS]\tTea \\xe2\\x98\\x95
"""


class FakeRun:
    def __init__(self, replies=None):
        self.calls, self.replies = [], replies or {}

    def __call__(self, argv, **kw):
        assert isinstance(argv, list) and not kw.get("shell")
        self.calls.append(argv)
        out = ""
        for key, reply in self.replies.items():
            if key in argv:
                out = reply
        return subprocess.CompletedProcess(argv, 0, out, "")


def make(tmp_path, replies=None):
    run = FakeRun(replies)
    s = System(tmp_path / "data", tmp_path / "boot", run=run)
    s.sys_root, s.zoneinfo, s.sleep = tmp_path / "sys", tmp_path / "zoneinfo", lambda _: None
    s.etc.mkdir(parents=True)
    return s, run


def test_wifi_connect_commands_are_safe(tmp_path):
    s, run = make(tmp_path, {"add_network": "3\n", "list_networks": "network id / ssid / bssid / flags\n"})
    ssid, pw = 'My "Home" Wi-Fi ☕', 'p@ss "word"'
    s.wifi_connect(ssid, pw)
    flat = [a for c in run.calls for a in c]
    assert ssid.encode().hex() in flat
    psk = [c[-1] for c in run.calls if "psk" in c][0]
    assert re.fullmatch(r"[0-9a-f]{64}", psk)
    import hashlib
    assert psk == hashlib.pbkdf2_hmac("sha1", pw.encode(), ssid.encode(), 4096, 32).hex()
    assert pw not in flat and ssid not in flat
    assert [c for c in run.calls if "save_config" in c]


def test_wifi_connect_open_and_validation(tmp_path):
    s, run = make(tmp_path, {"add_network": "0\n", "list_networks": ""})
    s.wifi_connect("Cafe Free", "")
    assert ["key_mgmt", "NONE"] == [c for c in run.calls if "key_mgmt" in c][0][-2:]
    with pytest.raises(ValueError):
        s.wifi_connect("x", "short")
    with pytest.raises(ValueError):
        s.wifi_connect("", "longenough")


def test_wifi_connect_replaces_same_ssid(tmp_path):
    listing = "network id / ssid / bssid / flags\n0\tOther\tany\t\n2\tHome\tany\t[CURRENT]\n"
    s, run = make(tmp_path, {"add_network": "3\n", "list_networks": listing})
    s.wifi_connect("Home", "password1")
    assert ["wpa_cli", "-i", "wlan0", "remove_network", "2"] in run.calls
    assert ["wpa_cli", "-i", "wlan0", "remove_network", "0"] not in run.calls


def test_wifi_scan_parses(tmp_path):
    s, _ = make(tmp_path, {"scan_results": SCAN})
    nets = s.wifi_scan()
    assert nets == [{"ssid": "Home", "signal": -45, "secure": True},
                    {"ssid": "Tea ☕", "signal": -50, "secure": True},
                    {"ssid": "Cafe Free", "signal": -60, "secure": False}]


def test_set_country(tmp_path):
    s, run = make(tmp_path)
    conf = s.etc / "wpa_supplicant-wlan0.conf"
    conf.write_text("ctrl_interface=/run/wpa_supplicant\nupdate_config=1\ncountry=US\nnetwork={\n}\n")
    s.set_country("id")
    assert "country=ID\n" in conf.read_text() and "country=US" not in conf.read_text()
    assert ["wpa_cli", "-i", "wlan0", "set", "country", "ID"] in run.calls
    with pytest.raises(ValueError):
        s.set_country("XYZ\nnetwork={")


def test_display_modes_reads_sysfs(tmp_path):
    s, _ = make(tmp_path)
    d = s.sys_root / "class" / "drm" / "card1-HDMI-A-1"
    d.mkdir(parents=True)
    (d / "modes").write_text("1920x1080\n1280x720\n1920x1080\n720x480\n")
    assert s.display_modes() == ["1920x1080", "1280x720", "720x480"]


def test_set_display_mode_writes_eglfs_json(tmp_path):
    s, run = make(tmp_path)
    (s.sys_root / "class" / "drm" / "card1-HDMI-A-1").mkdir(parents=True)
    s.set_display_mode("1280x720")
    cfg = json.loads((s.etc / "eglfs.json").read_text())
    assert cfg == {"device": "/dev/dri/card1", "hwcursor": False, "outputs": [{"name": "HDMI1", "mode": "1280x720"}]}
    assert ["systemctl", "restart", "display.service"] in run.calls
    s.set_display_mode("auto")
    assert not (s.etc / "eglfs.json").exists()
    with pytest.raises(ValueError):
        s.set_display_mode("1280x720; reboot")


def test_set_timezone_rejects_bad(tmp_path):
    s, run = make(tmp_path)
    (s.zoneinfo / "Asia").mkdir(parents=True)
    (s.zoneinfo / "Asia" / "Jakarta").write_text("tz")
    for bad in ("../../etc/passwd", "/etc/passwd", "Asia/Nowhere", "", "Asia/../../x"):
        with pytest.raises(ValueError):
            s.set_timezone(bad)
    assert run.calls == []


def test_screen_power_commands(tmp_path):
    s, run = make(tmp_path)
    (s.sys_root / "class" / "graphics" / "fb0").mkdir(parents=True)
    s.screen_power(False)
    assert run.calls[0] == ["systemctl", "stop", "display.service"]
    assert (s.sys_root / "class" / "graphics" / "fb0" / "blank").read_text() == "4"
    assert any("--standby" in c for c in run.calls)
    run.calls.clear()
    s.screen_power(True)
    assert run.calls[-1] == ["systemctl", "start", "display.service"]
    assert (s.sys_root / "class" / "graphics" / "fb0" / "blank").read_text() == "0"


def test_in_off_window_wraps_midnight():
    assert in_off_window(time(23, 30), "23:00", "06:00") is True
    assert in_off_window(time(12, 0), "23:00", "06:00") is False
    assert in_off_window(time(5, 59), "23:00", "06:00") is True
    assert in_off_window(time(6, 0), "23:00", "06:00") is False
    assert in_off_window(time(13, 0), "12:00", "14:00") is True
    assert in_off_window(time(13, 0), "12:00", "12:00") is False


def test_screen_schedule_turns_off_once(rt, monkeypatch):
    cfg = rt.config
    cfg["display"]["schedule"] = {"enabled": True, "off": "00:00", "on": "23:59"}
    rt.update_config(cfg)
    calls = []
    monkeypatch.setattr(rt.system, "screen_power", lambda on: calls.append(on))
    monkeypatch.setattr(system, "in_off_window", lambda now, off, on: True)
    rt.screen_tick()
    rt.screen_tick()
    assert calls == [False]
    monkeypatch.setattr(system, "in_off_window", lambda now, off, on: False)
    rt.screen_tick()
    assert calls == [False, True]


def test_config_side_effects(rt, monkeypatch):
    calls = []
    for name in ("set_display_mode", "set_timezone", "set_country"):
        monkeypatch.setattr(rt.system, name, lambda v, n=name: calls.append((n, v)))
    cfg = rt.config
    cfg["display"]["mode"] = "1280x720"
    cfg["location"]["timezone"] = "Asia/Jakarta"
    cfg["location"]["country"] = "ID"
    rt.update_config(cfg)
    assert sorted(calls) == [("set_country", "ID"), ("set_display_mode", "1280x720"),
                             ("set_timezone", "Asia/Jakarta")]


def test_system_routes(admin):
    info = admin.get("/api/system/info", environ_overrides=REMOTE).json
    assert {"version", "urls", "modes", "clockSynced", "freeSpace", "screenOff"} <= set(info)
    assert "networks" in admin.get("/api/wifi/scan", environ_overrides=REMOTE).json
    r = admin.post("/api/wifi/connect", json={"ssid": "Home", "password": "short"}, headers=H,
                   environ_overrides=REMOTE)
    assert r.status_code == 400
    assert admin.post("/api/system/restart", headers=H, environ_overrides=REMOTE).status_code == 200
    assert isinstance(admin.get("/api/system/logs", environ_overrides=REMOTE).json["text"], str)
