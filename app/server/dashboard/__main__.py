import argparse
import logging
from pathlib import Path

from .runtime import Runtime
from .web import create_app


def main():
    p = argparse.ArgumentParser(prog="dashboard")
    p.add_argument("--data", default="/data")
    p.add_argument("--boot", default=None)
    p.add_argument("--appdir", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("--port", type=int, default=80)
    p.add_argument("--dev", action="store_true", help="run on a PC: system actions are only logged")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    boot = a.boot or (str(Path(a.data) / "boot") if a.dev else "/boot")
    rt = Runtime(a.data, boot, a.appdir, dev=a.dev, port=a.port)
    from . import features
    features.install(rt)
    if (rt.boot_dir / "reset-password").exists():
        with rt.system.boot_rw():
            rt.auth.check_reset_file()
        logging.getLogger("dashboard").warning("password reset via reset-password file")
    app = create_app(rt)
    features.install_routes(app, rt)
    rt.start_background()
    app.run(host="0.0.0.0", port=a.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
