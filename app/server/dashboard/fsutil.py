"""Small file helpers. All state writes on the Pi go through atomic_write_* so a
power cut leaves either the old or the new file, never half of one."""
import json
import os
import re
import tempfile
from pathlib import Path


def atomic_write_bytes(path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, obj) -> None:
    atomic_write_bytes(path, json.dumps(obj, indent=1, ensure_ascii=False).encode("utf-8"))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def safe_name(name: str) -> str:
    base = os.path.basename(str(name).replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")[:80]
    return base or "file"
