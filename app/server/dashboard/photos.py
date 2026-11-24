"""Local photo library (Drive mirror + browser uploads) and the per-widget slideshow."""
import io
import os
import random
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from . import fsutil

MAX_UPLOAD = 30 * 1024 * 1024
ACCEPTED = {"JPEG", "MPO", "PNG", "WEBP"}


class PhotoLibrary:
    def __init__(self, data_dir):
        root = Path(data_dir) / "photos"
        self.drive_dir = root / "drive"
        self.upload_dir = root / "uploads"
        for d in (self.drive_dir, self.upload_dir):
            d.mkdir(parents=True, exist_ok=True)

    def all(self, source="both") -> list:
        dirs = {"drive": [self.drive_dir], "uploads": [self.upload_dir]}.get(source, [self.drive_dir, self.upload_dir])
        return [p for d in dirs for p in d.glob("*.jpg")]

    def add_upload(self, filename, data: bytes, long_side: int) -> str:
        if len(data) > MAX_UPLOAD:
            raise ValueError("Photo is larger than 30 MB")
        try:
            im = Image.open(io.BytesIO(data))
            fmt = im.format
        except Exception:
            raise ValueError("Use JPEG, PNG or WebP") from None
        if fmt not in ACCEPTED:
            raise ValueError("Use JPEG, PNG or WebP")
        w, h = im.size
        scale = min(1.0, long_side / max(w, h))
        im.draft("RGB", (int(w * scale) + 1, int(h * scale) + 1))  # JPEG: decode at reduced size, saves RAM
        try:
            im = ImageOps.exif_transpose(im).convert("RGB")
        except Exception:
            raise ValueError("That photo looks damaged") from None
        im.thumbnail((long_side, long_side))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        name = f"{uuid.uuid4().hex[:8]}__{Path(fsutil.safe_name(filename)).stem}.jpg"
        fsutil.atomic_write_bytes(self.upload_dir / name, out.getvalue())
        return name

    def delete_upload(self, name) -> bool:
        if not name or name != os.path.basename(name) or "\\" in name or name.startswith("."):
            return False
        p = self.upload_dir / name
        if not p.is_file():
            return False
        p.unlink()
        return True

    def uploads(self) -> list:
        files = sorted(self.upload_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"name": p.name, "size": p.stat().st_size} for p in files]


class Slideshow:
    """Server-owned 'current photo' per widget, so the screen and the preview agree."""

    def __init__(self):
        self.st = {}  # widget id -> {"current": Path|None, "nextAt": float, "queue": [Path]}

    def current(self, widget_id):
        s = self.st.get(widget_id)
        return s["current"] if s else None

    def _next(self, s, files, order):
        if order == "shuffle":
            pool = set(files)
            s["queue"] = [p for p in s.get("queue", []) if p in pool]
            if not s["queue"]:
                s["queue"] = random.sample(files, len(files))
                if len(files) > 1 and s["queue"][0] == s["current"]:
                    s["queue"].append(s["queue"].pop(0))  # don't show the same photo twice in a row
            return s["queue"].pop(0)
        if order == "newest":
            files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
        else:
            files = sorted(files, key=lambda p: p.name.lower())
        if s["current"] in files:
            return files[(files.index(s["current"]) + 1) % len(files)]
        return files[0]

    def tick(self, widgets, library, now: float) -> bool:
        changed = False
        ids = set()
        for w in widgets:
            if w.get("type") != "photos":
                continue
            ids.add(w["id"])
            o = w["options"]
            s = self.st.setdefault(w["id"], {"current": None, "nextAt": 0.0})
            if s["current"] is not None and now < s["nextAt"] and s["current"].exists():
                continue
            files = library.all(o.get("source", "both"))
            if not files:
                if s["current"] is not None:
                    s["current"], changed = None, True
                continue
            nxt = self._next(s, files, o.get("order", "shuffle"))
            if nxt != s["current"]:
                changed = True
            s["current"], s["nextAt"] = nxt, now + float(o.get("interval", 15))
        for gone in set(self.st) - ids:
            del self.st[gone]
        return changed
