"""Wires config, state, auth, system and the background jobs together."""
import copy
import logging
import threading
import time
import traceback
from pathlib import Path

from . import config as config_mod
from .auth import Auth
from .state import DisplayState
from .system import DevSystem, System

log = logging.getLogger("dashboard")


class Runtime:
    def __init__(self, data_dir, boot_dir, app_dir, dev=False, port=80):
        self.data_dir = Path(data_dir).resolve()  # Flask and the display resolve relative paths elsewhere
        self.boot_dir = Path(boot_dir).resolve()
        self.app_dir = Path(app_dir).resolve()
        self.dev = dev
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self.config = config_mod.load(self.config_path)
        self._saved = copy.deepcopy(self.config)  # hooks diff against this, even if rt.config was edited in place
        self.state = DisplayState()
        self.auth = Auth(self.data_dir, self.boot_dir)
        self.system = DevSystem(self.data_dir, self.boot_dir, port) if dev else System(self.data_dir, self.boot_dir)
        self.version = (self.app_dir / "VERSION").read_text().strip() if (self.app_dir / "VERSION").exists() else "dev"
        self.screenshot_path = (self.data_dir / "screen.jpg") if dev else Path("/run/dashboard/screen.jpg")
        self.started = time.monotonic()
        # Per widget type: fn(widget, now) -> dict merged into the display state.
        self.providers = {}
        # Called with (old, new) config after every save.
        self.config_hooks = []
        self._jobs = []
        self._lock = threading.Lock()

    def update_config(self, new: dict) -> dict:
        with self._lock:
            old = self._saved
            self.config = config_mod.save(self.config_path, new)
            self._saved = copy.deepcopy(self.config)
        for hook in self.config_hooks:
            try:
                hook(old, self.config)
            except Exception:
                log.exception("config hook failed")
        self.state.bump()
        return self.config

    def build_display_state(self) -> dict:
        now = time.time()
        widgets = {}
        for w in self.config["widgets"]:
            fn = self.providers.get(w["type"])
            try:
                widgets[w["id"]] = fn(w, now) if fn else {}
            except Exception:
                log.exception("provider for %s failed", w["type"])
                widgets[w["id"]] = {}
        return {
            "rev": self.state.rev,
            "version": self.version,
            "config": self.config,
            "setup": {"needed": not self.auth.is_set(), "urls": self.system.urls()},
            "screenshot": {"wanted": self.state.screenshot_wanted(), "path": str(self.screenshot_path)},
            "clockSynced": self.system.clock_synced(),
            "widgets": widgets,
        }

    def every(self, seconds, fn, first_delay: float = 0, background: bool = False) -> list:
        """Run fn every `seconds` (a number or a callable returning one) on the job thread.
        background=True runs it in its own thread (network work), never two at once."""
        job = [seconds, fn, time.monotonic() + first_delay, background, threading.Event()]
        self._jobs.append(job)
        return job

    @staticmethod
    def trigger(job) -> None:
        """Run a job on the next tick of the job thread."""
        job[2] = 0

    def run_jobs_once(self) -> None:
        now = time.monotonic()
        for job in self._jobs:
            seconds, fn, due, background, running = job
            if now < due:
                continue
            job[2] = now + (seconds() if callable(seconds) else seconds)
            if not background:
                self._run_job(fn)
            elif not running.is_set():
                running.set()
                threading.Thread(target=self._run_job, args=(fn, running), daemon=True).start()

    @staticmethod
    def _run_job(fn, running=None) -> None:
        try:
            fn()
        except Exception:
            log.error("job %s failed:\n%s", getattr(fn, "__name__", fn), traceback.format_exc())
        finally:
            if running is not None:
                running.clear()

    def start_background(self) -> None:
        def loop():
            while True:
                self.run_jobs_once()
                time.sleep(1)

        threading.Thread(target=loop, name="jobs", daemon=True).start()
