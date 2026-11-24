import io
import json
import tarfile

import pytest

from conftest import H, REMOTE
from dashboard import updates
from dashboard.updates import UpdateError, install_bundle, resolve_release


def make_tar(path, version="0.2.0", extra=None, files=None):
    files = files if files is not None else {"VERSION": version + "\n", "server/dashboard/__init__.py": "",
                                             "display/Main.qml": "Item {}\n"}
    with tarfile.open(path, "w:gz") as tf:
        for name, text in files.items():
            data = text.encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        for ti in extra or []:
            tf.addfile(ti)
    return path


def current_version(root):
    d = resolve_release(root, "current")
    return (d / "VERSION").read_text().strip() if d else None


def assert_untouched(root, before):
    assert current_version(root) == before
    assert not list((root / "releases").glob("*.tmp"))


def test_install_valid_bundle_sets_current_previous(tmp_path):
    root = tmp_path / "app"
    assert install_bundle(make_tar(tmp_path / "a.tgz", "0.2.0"), root) == "0.2.0"
    assert current_version(root) == "0.2.0" and resolve_release(root, "previous") is None
    assert (root / "attempts").read_text() == "0"
    assert install_bundle(make_tar(tmp_path / "b.tgz", "0.3.0"), root) == "0.3.0"
    assert current_version(root) == "0.3.0"
    assert (resolve_release(root, "previous") / "VERSION").read_text().strip() == "0.2.0"


def test_first_install_keeps_factory_as_previous(tmp_path):
    factory = tmp_path / "factory"
    factory.mkdir()
    (factory / "VERSION").write_text("0.1.0")
    root = tmp_path / "app"
    install_bundle(make_tar(tmp_path / "a.tgz", "0.2.0"), root, factory=factory)
    assert resolve_release(root, "previous") == factory
    assert updates.rollback(root) == "0.1.0"


@pytest.mark.parametrize("bad", ["symlink", "dotdot", "absolute", "missing_version", "not_tar", "drive_letter",
                                 "bad_version", "no_server"])
def test_install_rejects_bad_bundles(tmp_path, bad):
    root = tmp_path / "app"
    install_bundle(make_tar(tmp_path / "good.tgz", "0.2.0"), root)
    p = tmp_path / "bad.tgz"
    base = {"VERSION": "0.9.0", "server/dashboard/__init__.py": ""}
    if bad == "symlink":
        link = tarfile.TarInfo("server/evil")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        make_tar(p, files=base, extra=[link])
    elif bad == "dotdot":
        make_tar(p, files={**base, "../escape.txt": "x"})
    elif bad == "absolute":
        make_tar(p, files={**base, "/tmp/abs.txt": "x"})
    elif bad == "drive_letter":
        make_tar(p, files={**base, "C:/win.txt": "x"})
    elif bad == "missing_version":
        make_tar(p, files={"server/dashboard/__init__.py": ""})
    elif bad == "bad_version":
        make_tar(p, files={**base, "VERSION": "1.0; rm -rf /"})
    elif bad == "no_server":
        make_tar(p, files={"VERSION": "0.9.0", "README": "hi"})
    else:
        p.write_bytes(b"this is not a tarball")
    with pytest.raises(UpdateError):
        install_bundle(p, root)
    assert_untouched(root, "0.2.0")
    assert not (tmp_path / "escape.txt").exists()


def test_install_rejects_too_many_members(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "MAX_MEMBERS", 3)
    files = {"VERSION": "0.2.0", "server/dashboard/__init__.py": "", "a": "", "b": ""}
    with pytest.raises(UpdateError):
        install_bundle(make_tar(tmp_path / "x.tgz", files=files), tmp_path / "app")


def test_rollback_swaps(tmp_path):
    root = tmp_path / "app"
    install_bundle(make_tar(tmp_path / "a.tgz", "0.2.0"), root)
    with pytest.raises(UpdateError):
        updates.rollback(root)
    install_bundle(make_tar(tmp_path / "b.tgz", "0.3.0"), root)
    assert updates.rollback(root) == "0.2.0"
    assert current_version(root) == "0.2.0"
    assert (resolve_release(root, "previous") / "VERSION").read_text().strip() == "0.3.0"


