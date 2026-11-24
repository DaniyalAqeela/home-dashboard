"""App updates: install a release bundle (.tar.gz) beside the running one, flip
the `current` pointer, keep `previous` for rollback (spec section 7.6).

Layout under app_root (/data/app on the Pi):
  releases/<version>/   one directory per installed release
  current, previous     symlinks to a release (a text file holding the path where
                        symlinks aren't available, i.e. dev on Windows)
  attempts              boot counter used by app-launcher for automatic rollback
"""
import json
import os
import re
import shutil
import tarfile
import urllib.error
import zlib
from pathlib import Path

from . import fsutil, net

VERSION_RE = r"\d+(\.\d+){1,3}"
MAX_UNPACKED = 200 * 1024 * 1024
MAX_MEMBERS = 5000
MAX_DOWNLOAD = 200 * 1024 * 1024
NOT_BUNDLE = "That isn't a dashboard update file (expected the dashboard-app-<version>.tar.gz from a release)."


class UpdateError(Exception):
    pass


def resolve_release(app_root, name):
    p = Path(app_root) / name
    if p.is_symlink():
        target = os.readlink(p)
    elif p.is_file():
        target = p.read_text().strip()
    else:
        return None
    d = Path(app_root) / target
    return d if (d / "VERSION").is_file() else None


def _version_of(d):
    return (d / "VERSION").read_text().strip() if d else None


def _point(app_root, name, target):
    root = Path(app_root)
    link = root / name
    if target is None:
        if link.is_symlink() or link.exists():
            link.unlink()
        return
    try:
        rel = Path(target).relative_to(root).as_posix()
    except ValueError:
        rel = str(target)
    tmp = root / f".{name}.new"
    try:
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        os.symlink(rel, tmp)
        os.replace(tmp, link)
    except OSError:  # no symlinks (Windows dev): pointer file
        fsutil.atomic_write_bytes(link, rel.encode())


def _clean_name(m) -> str:
    name = m.name
    if "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise UpdateError(f"Update file has an unsafe path: {name!r}")
    while name.startswith("./"):
        name = name[2:]
    if ".." in name.split("/"):
        raise UpdateError(f"Update file has an unsafe path: {name!r}")
    if not (m.isfile() or m.isdir()):
        raise UpdateError("Update file contains links or special files, which aren't allowed.")
    return name


def install_bundle(tar_path, app_root, factory=None) -> str:
    root = Path(app_root)
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tarfile.open(tar_path, "r:gz") as tf:
            members, names, total, version_member = [], set(), 0, None
            for m in tf:
                if len(members) >= MAX_MEMBERS:
                    raise UpdateError("Update file has too many files.")
                name = _clean_name(m)
                total += m.size
                if total > MAX_UNPACKED:
                    raise UpdateError("Update file is too large when unpacked.")
                members.append(m)
                if m.isfile():
                    names.add(name)
                    if name == "VERSION":
                        version_member = m
            if version_member is None:
                raise UpdateError("Update file has no VERSION file.")
            version = tf.extractfile(version_member).read(64).decode("utf-8", "replace").strip()
            if not re.fullmatch(VERSION_RE, version):
                raise UpdateError(f"Update file has an invalid VERSION: {version[:20]!r}")
            if "server/dashboard/__init__.py" not in names:
                raise UpdateError(NOT_BUNDLE)
            tmp = releases / f"{version}.tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            tf.extractall(tmp, members=members, filter="data")
    except UpdateError:
        _cleanup(tmp)
        raise
    except (tarfile.TarError, OSError, EOFError, zlib.error) as e:
        _cleanup(tmp)
        raise UpdateError(NOT_BUNDLE if tmp is None else f"Couldn't unpack the update: {e}") from None

    final = releases / version
    current = resolve_release(root, "current")
    same = current is not None and current.resolve() == final.resolve()
    if final.exists():
        old = releases / f"{version}.old"
        shutil.rmtree(old, ignore_errors=True)
        final.rename(old)
        tmp.rename(final)
        shutil.rmtree(old, ignore_errors=True)
    else:
        tmp.rename(final)
    if same:
        previous = resolve_release(root, "previous")
    elif current is not None:
        previous = current
    else:
        previous = factory if factory and (Path(factory) / "VERSION").is_file() else None
    _point(root, "previous", previous)
    _point(root, "current", final)
    fsutil.atomic_write_bytes(root / "attempts", b"0")
    (root / "rolled-back").unlink(missing_ok=True)
    prune(root)
    return version


def _cleanup(tmp):
    if tmp is not None:
        shutil.rmtree(tmp, ignore_errors=True)


def prune(app_root) -> None:
    root = Path(app_root)
    keep = {d.resolve() for d in (resolve_release(root, "current"), resolve_release(root, "previous")) if d}
    for d in (root / "releases").iterdir() if (root / "releases").is_dir() else []:
        if d.resolve() not in keep:
            shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink(missing_ok=True)


def rollback(app_root) -> str:
    root = Path(app_root)
    current, previous = resolve_release(root, "current"), resolve_release(root, "previous")
    if previous is None:
        raise UpdateError("There is no previous version to go back to.")
    _point(root, "current", previous)
    _point(root, "previous", current)
    fsutil.atomic_write_bytes(root / "attempts", b"0")
    return _version_of(previous)


def mark_healthy(app_root) -> None:
    (Path(app_root) / "attempts").unlink(missing_ok=True)


def is_newer(a, b) -> bool:
    try:
        ta, tb = (tuple(int(x) for x in str(v).split(".")) for v in (a, b))
    except ValueError:
        return False
    n = max(len(ta), len(tb))
    return ta + (0,) * (n - len(ta)) > tb + (0,) * (n - len(tb))


def github_latest(repo, http=None):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        d = json.loads(net.get_bytes(url, http, cap=1024 * 1024, timeout=15))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # no releases yet
        raise UpdateError(f"GitHub error {e.code}") from None
    asset = next((a["browser_download_url"] for a in d.get("assets", [])
                  if re.fullmatch(r"dashboard-app-.+\.tar\.gz", a.get("name", ""))), None)
    return {"version": str(d.get("tag_name", "")).lstrip("v"), "notes": str(d.get("body") or "")[:4000],
            "asset_url": asset}


def download(url, dest, http=None, cap=MAX_DOWNLOAD) -> None:
    if not str(url).startswith("https://"):
        raise UpdateError("Refusing to download an update over plain HTTP.")
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    total = 0
    try:
        r = (http or net.urlopen)(url, timeout=60)
        try:
            with open(part, "wb") as f:
                while chunk := r.read(1 << 16):
                    total += len(chunk)
                    if total > cap:
                        raise UpdateError("Update download is too large.")
                    f.write(chunk)
        finally:
            r.close()
        os.replace(part, dest)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except OSError as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Download failed: {e}") from None
