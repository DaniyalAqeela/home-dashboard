import io
import json
import zipfile

import pytest
from PIL import Image

from conftest import H, REMOTE
from dashboard import backup, config


def jpeg():
    b = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(b, "JPEG")
    return b.getvalue()


def setup_data(d):
    (d / "photos" / "uploads").mkdir(parents=True)
    (d / "photos" / "uploads" / "abc__kids.jpg").write_bytes(jpeg())
    cfg = config.default_config()
    cfg["location"]["name"] = "Home"
    config.save(d / "config.json", cfg)
    (d / "auth.json").write_text('{"hash": "secret"}')


def test_backup_roundtrip(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    setup_data(src)
    out = tmp_path / "b.zip"
    backup.make_backup(src, out)
    names = zipfile.ZipFile(out).namelist()
    assert sorted(names) == ["config.json", "uploads/abc__kids.jpg"]  # never auth.json
    (dst / "photos" / "uploads").mkdir(parents=True)
    (dst / "photos" / "uploads" / "old.jpg").write_bytes(jpeg())
    cfg = backup.restore_backup(out, dst)
    assert cfg["location"]["name"] == "Home"
    assert sorted(p.name for p in (dst / "photos" / "uploads").iterdir()) == ["abc__kids.jpg"]


def zip_with(entries):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    b.seek(0)
    return b


@pytest.mark.parametrize("entries", [
    {"config.json": "{}", "uploads/../../evil.jpg": "x"},
    {"config.json": "{}", "../config.json": "{}"},
    {"config.json": "{}", "auth.json": "{}"},
    {"config.json": "{}", "uploads/not-an-image.jpg": "hello"},
    {"uploads/a.jpg": "x"},
    {"config.json": "not json"},
])
def test_restore_rejects_traversal(tmp_path, entries):
    d = tmp_path / "d"
    (d / "photos" / "uploads").mkdir(parents=True)
    (d / "photos" / "uploads" / "keep.jpg").write_bytes(jpeg())
    with pytest.raises(ValueError):
        backup.restore_backup(zip_with(entries), d)
    assert [p.name for p in (d / "photos" / "uploads").iterdir()] == ["keep.jpg"]
    assert not (tmp_path / "evil.jpg").exists()


def test_restore_rejects_not_zip(tmp_path):
    with pytest.raises(ValueError):
        backup.restore_backup(io.BytesIO(b"nope"), tmp_path)


def test_restore_normalizes_config(tmp_path):
    (tmp_path / "photos" / "uploads").mkdir(parents=True)
    cfg = backup.restore_backup(zip_with({"config.json": json.dumps({"display": {"rotation": "90", "scale": "huge"}})}),
                                tmp_path)
    assert cfg["display"]["rotation"] == 90 and cfg["display"]["scale"] == 1.0


def test_backup_routes(admin, rt):
    r = admin.get("/api/backup", environ_overrides=REMOTE)
    assert r.status_code == 200 and "dashboard-backup-" in r.headers["Content-Disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.data))
    cfg = json.loads(z.read("config.json"))
    cfg["location"]["name"] = "Restored"
    r = admin.post("/api/restore", data={"backup": (zip_with({"config.json": json.dumps(cfg)}), "b.zip")},
                   headers=H, environ_overrides=REMOTE, content_type="multipart/form-data")
    assert r.status_code == 200 and rt.config["location"]["name"] == "Restored"
