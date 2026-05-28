#!/usr/bin/env python3
"""
NexusOS — Desktop launcher.

Run this from anywhere:
    python3 /Users/abhay1703/Desktop/NexusOS/main.py

Structure
─────────
  NexusOS/
  ├── main.py            ← you are here
  ├── core/              ← shared theme / utilities
  ├── nexus/             ← graph engine, canvas, AI agent
  ├── apps/
  │   └── job_tracker/   ← JobTracker app (and future apps here)
  ├── desktop → ~/Desktop  ← symlink; every file appears as a graph node
  └── data/
      └── nexus.db       ← SQLite graph store

To add a new app: drop a folder under apps/ with an __init__.py
that defines APP_META, then tell the assistant to integrate it.
"""
import sys
import os

# ── Path setup ────────────────────────────────────────────────────────────────
_NEXUS = os.path.dirname(os.path.abspath(__file__))
_JT    = os.path.join(_NEXUS, "apps", "job_tracker")
_DESK  = os.path.join(_NEXUS, "desktop")          # symlink → ~/Desktop

# NexusOS root first (core/, nexus/), then app root (database, shell, ui, …)
if _NEXUS not in sys.path:
    sys.path.insert(0, _NEXUS)
if _JT not in sys.path:
    sys.path.insert(0, _JT)

if not os.path.exists(_JT):
    print(
        "ERROR: apps/job_tracker not found.\n"
        f"Expected: {_JT}"
    )
    sys.exit(1)

# ── Imports ───────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore    import Qt, QTimer
from PyQt6.QtGui     import QFont, QPixmap, QPainter, QColor, QRadialGradient

from database        import init_db, get_setting, set_setting
from core.theme      import FLUENT_LIGHT
from nexus.window    import NexusWindow


# ── Splash ────────────────────────────────────────────────────────────────────

def _build_splash() -> QSplashScreen:
    W, H = 640, 320
    px = QPixmap(W, H)
    px.fill(QColor("#FAFAFA"))

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    glow = QRadialGradient(W / 2, H / 2, W * 0.65)
    glow.setColorAt(0.0, QColor(0, 103, 192, 22))
    glow.setColorAt(0.6, QColor(0, 103, 192,  8))
    glow.setColorAt(1.0, QColor(250, 250, 250, 0))
    p.fillRect(0, 0, W, H, glow)

    # Subtle border
    p.setPen(QColor(0, 0, 0, 18))
    p.drawRect(0, 0, W - 1, H - 1)

    p.setPen(QColor(0, 103, 192, 200))
    p.setFont(QFont("Helvetica Neue", 46, QFont.Weight.Bold))
    p.drawText(0, 48, W, 72, Qt.AlignmentFlag.AlignCenter, "⬡")

    p.setPen(QColor("#0067C0"))
    p.setFont(QFont("Helvetica Neue", 30, QFont.Weight.Bold))
    p.drawText(0, 128, W, 48, Qt.AlignmentFlag.AlignCenter, "NexusOS")

    p.setPen(QColor(30, 30, 30, 140))
    p.setFont(QFont("Helvetica Neue", 13))
    p.drawText(0, 182, W, 28, Qt.AlignmentFlag.AlignCenter,
               "AI-Native Knowledge Graph Operating System")

    p.setPen(QColor(30, 30, 30, 80))
    p.setFont(QFont("Helvetica Neue", 11))
    p.drawText(0, 222, W, 26, Qt.AlignmentFlag.AlignCenter,
               "Scanning Desktop — building your knowledge graph…")

    p.setPen(QColor(0, 103, 192, 60))
    p.drawLine(W // 2 - 80, H - 18, W // 2 + 80, H - 18)
    p.end()

    return QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NexusOS")
    app.setStyleSheet(FLUENT_LIGHT)
    app.setFont(QFont("Helvetica Neue", 13))

    init_db()

    # Register Mistral model on first run (look next to NexusOS/ on the Desktop)
    _model = os.path.join(os.path.dirname(_NEXUS),
                          "mistral-7b-instruct-v0.2.Q4_K_M.gguf")
    if not _model or not os.path.exists(_model):
        # Also check Todays Folder fallback
        _model = os.path.join(os.path.expanduser("~/Desktop"), "Todays Folder",
                              "mistral-7b-instruct-v0.2.Q4_K_M.gguf")

    if not get_setting("llm_model_path") and os.path.exists(_model):
        set_setting("llm_model_path", os.path.abspath(_model))
        set_setting("llm_gpu_layers", "35")
        set_setting("llm_context",    "8192")

    splash = _build_splash()
    splash.show()
    app.processEvents()

    # Initialise graph DB and scan the Desktop *before* showing the window
    from nexus.graph_db  import init_nexus_db, seed_default_graph
    from nexus.registry  import seed_jobtracker
    from nexus.scanner   import scan_desktop

    init_nexus_db()
    seed_default_graph()
    seed_jobtracker()

    # Scan real Desktop (via symlink or direct path)
    _real_desktop = os.path.realpath(_DESK)
    scan_desktop(_real_desktop)

    # Also index Todays Folder if it exists
    _todays = os.path.join(_real_desktop, "Todays Folder")
    if os.path.isdir(_todays):
        scan_desktop(_todays)

    window = NexusWindow()
    window.show()
    QTimer.singleShot(2200, splash.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
