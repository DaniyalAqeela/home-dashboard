"""Mirror a public Google Drive folder into a local photo directory, as
screen-sized JPEG thumbnails named <file id>.jpg."""
import io
import json
import re
import shutil
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageOps

from . import fsutil, net

ID_RE = r"[A-Za-z0-9_-]{10,}"
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "heic", "heif", "gif", "bmp", "tif", "tiff"}
NOT_PUBLIC = "This folder isn't shared publicly. In Google Drive: Share → General access → Anyone with the link."
MAX_PHOTO_BYTES = 15 * 1024 * 1024
MIN_FREE_BYTES = 500 * 1024 * 1024


class DriveError(Exception):
    pass


def folder_id_from_url(url: str):
    s = (url or "").strip()
    m = re.search(rf"/folders/({ID_RE})", s) or re.search(rf"[?&]id=({ID_RE})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(ID_RE, s) else None


def _get(url, http, cap):
    """GET returning (bytes, final_url); Drive auth failures become DriveError."""
    try:
        r = (http or net.urlopen)(url, timeout=20)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise DriveError(NOT_PUBLIC) from None
        if e.code == 404:
            raise DriveError("Drive folder not found. Check the link.") from None
        raise DriveError(f"Google Drive error {e.code}") from None
    try:
        final = r.geturl() if hasattr(r, "geturl") else url
        return net.read_capped(r, cap), final
    finally:
        r.close()


class _FolderPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries, self.cur, self.in_title, self.listing = [], None, False, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if "flip-entries" in cls:
            self.listing = True
        if tag == "div" and "flip-entry" in cls and (a.get("id") or "").startswith("entry-"):
            self.cur = {"id": a["id"][6:], "name": "", "href": ""}
            self.entries.append(self.cur)
        elif tag == "div" and "flip-entry-title" in cls and self.cur is not None:
            self.in_title = True
        elif tag == "a" and self.cur is not None and not self.cur["href"]:
            self.cur["href"] = a.get("href") or ""

    def handle_endtag(self, tag):
        if tag == "div":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.cur["name"] += data


def _is_image_name(name):
    return name.rsplit(".", 1)[-1].lower() in IMAGE_EXT if "." in name else False


def list_folder(folder_id, api_key="", http=None) -> list:
    if api_key:
        return _list_api(folder_id, api_key, http)
    page, final = _get(f"https://drive.google.com/embeddedfolderview?id={folder_id}", http, 8 * 1024 * 1024)
    if "accounts.google.com" in final:
        raise DriveError(NOT_PUBLIC)
    p = _FolderPage()
    p.feed(page.decode("utf-8", "replace"))
    if not p.listing:
        raise DriveError("Google Drive sent an unexpected page instead of the folder. Keeping the photos already here.")
    return [{"id": e["id"], "name": e["name"].strip()} for e in p.entries
            if re.fullmatch(ID_RE, e["id"]) and "/folders/" not in e["href"] and _is_image_name(e["name"].strip())]


def _list_api(folder_id, api_key, http):
    files, token = [], None
    for _ in range(50):  # 50 pages x 1000 files is far beyond any family album
        q = {"q": f"'{folder_id}' in parents and trashed=false", "pageSize": 1000,
             "fields": "nextPageToken,files(id,name,mimeType)", "key": api_key}
        if token:
            q["pageToken"] = token
        try:
            body, _ = _get("https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(q), http, 8 << 20)
        except DriveError as e:
            raise DriveError(f"{e} (If the API key is wrong, clear it to use the public link.)") from None
        d = json.loads(body)
        files += [{"id": f["id"], "name": f.get("name", "")} for f in d.get("files", [])
                  if str(f.get("mimeType", "")).startswith("image/") and re.fullmatch(ID_RE, str(f.get("id", "")))]
        token = d.get("nextPageToken")
        if not token:
            break
    return files


def _to_jpeg(data: bytes, long_side: int) -> bytes:
    """Decode (raises if it isn't an image); re-encode only when not a plain upright JPEG."""
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.format == "JPEG" and im.getexif().get(0x0112, 1) == 1 and max(im.size) <= long_side * 1.25:
        return data
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((long_side, long_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


class DriveSync:
    def __init__(self, photo_dir: Path, http=None):
        self.dir = Path(photo_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index = self.dir / "index.json"
        self.http = http
        self.progress = None  # (done, total) while downloading

    def names(self) -> dict:
        return fsutil.read_json(self.index, {}) or {}

    def _present(self):
        return {p.stem: p for p in self.dir.glob("*.jpg")}

    def sync(self, url, api_key, long_side: int, http=None) -> dict:
        http = http or self.http
        present = self._present()
        result = {"count": len(present), "added": 0, "removed": 0, "error": None}
        fid = folder_id_from_url(url)
        if not fid:
            result["error"] = "That doesn't look like a Google Drive folder link." if url else "No Drive folder link set."
            return result
        try:
            files = list_folder(fid, api_key, http)
        except (DriveError, OSError, ValueError) as e:
            result["error"] = str(e)
            return result
        wanted = {f["id"]: f["name"] for f in files}
        if not wanted and present:
            result["error"] = ("Drive shows no photos in this folder. Is it still shared with \"Anyone with the link\"? "
                               "Keeping the photos already here.")
            return result
        for stem, path in present.items():
            if stem not in wanted:
                path.unlink(missing_ok=True)
                result["removed"] += 1
        missing = [i for i in wanted if i not in present]
        failed = 0
        for n, fid in enumerate(missing):
            self.progress = (n, len(missing))
            if shutil.disk_usage(self.dir).free < MIN_FREE_BYTES:
                result["error"] = "The SD card is nearly full, so some photos were not downloaded."
                break
            try:
                data, _ = _get(f"https://drive.google.com/thumbnail?id={fid}&sz=s{long_side}", http, MAX_PHOTO_BYTES)
                fsutil.atomic_write_bytes(self.dir / f"{fid}.jpg", _to_jpeg(data, long_side))
                result["added"] += 1
            except Exception:
                failed += 1  # not an image, quota page, network blip: retried next sync
        self.progress = None
        fsutil.atomic_write_json(self.index, wanted)
        result["count"] = len(self._present())
        if failed and not result["error"]:
            result["error"] = f"{failed} photo(s) couldn't be downloaded; will retry on the next sync."
        return result
