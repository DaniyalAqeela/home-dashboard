import threading
import time

from dashboard import state as state_mod
from dashboard.state import DisplayState


def test_wait_returns_immediately_when_newer():
    s = DisplayState()
    s.bump()
    t = time.monotonic()
    assert s.wait(0, 5) == 1
    assert time.monotonic() - t < 0.5


def test_wait_times_out():
    s = DisplayState()
    assert s.wait(s.rev, 0.05) == s.rev


def test_wait_wakes_on_bump():
    s = DisplayState()
    threading.Timer(0.05, s.bump).start()
    t = time.monotonic()
    assert s.wait(0, 5) == 1
    assert time.monotonic() - t < 2


def test_screenshot_wanted_expires(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(state_mod.time, "monotonic", lambda: now[0])
    s = DisplayState()
    assert s.screenshot_wanted() is False
    rev = s.rev
    s.want_screenshot()
    assert s.screenshot_wanted() is True and s.rev == rev + 1
    s.want_screenshot()
    assert s.rev == rev + 1  # only the rising edge bumps
    now[0] += 6
    assert s.screenshot_wanted() is False
