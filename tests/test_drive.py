import io
import json
import urllib.error
from pathlib import Path

import pytest
from PIL import Image

from dashboard import drive

FIXTURE = (Path(__file__).parent / "fixtures" / "embedded_folder.html").read_bytes()
IDS = ["1AAAAAAAAAAAAAAAAAAAAaa", "1BBBBBBBBBBBBBBBBBBBBbb", "1CCCCCCCCCCCCCCCCCCCCcc"]


def jpeg(w=40, h=30):
    b = io.BytesIO()
    Image.new("RGB", (w, h), "blue").save(b, "JPEG")
    return b.getvalue()


class Resp(io.BytesIO):
    def __init__(self, data, url="https://drive.google.com/x"):
        super().__init__(data)
        self._url = url

    def geturl(self):
        return self._url


def fake_http(listing=FIXTURE, images=None):
    images = images or {}
    calls = []

    def http(url, timeout=None):
        calls.append(url)
        if "embeddedfolderview" in url:
            return Resp(listing)
        if "thumbnail" in url:
            fid = url.split("id=")[1].split("&")[0]
            return Resp(images.get(fid, jpeg()))
        raise AssertionError(url)
    http.calls = calls
    return http


def test_folder_id_from_url():
    assert drive.folder_id_from_url("https://drive.google.com/drive/folders/1tmS8YYlrTHWv8vVR?usp=drive_link") \
        == "1tmS8YYlrTHWv8vVR"
    assert drive.folder_id_from_url("https://drive.google.com/embeddedfolderview?id=1abcdefghijk") == "1abcdefghijk"
    assert drive.folder_id_from_url("1abcdefghijkLMNOP") == "1abcdefghijkLMNOP"
    assert drive.folder_id_from_url("https://example.com/hello") is None
    assert drive.folder_id_from_url("") is None


def test_list_folder_parses_fixture():
    files = drive.list_folder("1folderidxxxx", http=fake_http())
    assert files == [{"id": IDS[0], "name": "Beach day.JPG"}, {"id": IDS[1], "name": "IMG_2041.heic"},
                     {"id": IDS[2], "name": "grandma & kids.png"}]


def test_list_folder_not_public():
    def http401(url, timeout=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    with pytest.raises(drive.DriveError) as e:
        drive.list_folder("1folderidxxxx", http=http401)
    assert "Anyone with the link" in str(e.value)

    def signin(url, timeout=None):
        return Resp(b"<html>sign in</html>", "https://accounts.google.com/v3/signin/identifier?x")
    with pytest.raises(drive.DriveError) as e:
        drive.list_folder("1folderidxxxx", http=signin)
    assert "Anyone with the link" in str(e.value)


def test_list_folder_api_key_pagination():
    pages = {
        None: {"files": [{"id": IDS[0], "name": "a.jpg", "mimeType": "image/jpeg"},
                         {"id": "d1", "name": "doc", "mimeType": "application/pdf"}], "nextPageToken": "T2"},
        "T2": {"files": [{"id": IDS[1], "name": "b.png", "mimeType": "image/png"}]},
    }
    seen = []

    def http(url, timeout=None):
        seen.append(url)
        token = url.split("pageToken=")[1].split("&")[0] if "pageToken=" in url else None
        return Resp(json.dumps(pages[token]).encode())
    files = drive.list_folder("1folderidxxxx", api_key="KEY123", http=http)
    assert files == [{"id": IDS[0], "name": "a.jpg"}, {"id": IDS[1], "name": "b.png"}]
    assert len(seen) == 2 and "key=KEY123" in seen[0]


def test_sync_adds_and_removes(tmp_path):
    s = drive.DriveSync(tmp_path)
    r = s.sync("https://drive.google.com/drive/folders/1folderidxxxx", "", 1920, http=fake_http())
    assert r["count"] == 3 and r["added"] == 3 and r["error"] is None
    assert sorted(p.stem for p in tmp_path.glob("*.jpg")) == sorted(IDS)
    assert s.names()[IDS[2]] == "grandma & kids.png"
    smaller = FIXTURE.replace(b"entry-1AAAAAAAAAAAAAAAAAAAAaa", b"entry-gone")
    r = s.sync("https://drive.google.com/drive/folders/1folderidxxxx", "", 1920, http=fake_http(listing=smaller))
    assert r["removed"] == 1 and not (tmp_path / f"{IDS[0]}.jpg").exists()


def test_sync_skips_bad_download(tmp_path):
    s = drive.DriveSync(tmp_path)
    r = s.sync("1folderidxxxx", "", 1920, http=fake_http(images={IDS[1]: b"<html>quota</html>"}))
    assert r["added"] == 2 and not (tmp_path / f"{IDS[1]}.jpg").exists()


def test_sync_keeps_files_on_error(tmp_path):
    s = drive.DriveSync(tmp_path)
    s.sync("1folderidxxxx", "", 1920, http=fake_http())

    def offline(url, timeout=None):
        raise OSError("no internet")
    r = s.sync("1folderidxxxx", "", 1920, http=offline)
    assert r["error"] and len(list(tmp_path.glob("*.jpg"))) == 3


def test_sync_bad_link(tmp_path):
    r = drive.DriveSync(tmp_path).sync("https://example.com/nope", "", 1920, http=fake_http())
    assert "Drive folder link" in r["error"]


def test_list_folder_page_without_entries_raises():
    # Google changed the page, or served a consent page: not "the folder is empty"
    with pytest.raises(drive.DriveError):
        drive.list_folder("1tmSabcdefghijklmnopqrstuv", http=fake_http(b"<html><body>Before you continue</body></html>"))


def test_sync_empty_listing_keeps_cache(tmp_path):
    d = drive.DriveSync(tmp_path)
    d.sync("https://drive.google.com/drive/folders/1tmSabcdefghijklmnopqrstuv", "", 1920, http=fake_http())
    assert len(list(tmp_path.glob("*.jpg"))) == 3
    empty = b'<div class="flip-entries"></div>'
    r = d.sync("https://drive.google.com/drive/folders/1tmSabcdefghijklmnopqrstuv", "", 1920, http=fake_http(empty))
    assert r["removed"] == 0 and r["error"] and r["count"] == 3
    assert len(list(tmp_path.glob("*.jpg"))) == 3


def test_api_listing_drops_unsafe_ids():
    def http(url, timeout=None):
        body = {"files": [{"id": "../../etc/x", "name": "a.jpg", "mimeType": "image/jpeg"},
                          {"id": IDS[0], "name": "b.jpg", "mimeType": "image/jpeg"}]}
        return Resp(json.dumps(body).encode())
    assert [f["id"] for f in drive.list_folder("1tmSabcdefghijklmnopqrstuv", "KEY", http)] == [IDS[0]]
