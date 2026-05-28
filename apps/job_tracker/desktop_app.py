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
from core.theme import FLUENT_DARK
from shell.window import MainWindow


def _build_splash() -> QSplashScreen:
    W, H = 600, 300
    px = QPixmap(W, H)
    px.fill(QColor("#0D0D10"))

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    grad = QLinearGradient(0, 0, W, H)
    grad.setColorAt(0.0, QColor(99, 102, 241, 30))
    grad.setColorAt(0.5, QColor(99, 102, 241, 10))
    grad.setColorAt(1.0, QColor(13, 13, 16, 0))
    p.fillRect(0, 0, W, H, grad)

    p.setPen(QColor("#818CF8"))
    p.setFont(QFont("Helvetica Neue", 38, QFont.Weight.Bold))
    p.drawText(0, 70, W, 60, Qt.AlignmentFlag.AlignCenter, "✦  JobTracker")

    p.setPen(QColor(239, 239, 239, 120))
    p.setFont(QFont("Helvetica Neue", 13))
    p.drawText(0, 142, W, 30, Qt.AlignmentFlag.AlignCenter, "AI Job Application Assistant")

    p.setPen(QColor(239, 239, 239, 55))
    p.setFont(QFont("Helvetica Neue", 11))
    p.drawText(0, 192, W, 28, Qt.AlignmentFlag.AlignCenter, "Initialising — loading Mistral 7B…")

    p.setPen(QColor(99, 102, 241, 70))
    p.drawLine(W // 2 - 70, H - 20, W // 2 + 70, H - 20)
    p.end()

    return QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JobTracker")
    app.setStyleSheet(FLUENT_DARK)
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
