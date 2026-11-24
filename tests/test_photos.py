import io
import os

import pytest
from PIL import Image

from conftest import H, REMOTE
from dashboard.photos import PhotoLibrary, Slideshow


def jpeg_with_orientation(w, h, orientation):
    im = Image.new("RGB", (w, h), "green")
    exif = Image.Exif()
    exif[0x0112] = orientation
    b = io.BytesIO()
    im.save(b, "JPEG", exif=exif)
    return b.getvalue()


def test_add_upload_resizes_and_rotates(tmp_path):
    lib = PhotoLibrary(tmp_path)
    name = lib.add_upload("My Photo!.jpg", jpeg_with_orientation(4000, 3000, 6), 1920)
    assert name.endswith("__My_Photo_.jpg")
    with Image.open(lib.upload_dir / name) as im:
        assert im.size == (1440, 1920)  # rotated to portrait, long side 1920
    assert [u["name"] for u in lib.uploads()] == [name]


def test_add_upload_rejects_non_image(tmp_path):
    lib = PhotoLibrary(tmp_path)
    with pytest.raises(ValueError, match="JPEG, PNG or WebP"):
        lib.add_upload("x.jpg", b"not an image", 1920)
    gif = io.BytesIO()
    Image.new("RGB", (4, 4)).save(gif, "GIF")
    with pytest.raises(ValueError):
        lib.add_upload("x.gif", gif.getvalue(), 1920)


def test_delete_upload(tmp_path):
    lib = PhotoLibrary(tmp_path)
    name = lib.add_upload("a.jpg", jpeg_with_orientation(10, 10, 1), 1920)
    assert lib.delete_upload("../" + name) is False
    assert lib.delete_upload(name) is True and lib.uploads() == []


def _lib_with(tmp_path, n):
    lib = PhotoLibrary(tmp_path)
    for i in range(n):
        p = lib.drive_dir / f"id{i}.jpg"
        p.write_bytes(b"x")
        os.utime(p, (1000 + i, 1000 + i))
    return lib


def test_slideshow_advances_after_interval(tmp_path):
    lib = _lib_with(tmp_path, 3)
    w = {"id": "p", "type": "photos", "options": {"interval": 10, "order": "name", "source": "both"}}
    s = Slideshow()
    assert s.tick([w], lib, 100.0) is True
    first = s.current("p")
    assert first.name == "id0.jpg"
    assert s.tick([w], lib, 105.0) is False and s.current("p") == first
    assert s.tick([w], lib, 111.0) is True and s.current("p").name == "id1.jpg"


def test_slideshow_newest_and_shuffle(tmp_path):
    lib = _lib_with(tmp_path, 4)
    s = Slideshow()
    w = {"id": "p", "type": "photos", "options": {"interval": 1, "order": "newest", "source": "drive"}}
    s.tick([w], lib, 0)
    assert s.current("p").name == "id3.jpg"
    w2 = {"id": "q", "type": "photos", "options": {"interval": 1, "order": "shuffle", "source": "both"}}
    seen = set()
    for t in range(8):
        s.tick([w2], lib, t * 2.0)
        seen.add(s.current("q").name)
    assert seen == {f"id{i}.jpg" for i in range(4)}  # a shuffle cycle shows every photo


def test_slideshow_empty_library(tmp_path):
    s = Slideshow()
    w = {"id": "p", "type": "photos", "options": {"interval": 10, "order": "name", "source": "uploads"}}
    assert s.tick([w], _lib_with(tmp_path, 2), 0) is False
    assert s.current("p") is None


def test_upload_requires_login(client):
    data = {"files": (io.BytesIO(jpeg_with_orientation(10, 10, 1)), "a.jpg")}
    r = client.post("/api/photos/upload", data=data, headers=H, environ_overrides=REMOTE,
                    content_type="multipart/form-data")
    assert r.status_code == 401


def test_upload_and_display_state(admin, rt):
    data = {"files": [(io.BytesIO(jpeg_with_orientation(100, 80, 1)), "a.jpg"),
                      (io.BytesIO(b"junk"), "b.jpg")]}
    r = admin.post("/api/photos/upload", data=data, headers=H, environ_overrides=REMOTE,
                   content_type="multipart/form-data")
    assert r.status_code == 200 and len(r.json["added"]) == 1 and len(r.json["errors"]) == 1
    rt.rotate_tick()
    photos = next(w for w in rt.config["widgets"] if w["type"] == "photos")
    url = rt.build_display_state()["widgets"][photos["id"]]["photo"]
    assert url.startswith("/photo/uploads/")
    assert admin.get(url, environ_overrides=REMOTE).status_code == 200
    listing = admin.get("/api/photos", environ_overrides=REMOTE).json
    assert len(listing["uploads"]) == 1 and "drive" in listing


def test_photo_route_localhost(client, rt):
    rt.photos.drive_dir.mkdir(parents=True, exist_ok=True)
    (rt.photos.drive_dir / "abc.jpg").write_bytes(b"x")
    assert client.get("/photo/drive/abc.jpg").status_code == 200
    assert client.get("/photo/drive/abc.jpg", environ_overrides=REMOTE).status_code == 401
    assert client.get("/photo/etc/passwd").status_code == 404
    assert client.get("/photo/drive/..%2Fconfig.json").status_code == 404


def test_slideshow_moves_on_when_current_photo_deleted(tmp_path):
    lib = _lib_with(tmp_path, 2)
    w = {"id": "p", "type": "photos", "options": {"interval": 60, "order": "name", "source": "drive"}}
    s = Slideshow()
    s.tick([w], lib, 0)
    s.current("p").unlink()
    assert s.tick([w], lib, 1) is True and s.current("p").name == "id1.jpg"
