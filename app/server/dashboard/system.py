"""Everything that touches the Pi's OS. DevSystem stands in on a PC."""
import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("dashboard.system")


class System:
    def __init__(self, data_dir: Path, boot_dir: Path, run=subprocess.run):
        self.data_dir = Path(data_dir)
        self.boot_dir = Path(boot_dir)
        self.run = run

    def _out(self, *argv, timeout=15) -> str:
        r = self.run(list(argv), capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""

    def ips(self) -> list:
        try:
            data = json.loads(self._out("ip", "-j", "-4", "addr") or "[]")
        except ValueError:
            return []
        return [a["local"] for i in data if i.get("ifname") != "lo"
                for a in i.get("addr_info", []) if a.get("local")]

    def urls(self) -> list:
        return ["http://dashboard.local"] + [f"http://{ip}" for ip in self.ips()]

    def clock_synced(self) -> bool:
        return Path("/run/systemd/timesync/synchronized").exists()


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

    def urls(self):
        return [f"http://localhost:{self.port}"]

    def clock_synced(self):
        return True
