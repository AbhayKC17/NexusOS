"""
nexus/window.py — NexusOS top-level application window.

NexusOS is the host OS.  JobTracker (and any future apps) are
nodes inside the knowledge graph.  Double-clicking an APP node
launches that app in its own window — like clicking an icon in
macOS Finder or Windows Start.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import QMainWindow, QStatusBar, QLabel
from PyQt6.QtCore import Qt, QTimer

from database import get_setting, set_setting
from nexus.page import NexusPage


class NexusWindow(QMainWindow):
    """Top-level window for NexusOS."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexusOS — AI-Native Knowledge Graph")
        self.setMinimumSize(1280, 820)

        self._loader = None

        # Central widget
        self._page = NexusPage()
        self.setCentralWidget(self._page)

        # Status bar
        self._build_status_bar()

        # Refresh graph after scanner may have added nodes (called from main.py)
        QTimer.singleShot(300, self._page.refresh)
        # Auto-load the Mistral model after the window is shown
        QTimer.singleShot(700, self._auto_load_model)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        sb = QStatusBar()
        sb.setFixedHeight(26)
        self.setStatusBar(sb)

        self._model_lbl = QLabel("  ◉  Loading Mistral 7B…")
        self._model_lbl.setStyleSheet(
            "color: #FCE100; font-size: 11px; background: transparent; padding: 2px 8px;"
        )
        sb.addWidget(self._model_lbl)

        ver_lbl = QLabel("NexusOS  ·  v1.0")
        ver_lbl.setStyleSheet(
            "color: rgba(239,239,239,0.22); font-size: 11px; background: transparent; padding: 2px 14px;"
        )
        sb.addPermanentWidget(ver_lbl)

    # ── LLM model ─────────────────────────────────────────────────────────────

    def _auto_load_model(self):
        _nexus = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Look for model on Desktop, one level above NexusOS/
        _default = os.path.join(os.path.dirname(_nexus),
                                "mistral-7b-instruct-v0.2.Q4_K_M.gguf")
        path = get_setting("llm_model_path", _default)
        if not path or not os.path.exists(path):
            self._set_status("  ◯  No model found — open JobTracker → Settings to configure",
                             "rgba(80,80,80,0.60)")
            return

        set_setting("llm_model_path", path)
        n_ctx = int(get_setting("llm_context", 8192))
        n_gpu = int(get_setting("llm_gpu_layers", 35))

        from ui.workers import LLMLoaderWorker
        self._loader = LLMLoaderWorker(path, n_ctx, n_gpu)
        self._loader.done.connect(self._on_model_loaded)
        self._loader.finished.connect(lambda: setattr(self, "_loader", None))
        self._loader.start()

    def _on_model_loaded(self, ok: bool, msg: str):
        if ok:
            self._set_status("  ●  Mistral 7B ready — AI features active", "#6CCB5F")
        else:
            self._set_status(f"  ✕  Model error: {msg[:70]}", "#FF99A4")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str):
        self._model_lbl.setText(text)
        self._model_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; background: transparent; padding: 2px 8px;"
        )
