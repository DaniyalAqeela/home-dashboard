"""Settings + uploaded photos as one zip. The password (auth.json) is never included."""
import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image

from . import config

MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_FILE = 30 * 1024 * 1024
MAX_ENTRIES = 20000
UPLOAD_RE = r"uploads/[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}\.jpg"


def make_backup(data_dir, dest) -> None:
    d, dest = Path(data_dir), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED) as z:  # photos are already compressed
        z.writestr("config.json", json.dumps(config.load(d / "config.json"), indent=2))
        for p in sorted((d / "photos" / "uploads").glob("*.jpg")):
            z.write(p, f"uploads/{p.name}")
    os.replace(part, dest)


def restore_backup(src, data_dir) -> dict:
    """src: a path or a seekable file object. Validates everything before touching data_dir."""
    try:
        z = zipfile.ZipFile(src)
    except (zipfile.BadZipFile, OSError):
        raise ValueError("That isn't a dashboard backup (.zip).") from None
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_TOTAL:
            raise ValueError("Backup is too large.")
        if "config.json" not in {i.filename for i in infos}:
            raise ValueError("Backup has no config.json.")
        photos = [i for i in infos if i.filename != "config.json"]
        for i in photos:
            if not re.fullmatch(UPLOAD_RE, i.filename) or i.file_size > MAX_FILE:
                raise ValueError(f"Unexpected file in backup: {i.filename[:80]}")
        try:
            cfg = json.loads(z.read("config.json"))
        except ValueError:
            raise ValueError("The backup's config.json is damaged.") from None
        if not isinstance(cfg, dict):
            raise ValueError("The backup's config.json is damaged.")
        cfg = config.normalize(cfg)

        uploads = Path(data_dir) / "photos" / "uploads"
        new, old = uploads.with_name("uploads.new"), uploads.with_name("uploads.old")
        shutil.rmtree(new, ignore_errors=True)
        new.mkdir(parents=True)
        try:
            for i in photos:
                data = z.read(i)
                try:
                    Image.open(io.BytesIO(data)).verify()
                except Exception:
                    raise ValueError(f"{i.filename[8:]} in the backup isn't a valid photo.") from None
                (new / i.filename[8:]).write_bytes(data)
        except BaseException:
            shutil.rmtree(new, ignore_errors=True)
            raise
    shutil.rmtree(old, ignore_errors=True)
    if uploads.exists():
        uploads.rename(old)
    new.rename(uploads)
    shutil.rmtree(old, ignore_errors=True)
    return cfg
