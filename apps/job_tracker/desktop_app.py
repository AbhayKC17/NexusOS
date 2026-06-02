#!/usr/bin/env python3
"""
JobTracker Desktop — entry point.
Run: python3 desktop_app.py

To launch NexusOS (the OS that contains JobTracker as a node):
    python3 ~/Desktop/NexusOS/main.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QLinearGradient

from database import init_db, get_setting, set_setting
from core.theme import FLUENT_LIGHT
from shell.window import MainWindow


def _build_splash() -> QSplashScreen:
    W, H = 560, 280
    px = QPixmap(W, H)
    px.fill(QColor("#FFFFFF"))

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Subtle blue gradient wash
    grad = QLinearGradient(0, 0, W, H)
    grad.setColorAt(0.0, QColor(0, 103, 192, 14))
    grad.setColorAt(1.0, QColor(0, 103, 192, 4))
    p.fillRect(0, 0, W, H, grad)

    # App icon circle
    p.setBrush(QColor(0, 103, 192))
    p.setPen(Qt.PenStyle.NoPen)
    cx = W // 2
    p.drawRoundedRect(cx - 30, 48, 60, 60, 14, 14)

    p.setPen(QColor("#FFFFFF"))
    p.setFont(QFont("Helvetica Neue", 22, QFont.Weight.Bold))
    p.drawText(cx - 30, 48, 60, 60, Qt.AlignmentFlag.AlignCenter, "JT")

    # Title
    p.setPen(QColor("#1A1A1A"))
    p.setFont(QFont("Helvetica Neue", 26, QFont.Weight.Bold))
    p.drawText(0, 128, W, 40, Qt.AlignmentFlag.AlignCenter, "JobTracker")

    # Subtitle
    p.setPen(QColor(0, 0, 0, 110))
    p.setFont(QFont("Helvetica Neue", 13))
    p.drawText(0, 172, W, 28, Qt.AlignmentFlag.AlignCenter, "AI Job Application Assistant")

    # Loading text
    p.setPen(QColor(0, 0, 0, 70))
    p.setFont(QFont("Helvetica Neue", 11))
    p.drawText(0, 210, W, 24, Qt.AlignmentFlag.AlignCenter, "Loading…")

    # Bottom accent bar
    p.setBrush(QColor(0, 103, 192, 60))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(W // 2 - 40, H - 8, 80, 3)
    p.end()

    return QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JobTracker")
    app.setStyleSheet(FLUENT_LIGHT)
    app.setFont(QFont("Helvetica Neue", 13))

    init_db()

    default_model = "/Users/abhay1703/Desktop/Todays Folder/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    if not get_setting("llm_model_path") and os.path.exists(default_model):
        set_setting("llm_model_path", default_model)
        set_setting("llm_gpu_layers", "35")
        set_setting("llm_context",    "8192")

    splash = _build_splash()
    splash.show()
    app.processEvents()

    window = MainWindow()
    window.show()
    QTimer.singleShot(1800, splash.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
