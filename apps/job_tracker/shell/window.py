"""
Main application window — Fluent NavigationView shell.

Structure
─────────
  QMainWindow
  └── centralWidget (QWidget, QHBoxLayout)
       ├── SidebarWidget (QFrame#sidebar, fixed 220 px)
       │    ├── AppBrandWidget   — icon + title + subtitle
       │    ├── NavScrollArea    — scrollable nav items
       │    │    └── nav buttons × N
       │    ├── hDivider
       │    ├── Settings button  — always at bottom
       │    ├── hDivider
       │    └── StatusFooter     — model dot + sync dot
       └── QStackedWidget (stretch 1) — one widget per tab

Each tab folder exports a single Page class via its __init__.py.
MainWindow instantiates them once and never recreates them.
"""

import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QScrollArea, QStatusBar, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from database import get_setting, set_setting
from ui.workers import LLMLoaderWorker, EmailSyncWorker
import modules.llm_summarizer as ls

# Feature pages — one import per module folder
from dashboard      import DashboardPage
from applications   import ApplicationsPage
from spreadsheet    import SpreadsheetPage
from campaign       import CampaignPage
from mail           import MailPage
from replies        import RepliesPage
from assistant      import AssistantPage
from resume_builder import ResumePage
from settings       import SettingsPage

from shell.compose  import ComposeDialog


# ── Navigation manifest ───────────────────────────────────────────────────────
# (label, icon_glyph)  — order maps directly to QStackedWidget index
NAV_ITEMS = [
    ("Overview",      "⌂"),
    ("Applications",  "◫"),
    ("Data",          "⊞"),
    ("Campaign",      "✉"),
    ("Mail",          "◉"),
    ("Replies",       "↩"),
    ("AI Assistant",  "✦"),
    ("Resume",        "◈"),
]

SETTINGS_IDX = len(NAV_ITEMS)   # Settings lives after the main items


# ── Sidebar ───────────────────────────────────────────────────────────────────

class _AppBrand(QWidget):
    """Top area of the sidebar: icon mark + app name + subtitle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appBrand")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 16)
        lay.setSpacing(3)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(10)

        mark = QLabel("✦")
        mark.setStyleSheet(
            "color: #6366F1; font-size: 22px; font-weight: 700; background: transparent;"
        )
        icon_row.addWidget(mark)

        title = QLabel("JobTracker")
        title.setObjectName("appTitle")
        icon_row.addWidget(title)
        icon_row.addStretch()
        lay.addLayout(icon_row)

        sub = QLabel("AI Application Manager")
        sub.setObjectName("appSubtitle")
        lay.addWidget(sub)


class _NavButton(QPushButton):
    """Single navigation item button."""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(f"  {icon}  {label}", parent)
        self.setObjectName("navBtn")
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class _StatusFooter(QWidget):
    """Bottom of the sidebar: model status + sync status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 12)
        lay.setSpacing(0)

        self.modelDot = QLabel("  ◉  Loading model…")
        self.modelDot.setObjectName("modelStatus")
        self.modelDot.setStyleSheet(
            "color: #FCE100; font-size: 11px; background: transparent; padding: 5px 14px;"
        )

        self.syncDot = QLabel("  Auto-sync: every 15 min")
        self.syncDot.setObjectName("syncStatus")

        lay.addWidget(self.modelDot)
        lay.addWidget(self.syncDot)