def test_prune_keeps_two(tmp_path):
    root = tmp_path / "app"
    for i, v in enumerate(["0.2.0", "0.3.0", "0.4.0"]):
        install_bundle(make_tar(tmp_path / f"{i}.tgz", v), root)
    (root / "releases" / "junk.tmp").mkdir()
    updates.prune(root)
    assert sorted(p.name for p in (root / "releases").iterdir()) == ["0.3.0", "0.4.0"]


def test_reinstall_same_version(tmp_path):
    root = tmp_path / "app"
    install_bundle(make_tar(tmp_path / "a.tgz", "0.2.0"), root)
    install_bundle(make_tar(tmp_path / "b.tgz", "0.3.0"), root)
    install_bundle(make_tar(tmp_path / "c.tgz", "0.3.0"), root)
    assert current_version(root) == "0.3.0"
    assert (resolve_release(root, "previous") / "VERSION").read_text().strip() == "0.2.0"


def test_mark_healthy(tmp_path):
    root = tmp_path / "app"
    install_bundle(make_tar(tmp_path / "a.tgz"), root)
    updates.mark_healthy(root)
    assert not (root / "attempts").exists()
    updates.mark_healthy(root)  # idempotent


def test_is_newer():
    assert updates.is_newer("0.10.0", "0.9.1")
    assert not updates.is_newer("0.9.1", "0.10.0")
    assert not updates.is_newer("0.2.0", "0.2.0")
    assert not updates.is_newer("garbage", "0.1.0")
    assert updates.is_newer("1.0", "0.9.9")


def test_github_latest_picks_asset():
    payload = {"tag_name": "v0.4.2", "body": "Fixes", "assets": [
        {"name": "dashboard-0.4.2.img.xz", "browser_download_url": "https://github.com/x/img"},
        {"name": "dashboard-app-0.4.2.tar.gz", "browser_download_url": "https://github.com/x/app"}]}
    urls = []

    def http(url, timeout=None):
        urls.append(url)
        return io.BytesIO(json.dumps(payload).encode())
    assert updates.github_latest("me/home-dashboard", http=http) == \
        {"version": "0.4.2", "notes": "Fixes", "asset_url": "https://github.com/x/app"}
    assert urls == ["https://api.github.com/repos/me/home-dashboard/releases/latest"]


def test_github_latest_without_releases():
    import urllib.error

    def http404(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    assert updates.github_latest("me/none", http=http404) is None


def test_download_caps_size(tmp_path):
    big = io.BytesIO(b"x" * 1000)
    with pytest.raises(UpdateError):
        updates.download("https://example.com/x", tmp_path / "f", http=lambda u, timeout=None: big, cap=100)
    assert not (tmp_path / "f").exists()
    with pytest.raises(UpdateError):
        updates.download("http://insecure/x", tmp_path / "f", http=lambda u, timeout=None: io.BytesIO(b""))


def test_update_upload_route(admin, rt, tmp_path):
    tar = make_tar(tmp_path / "u.tgz", "0.5.0").read_bytes()
    r = admin.post("/api/update/upload", data={"bundle": (io.BytesIO(tar), "u.tar.gz")}, headers=H,
                   environ_overrides=REMOTE, content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["version"] == "0.5.0"
    assert any("restart" in c for c in rt.system.calls)
    st = admin.get("/api/update/status", environ_overrides=REMOTE).json
    assert st["version"] == rt.version and st["installed"] == "0.5.0"
    bad = admin.post("/api/update/upload", data={"bundle": (io.BytesIO(b"nope"), "x.tar.gz")}, headers=H,
                     environ_overrides=REMOTE, content_type="multipart/form-data")
    assert bad.status_code == 400 and "error" in bad.json
