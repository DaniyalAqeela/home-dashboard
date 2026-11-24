"""Revision counter the display long-polls on. Anything that changes what the
screen should show calls bump()."""
import threading
import time

SCREENSHOT_WINDOW = 5.0


class DisplayState:
    def __init__(self):
        self.rev = 0
        self._cond = threading.Condition()
        self._wanted_until = 0.0

    def bump(self) -> None:
        with self._cond:
            self.rev += 1
            self._cond.notify_all()

    def wait(self, since: int, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self.rev <= since:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cond.wait(left)
            return self.rev

    def want_screenshot(self) -> None:
        rising = not self.screenshot_wanted()
        self._wanted_until = time.monotonic() + SCREENSHOT_WINDOW
        if rising:
            self.bump()

    def screenshot_wanted(self) -> bool:
        return time.monotonic() < self._wanted_until
