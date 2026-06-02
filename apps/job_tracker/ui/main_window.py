import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame, QStatusBar,
    QDialog, QFormLayout, QLineEdit, QTextEdit, QComboBox,
    QDialogButtonBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

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
from ui.workers            import LLMLoaderWorker, EmailSyncWorker
import modules.llm_summarizer as ls


NAV = [
    ("Overview",      "⌂"),
    ("Applications",  "◫"),
    ("Data",          "⊞"),
    ("Campaign",      "✉"),
    ("Mail",          "✆"),
    ("Replies",       "↩"),
    ("AI Assistant",  "✦"),
    ("Resume",        "◈"),
    ("Settings",      "⚙"),
]


class ComposeDialog(QDialog):
    def __init__(self, app_id, parent=None):
        super().__init__(parent)
        conn = get_db()
        self._app  = dict(conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone())
        self._tmpls = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
        conn.close()
        self._app_id = app_id
        self.setWindowTitle(f"Compose — {self._app.get('company','')}")
        self.setMinimumSize(660, 560)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setSpacing(12); lay.setContentsMargins(20,20,20,20)

        # Template row
        trow = QHBoxLayout(); trow.addWidget(QLabel("Template:"))
        self.tmplCb = QComboBox(); self.tmplCb.addItem("— select —", None)
        for t in self._tmpls: self.tmplCb.addItem(t["name"], t["id"])
        trow.addWidget(self.tmplCb, 1)
        lb = QPushButton("Load"); lb.setObjectName("subtleBtn"); lb.setFixedWidth(60)
        lb.clicked.connect(self._load_tmpl); trow.addWidget(lb)
        lay.addLayout(trow)

        form = QFormLayout(); form.setSpacing(10)
        self.toField = QLineEdit(self._app.get("contact_email","") or ""); self.toField.setReadOnly(True)
        self.subjField = QLineEdit()
        self.subjField.setPlaceholderText(
            f"Application for {self._app.get('position','role')} at {self._app.get('company','company')}"
        )
        self.bodyField = QTextEdit(); self.bodyField.setMinimumHeight(280)
        self.bodyField.setPlaceholderText("Email body…")
        form.addRow("To:", self.toField)
        form.addRow("Subject:", self.subjField)
        form.addRow("Body:", self.bodyField)
        lay.addLayout(form)

        ai_btn = QPushButton("✦  Generate with Mistral")
        ai_btn.clicked.connect(self._ai_gen); lay.addWidget(ai_btn)

        btns = QHBoxLayout()
        self.appleBtn = QPushButton("Send via Apple Mail")
        self.appleBtn.setObjectName("accentBtn"); self.appleBtn.clicked.connect(self._send_apple)
        btns.addWidget(self.appleBtn)

        smtpBtn = QPushButton("Send via SMTP (tracked)")
        smtpBtn.clicked.connect(self._send_smtp); btns.addWidget(smtpBtn)

        cancel = QPushButton("Cancel"); cancel.setObjectName("subtleBtn")
        cancel.clicked.connect(self.reject); btns.addWidget(cancel)
        lay.addLayout(btns)

    def _load_tmpl(self):
        tid = self.tmplCb.currentData()
        if not tid: return
        conn = get_db()
        t = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
        conn.close()
        if t:
            def fill(s):
                return (s or "").replace("{company}", self._app.get("company","") or "") \
                                .replace("{position}", self._app.get("position","") or "") \
                                .replace("{contact_name}", self._app.get("contact_name","Hiring Manager") or "")
            self.subjField.setText(fill(t["subject"]))
            self.bodyField.setPlainText(fill(t["body"]))

    def _ai_gen(self):
        if ls._get_llm() is None:
            QMessageBox.warning(self, "LLM", "Load the model in Settings first."); return
        from modules.apple_mail_sender import generate_personalized_intro, build_email_body, generate_subject
        from database import get_setting
        company = self._app.get("company", "your company")
        pos     = self._app.get("position", "")
        intro = generate_personalized_intro(company, self._app.get("notes",""))
        self.bodyField.setPlainText(build_email_body(company, intro))
        self.subjField.setText(generate_subject(
            company, pos,
            get_setting("sender_name", ""), get_setting("sender_role", ""),
        ))

    def _send_apple(self):
        if not self.subjField.text().strip() or not self.bodyField.toPlainText().strip():
            QMessageBox.warning(self, "Required", "Subject and body are required."); return
        from modules.apple_mail_sender import run_bulk_campaign
        result = run_bulk_campaign([self._app_id], sleep_seconds=0)
        if result["sent"]:
            QMessageBox.information(self, "Sent", "Email sent via Apple Mail!"); self.accept()
        else:
            err = result["errors"][0] if result["errors"] else "Unknown error"
            QMessageBox.critical(self, "Failed", err)

    def _send_smtp(self):
        subj = self.subjField.text().strip(); body = self.bodyField.toPlainText().strip()
        if not subj or not body:
            QMessageBox.warning(self, "Required", "Subject and body are required."); return
        try:
            from modules.email_sender import send_tracked_email
            r = send_tracked_email(self._app_id, subj, body)
            QMessageBox.information(self, "Sent", f"Sent with tracking!\nUUID: {r['uuid']}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "SMTP Error", str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JobTracker — AI Job Application Assistant")
        self.setMinimumSize(1120, 740)
        self._loader = None
        self._sync_worker = None
        self._build()
        self._setup_sync_timer()
        self._nav(0)
        # Load model 400ms after window shows — avoids Metal crash on startup error
        QTimer.singleShot(400, self._auto_load_model)

    def _build(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(208)
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(0,0,0,0); sl.setSpacing(0)

        # Brand
        brand = QWidget()
        brand.setStyleSheet("background: transparent; border-bottom: 1px solid rgba(255,255,255,0.06);")
        bl = QVBoxLayout(brand); bl.setContentsMargins(18,16,18,14); bl.setSpacing(2)
        title = QLabel("✦  JobTracker"); title.setObjectName("appTitle")
        sub   = QLabel("AI Application Manager"); sub.setObjectName("appSubtitle")
        bl.addWidget(title); bl.addWidget(sub)
        sl.addWidget(brand)

        # Nav buttons
        nav_w = QWidget(); nav_w.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(nav_w); nl.setContentsMargins(0,8,0,8); nl.setSpacing(2)
        self._nav_btns = []
        for i, (label, icon) in enumerate(NAV):
            btn = QPushButton(f"  {icon}  {label}"); btn.setObjectName("navBtn")
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda _, idx=i: self._nav(idx))
            nl.addWidget(btn); self._nav_btns.append(btn)
        nl.addStretch()
        sl.addWidget(nav_w, 1)

        # Sidebar footer
        self.modelDot = QLabel("  ◉  Loading model…")
        self.modelDot.setStyleSheet(
            "color: #FCE100; font-size: 11px; background: transparent; padding: 6px 12px;"
        )
        sl.addWidget(self.modelDot)
        self.syncDot = QLabel("  Auto-sync: every 15 min")
        self.syncDot.setStyleSheet(
            "color: rgba(0,0,0,0.35); font-size: 11px; background: transparent; padding: 2px 12px 12px 12px;"
        )
        sl.addWidget(self.syncDot)
        root.addWidget(sidebar)

        # ── Pages ────────────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.dashPage  = DashboardPage()
        self.appsPage  = ApplicationsPage()
        self.dataPage  = SpreadsheetPage()
        self.campPage  = CampaignPage()
        self.mailPage  = MailPage()
        self.replPage  = RepliesPage()
        self.asst      = AssistantPage()
        self.resumePage = ResumePage()
        self.settPage   = SettingsPage()

        for p in [self.dashPage, self.appsPage, self.dataPage, self.campPage,
                  self.mailPage, self.replPage, self.asst, self.resumePage, self.settPage]:
            self.stack.addWidget(p)

        self.appsPage.compose_requested.connect(self._compose)
        root.addWidget(self.stack, 1)

        # Status bar
        sb = QStatusBar(); sb.setFixedHeight(26); self.setStatusBar(sb)
        self._statusMsg = QLabel("Ready")
        self._statusMsg.setStyleSheet("color: rgba(0,0,0,0.42); background: transparent;")
        sb.addWidget(self._statusMsg)

        self.settPage.load_settings()

    def _nav(self, idx):
        for i, btn in enumerate(self._nav_btns):
            btn.setProperty("active", "true" if i == idx else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)
        self.stack.setCurrentIndex(idx)
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    def _setup_sync_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_sync)
        self._timer.start(15 * 60 * 1000)

    def _auto_sync(self):
        if self._sync_worker: return
        self._sync_worker = EmailSyncWorker()
        self._sync_worker.done.connect(self._on_auto_sync)
        self._sync_worker.finished.connect(lambda: setattr(self, '_sync_worker', None))
        self._sync_worker.start()

    def _on_auto_sync(self, count, errors):
        if count:
            self.syncDot.setText(f"  ✓  {count} new repl{'y' if count==1 else 'ies'}")
            self.syncDot.setStyleSheet(
                "color: #6CCB5F; font-size: 11px; background: transparent; padding: 2px 12px 12px 12px;"
            )
            if self.stack.currentWidget() in (self.replPage, self.dashPage, self.dataPage):
                self.stack.currentWidget().refresh()
        else:
            self.syncDot.setText("  Auto-sync: every 15 min")

    def _auto_load_model(self):
        path = get_setting("llm_model_path",
                           "/Users/abhay1703/Desktop/Todays Folder/mistral-7b-instruct-v0.2.Q4_K_M.gguf")
        if not path or not os.path.exists(path):
            self.modelDot.setText("  ◯  No model — see Settings")
            self.modelDot.setStyleSheet(
                "color: #FCE100; font-size: 11px; background: transparent; padding: 6px 12px;"
            )
            return

        set_setting("llm_model_path", path)
        n_ctx = int(get_setting("llm_context", 8192))
        n_gpu = int(get_setting("llm_gpu_layers", 35))

        self._loader = LLMLoaderWorker(path, n_ctx, n_gpu)
        self._loader.done.connect(self._on_model_loaded)
        self._loader.finished.connect(lambda: setattr(self, '_loader', None))
        self._loader.start()

    def _on_model_loaded(self, ok, msg):
        if ok:
            self.modelDot.setText("  ●  Mistral 7B ready")
            self.modelDot.setStyleSheet(
                "color: #6CCB5F; font-size: 11px; background: transparent; padding: 6px 12px;"
            )
            self._statusMsg.setText("Mistral 7B loaded — AI features active")
            # Refresh current page if it cares
            page = self.stack.currentWidget()
            if hasattr(page, "refresh"): page.refresh()
        else:
            self.modelDot.setText("  ✕  Model failed")
            self.modelDot.setStyleSheet(
                "color: #FF99A4; font-size: 11px; background: transparent; padding: 6px 12px;"
            )
            self._statusMsg.setText(f"Model error: {msg[:80]}")

    def _compose(self, app_id):
        dlg = ComposeDialog(app_id, self)
        dlg.exec()
        self.appsPage.refresh()
