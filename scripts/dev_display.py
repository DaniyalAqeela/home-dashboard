"""PC twin of os/package/dashboard-display/src/main.cpp (same context property, same load).
Usage: python scripts/dev_display.py [server-url]"""
import importlib.util
import os
import sys
from pathlib import Path

# Windows: QML plugin DLLs need PySide6's Qt DLLs on the DLL search path (PATH isn't searched since Python 3.8)
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(str(Path(importlib.util.find_spec("PySide6").origin).parent))

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("dashboardUrl", sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080")
engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "app" / "display" / "Main.qml")))
sys.exit(1 if not engine.rootObjects() else app.exec())
