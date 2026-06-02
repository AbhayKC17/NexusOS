import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QStatusBar,
    QDialog, QFormLayout, QLineEdit, QTextEdit, QComboBox,
    QDialogButtonBox, QMessageBox, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPixmap

from database import get_db, get_setting, set_setting
from dashboard      import DashboardPage
from applications   import ApplicationsPage
from spreadsheet    import SpreadsheetPage
from campaign       import CampaignPage
from mail           import MailPage
from replies        import RepliesPage
from assistant      import AssistantPage
from resume_builder import ResumePage
from settings       import SettingsPage
from ui.workers     import LLMLoaderWorker, EmailSyncWorker
import modules.llm_summarizer as ls
from core.widgets   import FadeStackedWidget


# ─────────────────────────────────────────────────────────────────────────────
#  Navigation definition
# ─────────────────────────────────────────────────────────────────────────────

NAV = [
    ("Overview",      "⌂",  "Dashboard and quick stats"),
    ("Applications",  "◫",  "All tracked companies"),
    ("Data",          "⊞",  "Import & edit spreadsheet"),
    ("Campaign",      "✉",  "Bulk email campaigns"),
    ("Mail",          "✆",  "Built-in inbox reader"),
    ("Replies",       "↩",  "AI reply drafts"),
    ("AI Assistant",  "✦",  "Chat with Mistral 7B"),
    ("Resume",        "◈",  "AI-tailored resume builder"),
    ("Settings",      "⚙",  "Preferences & credentials"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  FluentNavButton — custom painted nav item
# ─────────────────────────────────────────────────────────────────────────────

class FluentNavButton(QPushButton):
    """
    A navigation rail button with:
    • Left-side animated selection indicator bar
    • Smooth background hover state
    • Icon (unicode) + label layout
    """

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._label = label
        self._active = False
        self.setObjectName("navBtn")
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)
        self._build_layout()

    def _build_layout(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(10)

        self._icon_lbl = QLabel(self._icon)
        self._icon_lbl.setFixedWidth(20)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent; font-size: 15px;")
        lay.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(self._label)
        self._text_lbl.setStyleSheet(
            "background: transparent; font-size: 13px;"
        )
        lay.addWidget(self._text_lbl, 1)

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        # Sync icon/label colour
        if active:
            self._icon_lbl.setStyleSheet(
                "background: transparent; font-size: 15px; color: #0067C0;"
            )
            self._text_lbl.setStyleSheet(
                "background: transparent; font-size: 13px; "
                "color: #0067C0; font-weight: 600;"
            )
        else:
            self._icon_lbl.setStyleSheet(
                "background: transparent; font-size: 15px; color: rgba(0,0,0,0.55);"
            )
            self._text_lbl.setStyleSheet(
                "background: transparent; font-size: 13px; color: rgba(0,0,0,0.55);"
            )


# ─────────────────────────────────────────────────────────────────────────────
#  StatusDot — sidebar footer indicator
# ─────────────────────────────────────────────────────────────────────────────

class _StatusDot(QWidget):
    """Small coloured circle + status text row."""

    COLORS = {
        "ok":      "#107C10",
        "warn":    "#9D5D00",
        "error":   "#C42B1C",
        "loading": "#0067C0",
        "off":     "rgba(0,0,0,0.30)",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 4, 14, 4)
        lay.setSpacing(7)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(
            "font-size: 8px; background: transparent; color: rgba(0,0,0,0.28);"
        )
        lay.addWidget(self._dot)

        self._lbl = QLabel("—")
        self._lbl.setStyleSheet(
            "font-size: 11px; background: transparent; color: rgba(0,0,0,0.40);"
        )
        lay.addWidget(self._lbl, 1)

    def set_state(self, text: str, state: str = "off"):
        color = self.COLORS.get(state, self.COLORS["off"])
        self._dot.setStyleSheet(
            f"font-size: 8px; background: transparent; color: {color};"
        )
        text_color = (
            color if state in ("ok", "warn", "error", "loading")
            else "rgba(0,0,0,0.40)"
        )
        self._lbl.setStyleSheet(
            f"font-size: 11px; background: transparent; color: {text_color};"
        )
        self._lbl.setText(text)


# ─────────────────────────────────────────────────────────────────────────────
#  ComposeDialog
# ─────────────────────────────────────────────────────────────────────────────

class ComposeDialog(QDialog):
    def __init__(self, app_id, parent=None):
        super().__init__(parent)
        conn = get_db()
        self._app   = dict(conn.execute(
            "SELECT * FROM applications WHERE id=?", (app_id,)
        ).fetchone())
        self._tmpls = conn.execute(
            "SELECT * FROM templates ORDER BY name"
        ).fetchall()
        conn.close()
        self._app_id = app_id
        self.setWindowTitle(f"Compose  —  {self._app.get('company','')}")
        self.setMinimumSize(680, 580)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 24, 24, 24)

        # Template row
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Template:"))
        self.tmplCb = QComboBox()
        self.tmplCb.addItem("— select —", None)
        for t in self._tmpls:
            self.tmplCb.addItem(t["name"], t["id"])
        trow.addWidget(self.tmplCb, 1)
        lb = QPushButton("Load")
        lb.setObjectName("subtleBtn")
        lb.setFixedWidth(68)
        lb.clicked.connect(self._load_tmpl)
        trow.addWidget(lb)
        lay.addLayout(trow)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.toField   = QLineEdit(self._app.get("contact_email", "") or "")
        self.toField.setReadOnly(True)
        self.subjField = QLineEdit()
        self.subjField.setPlaceholderText(
            f"Application for {self._app.get('position','role')} "
            f"at {self._app.get('company','company')}"
        )
        self.bodyField = QTextEdit()
        self.bodyField.setMinimumHeight(280)
        self.bodyField.setPlaceholderText("Email body…")
        form.addRow("To:", self.toField)
        form.addRow("Subject:", self.subjField)
        form.addRow("Body:", self.bodyField)
        lay.addLayout(form)

        ai_btn = QPushButton("  ✦  Generate with AI")
        ai_btn.clicked.connect(self._ai_gen)
        lay.addWidget(ai_btn)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.appleBtn = QPushButton("Send via Apple Mail")
        self.appleBtn.setObjectName("accentBtn")
        self.appleBtn.clicked.connect(self._send_apple)
        btns.addWidget(self.appleBtn)

        smtpBtn = QPushButton("Send via SMTP")
        smtpBtn.clicked.connect(self._send_smtp)
        btns.addWidget(smtpBtn)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("subtleBtn")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        lay.addLayout(btns)

    def _load_tmpl(self):
        tid = self.tmplCb.currentData()
        if not tid:
            return
        conn = get_db()
        t = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
        conn.close()
        if t:
            def fill(s):
                return (
                    (s or "")
                    .replace("{company}",      self._app.get("company",      "") or "")
                    .replace("{position}",     self._app.get("position",     "") or "")
                    .replace("{contact_name}", self._app.get("contact_name", "Hiring Manager") or "")
                )
            self.subjField.setText(fill(t["subject"]))
            self.bodyField.setPlainText(fill(t["body"]))

    def _ai_gen(self):
        if ls._get_llm() is None:
            QMessageBox.warning(self, "AI not ready", "Load the model in Settings first.")
            return
        from modules.apple_mail_sender import generate_personalized_intro, build_email_body, generate_subject
        company = self._app.get("company", "your company")
        pos     = self._app.get("position", "")
        intro   = generate_personalized_intro(company, self._app.get("notes", ""))
        self.bodyField.setPlainText(build_email_body(company, intro))
        self.subjField.setText(generate_subject(
            company, pos,
            get_setting("sender_name", ""),
            get_setting("sender_role", ""),
        ))

    def _send_apple(self):
        if not self.subjField.text().strip() or not self.bodyField.toPlainText().strip():
            QMessageBox.warning(self, "Required", "Subject and body are required.")
            return
        from modules.apple_mail_sender import run_bulk_campaign
        result = run_bulk_campaign([self._app_id], sleep_seconds=0)
        if result["sent"]:
            QMessageBox.information(self, "Sent", "Email sent via Apple Mail!")
            self.accept()
        else:
            err = result["errors"][0] if result["errors"] else "Unknown error"
            QMessageBox.critical(self, "Failed", err)

    def _send_smtp(self):
        subj = self.subjField.text().strip()
        body = self.bodyField.toPlainText().strip()
        if not subj or not body:
            QMessageBox.warning(self, "Required", "Subject and body are required.")
            return
        try:
            from modules.email_sender import send_tracked_email
            r = send_tracked_email(self._app_id, subj, body)
            QMessageBox.information(
                self, "Sent", f"Email sent with tracking key!\nUUID: {r['uuid']}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "SMTP Error", str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  MainWindow
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JobTracker")
        self.setMinimumSize(1180, 760)
        self._loader      = None
        self._sync_worker = None
        self._build()
        self._setup_sync_timer()
        self._nav(0, instant=True)
        QTimer.singleShot(400, self._auto_load_model)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        # Brand header
        brand = QWidget()
        brand.setObjectName("appBrand")
        brand.setFixedHeight(64)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(12)

        # App icon circle
        icon_w = QLabel("JT")
        icon_w.setFixedSize(34, 34)
        icon_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_w.setStyleSheet(
            "background: #0067C0; color: white; border-radius: 8px; "
            "font-size: 13px; font-weight: 700;"
        )
        bl.addWidget(icon_w)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("JobTracker")
        title.setObjectName("appTitle")
        sub = QLabel("AI Application Manager")
        sub.setObjectName("appSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        bl.addLayout(title_col)
        sl.addWidget(brand)

        # Nav section label
        nav_section = QLabel("NAVIGATION")
        nav_section.setObjectName("sectionTitle")
        nav_section.setContentsMargins(16, 14, 0, 6)
        sl.addWidget(nav_section)

        # Nav buttons
        nav_w = QWidget()
        nav_w.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(nav_w)
        nl.setContentsMargins(6, 0, 6, 0)
        nl.setSpacing(1)

        self._nav_btns: list[FluentNavButton] = []
        for i, (label, icon, _tip) in enumerate(NAV):
            btn = FluentNavButton(icon, label)
            btn.clicked.connect(lambda _, idx=i: self._nav(idx))
            nl.addWidget(btn)
            self._nav_btns.append(btn)

        nl.addStretch()
        sl.addWidget(nav_w, 1)

        # Sidebar divider
        div = QFrame()
        div.setObjectName("sidebarDivider")
        sl.addWidget(div)

        # Footer: model + sync status
        self._model_dot = _StatusDot()
        sl.addWidget(self._model_dot)

        self._sync_dot = _StatusDot()
        self._sync_dot.set_state("Auto-sync every 15 min", "off")
        sl.addWidget(self._sync_dot)

        root.addWidget(sidebar)

        # ── Page area ─────────────────────────────────────────────────────────
        self.stack = FadeStackedWidget(duration=160)

        self.dashPage   = DashboardPage()
        self.appsPage   = ApplicationsPage()
        self.dataPage   = SpreadsheetPage()
        self.campPage   = CampaignPage()
        self.mailPage   = MailPage()
        self.replPage   = RepliesPage()
        self.asst       = AssistantPage()
        self.resumePage = ResumePage()
        self.settPage   = SettingsPage()

        for p in [
            self.dashPage, self.appsPage, self.dataPage, self.campPage,
            self.mailPage, self.replPage, self.asst, self.resumePage, self.settPage,
        ]:
            self.stack.addWidget(p)

        self.appsPage.compose_requested.connect(self._compose)
        self.dataPage.data_changed.connect(self.campPage.refresh)
        self.appsPage.data_changed.connect(self.campPage.refresh)

        root.addWidget(self.stack, 1)

        # Status bar
        sb = QStatusBar()
        sb.setFixedHeight(26)
        self.setStatusBar(sb)
        self._statusMsg = QLabel("Ready")
        self._statusMsg.setStyleSheet(
            "color: rgba(0,0,0,0.42); background: transparent;"
        )
        sb.addWidget(self._statusMsg)

        self.settPage.load_settings()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _nav(self, idx: int, instant: bool = False):
        for i, btn in enumerate(self._nav_btns):
            btn.set_active(i == idx)
        if instant:
            self.stack.setCurrentIndexInstant(idx)
        else:
            self.stack.setCurrentIndex(idx)
        page = self.stack.widget(idx)
        if hasattr(page, "refresh"):
            page.refresh()

    # ── Email sync ────────────────────────────────────────────────────────────

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
        if count:
            self._sync_dot.set_state(
                f"✓  {count} new repl{'y' if count == 1 else 'ies'}", "ok"
            )
            cur = self.stack.currentWidget()
            if cur in (self.replPage, self.dashPage, self.dataPage):
                cur.refresh()
        else:
            self._sync_dot.set_state("Auto-sync every 15 min", "off")

    # ── Model loading ─────────────────────────────────────────────────────────

    def _auto_load_model(self):
        path = get_setting(
            "llm_model_path",
            "/Users/abhay1703/Desktop/Todays Folder/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        )
        if not path or not os.path.exists(path):
            self._model_dot.set_state("No model — check Settings", "warn")
            return

        set_setting("llm_model_path", path)
        n_ctx = int(get_setting("llm_context", 8192))
        n_gpu = int(get_setting("llm_gpu_layers", 35))

        self._model_dot.set_state("Loading Mistral 7B…", "loading")
        self._loader = LLMLoaderWorker(path, n_ctx, n_gpu)
        self._loader.done.connect(self._on_model_loaded)
        self._loader.finished.connect(lambda: setattr(self, "_loader", None))
        self._loader.start()

    def _on_model_loaded(self, ok: bool, msg: str):
        if ok:
            self._model_dot.set_state("Mistral 7B  ·  ready", "ok")
            self._statusMsg.setText("Mistral 7B loaded — AI features active")
            page = self.stack.currentWidget()
            if hasattr(page, "refresh"):
                page.refresh()
        else:
            self._model_dot.set_state("Model load failed", "error")
            self._statusMsg.setText(f"Model error: {msg[:80]}")

    # ── Compose dialog ────────────────────────────────────────────────────────

    def _compose(self, app_id: str):
        dlg = ComposeDialog(app_id, self)
        dlg.exec()
        self.appsPage.refresh()
