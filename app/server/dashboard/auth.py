"""Settings-site password. Stored as a salted scrypt hash on /data; an `epoch`
value invalidates every session when the password changes or is reset."""
import hashlib
import hmac
import secrets
from pathlib import Path

from . import fsutil

N, R, P = 2 ** 14, 8, 1
MIN_LEN = 6


def _hash(pw: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=N, r=R, p=P, maxmem=64 * 1024 * 1024, dklen=32)


class Auth:
    def __init__(self, data_dir: Path, boot_dir: Path):
        self.path = Path(data_dir) / "auth.json"
        self.key_path = Path(data_dir) / "secret.key"
        self.boot_dir = Path(boot_dir)

    def _load(self):
        return fsutil.read_json(self.path) or None

    def is_set(self) -> bool:
        d = self._load()
        return bool(d and d.get("hash"))

    def epoch(self) -> str:
        d = self._load()
        return d.get("epoch", "") if d else ""

    def set_password(self, pw: str) -> None:
        if not isinstance(pw, str) or len(pw) < MIN_LEN:
            raise ValueError(f"Password must be at least {MIN_LEN} characters")
        salt = secrets.token_bytes(16)
        fsutil.atomic_write_json(self.path, {"salt": salt.hex(), "hash": _hash(pw, salt).hex(),
                                             "epoch": secrets.token_hex(8)})

    def verify(self, pw: str) -> bool:
        d = self._load()
        if not d or not isinstance(pw, str):
            return False
        return hmac.compare_digest(_hash(pw, bytes.fromhex(d["salt"])).hex(), d["hash"])

    def check_reset_file(self) -> bool:
        """An empty `reset-password` file on the SD card's boot partition clears the password."""
        flag = self.boot_dir / "reset-password"
        if not flag.exists():
            return False
        self.path.unlink(missing_ok=True)
        try:
            flag.unlink()
        except OSError:
            pass  # read-only /boot: caller remounts rw before calling, best effort otherwise
        return True

    def secret_key(self) -> bytes:
        try:
            key = self.key_path.read_bytes()
            if len(key) == 32:
                return key
        except OSError:
            pass
        key = secrets.token_bytes(32)
        fsutil.atomic_write_bytes(self.key_path, key)
        return key
