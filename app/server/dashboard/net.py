"""Capped, timed HTTP GETs. `http` is injectable so tests never touch the network."""
import contextlib
import urllib.request

UA = "home-dashboard/1.0"


def urlopen(url, timeout=10):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)


def read_capped(resp, cap: int) -> bytes:
    data = resp.read(cap + 1)
    if len(data) > cap:
        raise ValueError("response too large")
    return data


def get_bytes(url, http=None, cap=1024 * 1024, timeout=10) -> bytes:
    with contextlib.closing((http or urlopen)(url, timeout=timeout)) as r:
        return read_capped(r, cap)