class _Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarDivider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class Sidebar(QFrame):
    """Left navigation rail — fixed 220 px, never resizable."""

    def __init__(self, nav_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        self._nav_callback = nav_callback
        self._buttons: list[_NavButton] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Brand
        lay.addWidget(_AppBrand())
        lay.addWidget(_Divider())

        # Scrollable nav area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_lay = QVBoxLayout(nav_container)
        nav_lay.setContentsMargins(0, 8, 0, 8)
        nav_lay.setSpacing(1)

        for idx, (label, icon) in enumerate(NAV_ITEMS):
            btn = _NavButton(icon, label)
            btn.clicked.connect(lambda _, i=idx: self._nav_callback(i))
            nav_lay.addWidget(btn)
            self._buttons.append(btn)

        nav_lay.addStretch()
        scroll.setWidget(nav_container)
        lay.addWidget(scroll, 1)

        # Divider + Settings
        lay.addWidget(_Divider())
        settings_btn = _NavButton("⚙", "Settings")
        settings_btn.clicked.connect(lambda: self._nav_callback(SETTINGS_IDX))
        self._buttons.append(settings_btn)
        lay.addWidget(settings_btn)

        # Status footer
        lay.addWidget(_Divider())
        self._footer = _StatusFooter()
        lay.addWidget(self._footer)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def model_dot(self) -> QLabel:
        return self._footer.modelDot

    @property
    def sync_dot(self) -> QLabel:
        return self._footer.syncDot

    def set_active(self, idx: int):
        for i, btn in enumerate(self._buttons):
            btn.set_active(i == idx)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JobTracker — AI Job Application Assistant")
        self.setMinimumSize(1140, 760)

        self._loader      = None
        self._sync_worker = None

        self._build()
        self._setup_sync_timer()
        self._navigate(0)
        QTimer.singleShot(400, self._auto_load_model)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar(nav_callback=self._navigate)
        root.addWidget(self._sidebar)

        # Page stack — each tab has exactly one persistent widget
        self._stack = QStackedWidget()

        self._dash   = DashboardPage()
        self._apps   = ApplicationsPage()
        self._data   = SpreadsheetPage()
        self._camp   = CampaignPage()
        self._mail   = MailPage()
        self._repl   = RepliesPage()
        self._asst   = AssistantPage()
        self._resume = ResumePage()
        self._sett   = SettingsPage()

        for page in (
            self._dash, self._apps, self._data, self._camp,
            self._mail, self._repl, self._asst, self._resume, self._sett,
        ):
            self._stack.addWidget(page)

        # Wire cross-page signals
        self._apps.compose_requested.connect(self._open_compose)

        root.addWidget(self._stack, 1)

        # Status bar
        sb = QStatusBar()
        sb.setFixedHeight(26)
        self.setStatusBar(sb)
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.35); background: transparent;"
        )
        sb.addWidget(self._status_lbl)

        self._sett.load_settings()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate(self, idx: int):
        self._sidebar.set_active(idx)
        self._stack.setCurrentIndex(idx)
        page = self._stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    # ── Compose ───────────────────────────────────────────────────────────────

    def _open_compose(self, app_id: int):
        dlg = ComposeDialog(app_id, self)
        dlg.exec()
        self._apps.refresh()

    # ── Background sync timer ─────────────────────────────────────────────────

    def _setup_sync_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_sync)
        self._timer.start(15 * 60 * 1000)

    def _auto_sync(self):
        if self._sync_worker:
            return
        self._sync_worker = EmailSyncWorker()
        self._sync_worker.done.connect(self._on_auto_sync)
        self._sync_worker.finished.connect(
            lambda: setattr(self, "_sync_worker", None)
        )
        self._sync_worker.start()

    def _on_auto_sync(self, count: int, errors: list):
        dot = self._sidebar.sync_dot
        if count:
            label = f"repl{'y' if count == 1 else 'ies'}"
            dot.setText(f"  ✓  {count} new {label}")
            dot.setStyleSheet(
                "color: #6CCB5F; font-size: 11px; background: transparent; padding: 2px 14px 12px 14px;"
            )
            current = self._stack.currentWidget()
            if current in (self._repl, self._dash, self._data):
                current.refresh()
        else:
            dot.setText("  Auto-sync: every 15 min")
            dot.setStyleSheet(
                "color: rgba(255,255,255,0.32); font-size: 11px; background: transparent; padding: 2px 14px 12px 14px;"
            )

    # ── LLM loader ────────────────────────────────────────────────────────────

    def _auto_load_model(self):
        default = "/Users/abhay1703/Desktop/Todays Folder/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
        path = get_setting("llm_model_path", default)
        if not path or not os.path.exists(path):
            self._sidebar.model_dot.setText("  ◯  No model — see Settings")
            self._sidebar.model_dot.setStyleSheet(
                "color: #FCE100; font-size: 11px; background: transparent; padding: 5px 14px;"
            )
            return

        set_setting("llm_model_path", path)
        n_ctx = int(get_setting("llm_context", 8192))
        n_gpu = int(get_setting("llm_gpu_layers", 35))

        self._loader = LLMLoaderWorker(path, n_ctx, n_gpu)
        self._loader.done.connect(self._on_model_loaded)
        self._loader.finished.connect(lambda: setattr(self, "_loader", None))
        self._loader.start()

    def _on_model_loaded(self, ok: bool, msg: str):
        dot = self._sidebar.model_dot
        if ok:
            dot.setText("  ●  Mistral 7B ready")
            dot.setStyleSheet(
                "color: #6CCB5F; font-size: 11px; background: transparent; padding: 5px 14px;"
            )
            self._status_lbl.setText("Mistral 7B loaded — AI features active")
            page = self._stack.currentWidget()
            if hasattr(page, "refresh"):
                page.refresh()
        else:
            dot.setText("  ✕  Model failed")
            dot.setStyleSheet(
                "color: #FF99A4; font-size: 11px; background: transparent; padding: 5px 14px;"
            )
            self._status_lbl.setText(f"Model error: {msg[:80]}")
