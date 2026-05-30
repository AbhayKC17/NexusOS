"""
Settings page — two email accounts, zero passwords.
  Google / Gmail  : OAuth2 browser flow (bundled credentials)
  Outlook / School: Apple Mail SSO (AppleScript — no password)
"""
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QFileDialog, QMessageBox, QDialog,
    QFormLayout, QGroupBox, QTabWidget, QTextEdit,
    QScrollArea, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer
from database import get_setting, set_setting
from ui.workers import LLMLoaderWorker, OAuthWorker
import modules.llm_summarizer as ls


class _OAuthWaitDialog(QDialog):
    """Shown while the user authenticates in the browser."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in with Google")
        self.setMinimumWidth(420)
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(18)

        title = QLabel("Connect Google Account")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #EA4335; background: transparent;"
        )
        lay.addWidget(title)

        info = QLabel(
            "Your browser has opened Google's sign-in page.\n\n"
            "Sign in with your Google account and click Allow on the\n"
            "permissions screen — this dialog will close automatically."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: rgba(0,0,0,0.65); font-size: 13px; background: transparent;"
        )
        lay.addWidget(info)

        self._wait_lbl = QLabel("Waiting for authentication")
        self._wait_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._wait_lbl.setStyleSheet(
            "color: #FCE100; font-size: 13px; background: transparent; padding: 8px;"
        )
        lay.addWidget(self._wait_lbl)

        self._dot = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("subtleBtn")
        cancel.setFixedHeight(34)
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel)

    def _tick(self):
        self._dot = (self._dot + 1) % 4
        self._wait_lbl.setText("Waiting for authentication" + "." * self._dot)

    def accept(self):
        self._timer.stop()
        self._wait_lbl.setText("✓  Connected!")
        self._wait_lbl.setStyleSheet(
            "color: #6CCB5F; font-size: 13px; background: transparent; padding: 8px;"
        )
        super().accept()

    def reject(self):
        self._timer.stop()
        super().reject()


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader       = None
        self._oauth_worker = None
        self._oauth_dlg    = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        t = QLabel("Settings")
        t.setObjectName("pageTitle")
        root.addWidget(t)

        tabs = QTabWidget()
        tabs.addTab(self._tab_profile(), "Sender Profile")
        tabs.addTab(self._tab_email(),   "Email Accounts")
        tabs.addTab(self._tab_llm(),     "Local LLM")
        tabs.addTab(self._tab_guide(),   "Guide")
        root.addWidget(tabs, 1)

        save = QPushButton("  Save Settings")
        save.setObjectName("accentBtn")
        save.setFixedHeight(40)
        save.clicked.connect(self._save)
        root.addWidget(save)

    # ── Sender Profile ────────────────────────────────────────────────────────
    def _tab_profile(self):
        w = QWidget()
        lay = QFormLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(13)

        def f(ph):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            return e

        self.sName     = f("Abhay Kumar Choudhary")
        self.sRole     = f("Product Manager - Digital Supply Chain")
        self.sPitch    = f("digital supply chain PM, Python automation, process improvement")
        self.sLinkedin = f("https://linkedin.com/in/abhaykumarchoudhary2947/")

        self.sResume = QLineEdit()
        self.sResume.setPlaceholderText("/Users/abhay1703/Desktop/Abhay_Resume.pdf")
        browse = QPushButton("Browse…")
        browse.setObjectName("subtleBtn")
        browse.setFixedWidth(90)
        browse.clicked.connect(self._browse_resume)
        rrow = QHBoxLayout()
        rrow.addWidget(self.sResume)
        rrow.addWidget(browse)

        self.resumeStatus = QLabel("")
        self.resumeStatus.setStyleSheet("font-size: 12px; background: transparent;")

        lay.addRow("Your Name:",     self.sName)
        lay.addRow("Target Role:",   self.sRole)
        lay.addRow("Key Strengths:", self.sPitch)
        lay.addRow("LinkedIn URL:",  self.sLinkedin)
        lay.addRow("Resume PDF:",    rrow)
        lay.addRow("",               self.resumeStatus)
        return w

    def _browse_resume(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Resume PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            self.sResume.setText(path)
            self._update_resume_status(path)

    def _update_resume_status(self, path):
        if path and os.path.isfile(path):
            self.resumeStatus.setText(f"✓  {os.path.basename(path)}")
            self.resumeStatus.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
        elif path:
            self.resumeStatus.setText("✗  File not found at this path")
            self.resumeStatus.setStyleSheet("color: #FF99A4; font-size: 12px; background: transparent;")
        else:
            self.resumeStatus.setText("")

    # ── Email Accounts ────────────────────────────────────────────────────────
    def _tab_email(self):
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(w)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(20)

        # ── Google / Gmail (multiple accounts) ───────────────────────────────
        g_box = QGroupBox("Google / Gmail  ·  Multiple Accounts")
        g_box.setStyleSheet(
            "QGroupBox { border: 2px solid rgba(234,67,53,0.8); border-radius: 10px; "
            "margin-top: 12px; color: #EA4335; font-weight: 700; font-size: 13px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; }"
        )
        gf = QVBoxLayout(g_box)
        gf.setContentsMargins(18, 18, 18, 18)
        gf.setSpacing(12)

        g_note = QLabel(
            "Connect any number of Gmail accounts. Each can send emails independently — "
            "great for running simultaneous campaigns from different addresses.\n"
            "Sign in once; tokens are refreshed automatically."
        )
        g_note.setWordWrap(True)
        g_note.setStyleSheet("color: rgba(0,0,0,0.65); font-size: 12px; background: transparent;")
        gf.addWidget(g_note)

        # Dynamic account list
        self._google_accounts_frame = QFrame()
        self._google_accounts_frame.setStyleSheet("background: transparent;")
        self._google_accounts_lay = QVBoxLayout(self._google_accounts_frame)
        self._google_accounts_lay.setContentsMargins(0, 0, 0, 0)
        self._google_accounts_lay.setSpacing(6)
        gf.addWidget(self._google_accounts_frame)

        add_btn = QPushButton("  + Add Google Account  →")
        add_btn.setFixedHeight(42)
        add_btn.setStyleSheet(
            "QPushButton { background: #EA4335; color: #fff; border-radius: 8px; "
            "font-size: 14px; font-weight: 600; border: none; }"
            "QPushButton:hover { background: #c5392d; }"
            "QPushButton:disabled { background: rgba(234,67,53,0.4); }"
        )
        add_btn.clicked.connect(self._google_add_account)
        self._google_add_btn = add_btn
        gf.addWidget(add_btn)
        lay.addWidget(g_box)

        # ── Outlook via Apple Mail ────────────────────────────────────────────
        a_box = QGroupBox("Outlook / School Email  ·  via Apple Mail")
        a_box.setStyleSheet(
            "QGroupBox { border: 2px solid rgba(0,120,212,0.7); border-radius: 10px; "
            "margin-top: 12px; color: #60CDFF; font-weight: 700; font-size: 13px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; }"
        )
        af = QVBoxLayout(a_box)
        af.setContentsMargins(18, 18, 18, 18)
        af.setSpacing(14)

        a_note = QLabel(
            "Your school Outlook is already signed in to Apple Mail — no password needed here. "
            "JobTracker reads your Outlook inbox via Apple Mail to detect company replies "
            "and match them to your job applications."
        )
        a_note.setWordWrap(True)
        a_note.setStyleSheet("color: rgba(0,0,0,0.65); font-size: 12px; background: transparent;")
        af.addWidget(a_note)

        acct_row = QHBoxLayout()
        acct_row.addWidget(QLabel("Account:"))
        self.applMailAcct = QComboBox()
        self.applMailAcct.setFixedHeight(34)
        self.applMailAcct.addItem("— click Detect to find accounts —")
        acct_row.addWidget(self.applMailAcct, 1)
        af.addLayout(acct_row)

        self.ssoStatusLbl = QLabel("")
        self.ssoStatusLbl.setStyleSheet("font-size: 12px; background: transparent;")
        af.addWidget(self.ssoStatusLbl)

        aml_btn_row = QHBoxLayout()
        aml_btn_row.setSpacing(8)

        self.ssoRefreshBtn = QPushButton("⟳  Detect Accounts")
        self.ssoRefreshBtn.setObjectName("subtleBtn")
        self.ssoRefreshBtn.setFixedHeight(36)
        self.ssoRefreshBtn.clicked.connect(self._detect_apple_mail_accounts)
        aml_btn_row.addWidget(self.ssoRefreshBtn)

        self.ssoTestBtn = QPushButton("Test Sync")
        self.ssoTestBtn.setObjectName("subtleBtn")
        self.ssoTestBtn.setFixedHeight(36)
        self.ssoTestBtn.clicked.connect(self._test_apple_mail_sync)
        aml_btn_row.addWidget(self.ssoTestBtn)

        self.ssoUseBtn = QPushButton("✓  Use for Reply Sync")
        self.ssoUseBtn.setObjectName("accentBtn")
        self.ssoUseBtn.setFixedHeight(36)
        self.ssoUseBtn.clicked.connect(self._set_apple_mail_mode)
        aml_btn_row.addWidget(self.ssoUseBtn)
        aml_btn_row.addStretch()
        af.addLayout(aml_btn_row)
        lay.addWidget(a_box)

        lay.addStretch()

        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(scroll)
        return outer

    # ── Google multi-account helpers ──────────────────────────────────────────

    def _rebuild_google_accounts_list(self):
        """Repopulate the connected-accounts widget from disk."""
        import time as _time
        lay = self._google_accounts_lay
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            from modules.oauth_manager import list_google_accounts
            accounts = list_google_accounts()
        except Exception:
            accounts = []

        if not accounts:
            lbl = QLabel("  No Google accounts connected yet.")
            lbl.setStyleSheet("color: rgba(0,0,0,0.5); font-size: 12px; background: transparent;")
            lay.addWidget(lbl)
            return

        for acct in accounts:
            email      = acct.get("email", "?")
            still_ok   = _time.time() < acct.get("expires_at", 0) - 60
            status_ico = "●" if still_ok else "○"
            status_col = "#6CCB5F" if still_ok else "#FCE100"

            row_w = QWidget()
            row_w.setStyleSheet(
                "background: #FAFAFA; border-radius: 8px;"
            )
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(10)

            dot = QLabel(status_ico)
            dot.setStyleSheet(
                f"color: {status_col}; font-size: 13px; background: transparent;"
            )
            rl.addWidget(dot)

            email_lbl = QLabel(email)
            email_lbl.setStyleSheet(
                "color: #EFEFEF; font-size: 13px; background: transparent;"
            )
            rl.addWidget(email_lbl, 1)

            reconnect_btn = QPushButton("↺  Reconnect")
            reconnect_btn.setObjectName("subtleBtn")
            reconnect_btn.setFixedHeight(28)
            reconnect_btn.clicked.connect(lambda _, e=email: self._google_reconnect(e))
            rl.addWidget(reconnect_btn)

            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("subtleBtn")
            delete_btn.setFixedHeight(28)
            delete_btn.setStyleSheet(
                "QPushButton { color: #FF99A4; } QPushButton:hover { background: rgba(255,80,80,0.15); }"
            )
            delete_btn.clicked.connect(lambda _, e=email: self._google_delete_account(e))
            rl.addWidget(delete_btn)

            lay.addWidget(row_w)

    def _google_add_account(self):
        self._google_add_btn.setEnabled(False)
        self._google_add_btn.setText("Opening browser…")
        self._oauth_dlg = _OAuthWaitDialog(self)
        self._oauth_worker = OAuthWorker("google")
        self._oauth_worker.done.connect(self._google_auth_done)
        self._oauth_worker.error.connect(self._google_auth_error)
        self._oauth_worker.finished.connect(lambda: setattr(self, "_oauth_worker", None))
        self._oauth_worker.start()
        self._oauth_dlg.exec()

    def _google_reconnect(self, email: str):
        self._google_add_btn.setEnabled(False)
        self._google_add_btn.setText("Opening browser…")
        self._oauth_dlg = _OAuthWaitDialog(self)
        self._oauth_worker = OAuthWorker("google")
        self._oauth_worker.done.connect(self._google_auth_done)
        self._oauth_worker.error.connect(self._google_auth_error)
        self._oauth_worker.finished.connect(lambda: setattr(self, "_oauth_worker", None))
        self._oauth_worker.start()
        self._oauth_dlg.exec()

    def _google_auth_done(self, email: str):
        if self._oauth_dlg:
            self._oauth_dlg.accept()
            self._oauth_dlg = None
        self._google_add_btn.setEnabled(True)
        self._google_add_btn.setText("  + Add Google Account  →")
        self._rebuild_google_accounts_list()
        QMessageBox.information(
            self, "Gmail Connected",
            f"Connected as  {email}\n\n"
            "You can now send emails, track replies, and use the Mail tab "
            "from this account.\n\nAdd more accounts to send from multiple Gmail addresses.",
        )

    def _google_auth_error(self, err: str):
        if self._oauth_dlg:
            self._oauth_dlg.reject()
            self._oauth_dlg = None
        self._google_add_btn.setEnabled(True)
        self._google_add_btn.setText("  + Add Google Account  →")
        QMessageBox.critical(self, "Google Sign-in Failed", err)

    def _google_delete_account(self, email: str):
        if QMessageBox.question(
            self, "Remove Account",
            f"Remove  {email}?\nYou can always reconnect it later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            from modules.oauth_manager import google_disconnect_account
            google_disconnect_account(email)
        except Exception:
            pass
        self._rebuild_google_accounts_list()

    # ── Apple Mail SSO helpers ────────────────────────────────────────────────

    def _detect_apple_mail_accounts(self):
        self.ssoRefreshBtn.setEnabled(False)
        self.ssoRefreshBtn.setText("Detecting…")
        from modules.apple_mail_reader import list_accounts
        accounts = list_accounts()
        self.applMailAcct.clear()

        if accounts == ["__permission_denied__"]:
            self.applMailAcct.addItem("— permission denied —")
            self.ssoStatusLbl.setText("✕  macOS blocked AppleScript access")
            self.ssoStatusLbl.setStyleSheet("color: #FF99A4; font-size: 12px; background: transparent;")
            QMessageBox.warning(
                self, "Permission Required",
                "macOS is blocking AppleScript access to Apple Mail.\n\n"
                "Fix (10 seconds):\n"
                "  System Settings → Privacy & Security → Automation\n"
                "  → Find your terminal / Python → enable Mail\n\n"
                "Then click Detect Accounts again.",
            )
        elif accounts:
            self.applMailAcct.addItem("— select account —")
            for a in accounts:
                self.applMailAcct.addItem(a)
            self.ssoStatusLbl.setText(f"✓  Found {len(accounts)} account(s)")
            self.ssoStatusLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
            saved = get_setting("apple_mail_account", "")
            if saved:
                idx = self.applMailAcct.findText(saved)
                if idx >= 0:
                    self.applMailAcct.setCurrentIndex(idx)
        else:
            self.applMailAcct.addItem("— Apple Mail not running or no accounts —")
            self.ssoStatusLbl.setText("Open Apple Mail first, then click Detect again")
            self.ssoStatusLbl.setStyleSheet("color: #FCE100; font-size: 12px; background: transparent;")

        self.ssoRefreshBtn.setEnabled(True)
        self.ssoRefreshBtn.setText("⟳  Detect Accounts")

    def _test_apple_mail_sync(self):
        acct = self.applMailAcct.currentText()
        if not acct or acct.startswith("—"):
            QMessageBox.warning(self, "No Account", "Select an Apple Mail account first.")
            return
        self.ssoTestBtn.setEnabled(False)
        self.ssoTestBtn.setText("Scanning…")
        from modules.apple_mail_reader import sync_replies
        result = sync_replies(acct)
        self.ssoTestBtn.setEnabled(True)
        self.ssoTestBtn.setText("Test Sync")
        n = result.get("new_replies", 0)
        errs = result.get("errors", [])
        if errs:
            QMessageBox.warning(self, "Scan Result", "Errors:\n" + "\n".join(errs))
        else:
            QMessageBox.information(
                self, "Scan Result",
                f"Scan complete — {n} new repl{'y' if n == 1 else 'ies'} found.",
            )

    def _set_apple_mail_mode(self):
        acct = self.applMailAcct.currentText()
        if not acct or acct.startswith("—"):
            QMessageBox.warning(self, "No Account", "Select an Apple Mail account first.")
            return
        set_setting("apple_mail_account", acct)
        set_setting("sync_mode", "apple_mail")
        self.ssoStatusLbl.setText(f"✓  Active — {acct}")
        self.ssoStatusLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
        QMessageBox.information(
            self, "Outlook Sync Active",
            f"Reply tracking is now using Apple Mail  ({acct}).\n\n"
            "Apple Mail just needs to stay open and syncing — no passwords ever needed.",
        )

    # ── Local LLM ─────────────────────────────────────────────────────────────
    def _tab_llm(self):
        w = QWidget()
        lay = QFormLayout(w)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        self.llmPath = QLineEdit()
        self.llmPath.setPlaceholderText(
            "/Users/abhay1703/Desktop/Todays Folder/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
        )
        b2 = QPushButton("Browse…")
        b2.setObjectName("subtleBtn")
        b2.setFixedWidth(90)
        b2.clicked.connect(self._browse_model)
        mrow = QHBoxLayout()
        mrow.addWidget(self.llmPath)
        mrow.addWidget(b2)

        self.llmCtx = QLineEdit()
        self.llmCtx.setPlaceholderText("8192")
        self.llmGpu = QLineEdit()
        self.llmGpu.setPlaceholderText("35  (Apple Silicon Metal GPU)")

        self.modelStatusLbl = QLabel("● Not loaded")
        self.modelStatusLbl.setStyleSheet("color: #FCE100; background: transparent;")

        load = QPushButton("Load Model Now")
        load.setObjectName("accentBtn")
        load.clicked.connect(self._load_model)

        # ── Groq cloud AI ─────────────────────────────────────────────────────
        groq_sep = QLabel("─" * 40)
        groq_sep.setStyleSheet("color: rgba(255,255,255,0.12); background: transparent;")

        groq_hdr = QLabel("✦  Groq Cloud AI  (recommended — fast, free tier)")
        groq_hdr.setStyleSheet(
            "color: #A78BFA; font-size: 13px; font-weight: 700; background: transparent; padding: 4px 0;"
        )

        self.groqKey = QLineEdit()
        self.groqKey.setPlaceholderText("gsk_…  (get yours free at console.groq.com)")
        self.groqKey.setEchoMode(QLineEdit.EchoMode.Password)

        show_key = QPushButton("Show")
        show_key.setObjectName("subtleBtn")
        show_key.setFixedWidth(56)
        show_key.setCheckable(True)
        show_key.toggled.connect(
            lambda v: self.groqKey.setEchoMode(
                QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password
            )
        )
        groq_row = QHBoxLayout()
        groq_row.addWidget(self.groqKey)
        groq_row.addWidget(show_key)

        self.groqStatusLbl = QLabel("")
        self.groqStatusLbl.setStyleSheet("font-size: 12px; background: transparent;")

        groq_note = QLabel(
            "When set: AI reply drafts and AI Composer use Groq (llama3-8b-8192) — "
            "no local GPU needed. Falls back to local Mistral 7B if Groq is unavailable."
        )
        groq_note.setWordWrap(True)
        groq_note.setStyleSheet(
            "color: rgba(0,0,0,0.5); font-size: 12px; background: transparent;"
        )

        lay.addRow("Model (.gguf):", mrow)
        lay.addRow("Context length:", self.llmCtx)
        lay.addRow("GPU Layers:", self.llmGpu)
        lay.addRow("Status:", self.modelStatusLbl)
        lay.addRow("", load)
        lay.addRow("", groq_sep)
        lay.addRow("", groq_hdr)
        lay.addRow("Groq API Key:", groq_row)
        lay.addRow("", self.groqStatusLbl)
        lay.addRow("", groq_note)

        note = QLabel(
            "<b>GPU Layers = 35</b> → Apple Metal (fast, M1/M2/M3/M4)<br>"
            "<b>GPU Layers = 0</b> → CPU only (always works)<br>"
            "Your model is already at the default path."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: rgba(0,0,0,0.5); font-size: 12px; background: transparent; padding: 8px 0;"
        )
        note.setTextFormat(Qt.TextFormat.RichText)
        lay.addRow("", note)
        return w

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GGUF Model", "", "GGUF Models (*.gguf)"
        )
        if path:
            self.llmPath.setText(path)

    def _load_model(self):
        path = self.llmPath.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Model", f"File not found:\n{path}")
            return
        n_ctx = int(self.llmCtx.text().strip() or 8192)
        n_gpu = int(self.llmGpu.text().strip() or 35)
        self.modelStatusLbl.setText("● Loading…")
        self.modelStatusLbl.setStyleSheet("color: #FCE100; background: transparent;")
        ls._llm = None
        self._loader = LLMLoaderWorker(path, n_ctx, n_gpu)
        self._loader.done.connect(self._on_model_loaded)
        self._loader.finished.connect(lambda: setattr(self, "_loader", None))
        self._loader.start()

    def _on_model_loaded(self, ok, msg):
        if ok:
            self.modelStatusLbl.setText("● Mistral 7B loaded ✓")
            self.modelStatusLbl.setStyleSheet("color: #6CCB5F; background: transparent;")
        else:
            self.modelStatusLbl.setText(f"● Error: {msg[:90]}")
            self.modelStatusLbl.setStyleSheet("color: #FF99A4; background: transparent;")

    # ── Guide ─────────────────────────────────────────────────────────────────
    def _tab_guide(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setStyleSheet("background: #1C1C1C; border: none; font-size: 13px; padding: 20px;")
        te.setHtml("""
<style>
body { color: #FFFFFF; font-family: Arial; line-height: 1.7; padding: 4px; }
h2  { color: #EA4335; margin: 16px 0 8px; }
h3  { color: rgba(255,255,255,0.8); margin: 12px 0 6px; }
code { background: #333; color: #6CCB5F; padding: 2px 6px; border-radius: 4px; }
.ok   { background: rgba(108,203,95,0.1); border-left: 3px solid #6CCB5F;
        padding: 10px 14px; border-radius: 4px; margin: 8px 0; }
.warn { background: rgba(252,225,0,0.08); border-left: 3px solid #FCE100;
        padding: 10px 14px; border-radius: 4px; margin: 8px 0; }
</style>

<h2>Gmail — already set up, just sign in</h2>
<div class="ok">
  ✓ Your app credentials are built in — just click <b>Sign in with Google</b>,
  approve permissions in the browser, and you're connected. No Client ID, no passwords.
</div>

<h3>Permissions requested</h3>
<p>JobTracker requests <code>https://mail.google.com/</code> — the same scope Apple Mail uses.
This covers everything: read inbox, sent, drafts, all folders; send emails on your behalf;
manage labels. Nothing is stored except the OAuth tokens on your local disk.</p>

<h3>First sign-in shows "This app isn't verified"</h3>
<p>Click <b>Advanced</b> → <b>Go to Personal_Assistant (unsafe)</b>. This warning appears
because the app hasn't gone through Google's formal review — it's safe, it's your own credential.</p>

<h2>Outlook / School Email — Apple Mail sync</h2>
<div class="ok">
  Your school Outlook is already in Apple Mail. JobTracker reads it via AppleScript —
  no password, no IMAP, nothing to configure. Just open Apple Mail and keep it running.
</div>

<h3>Setup (30 seconds)</h3>
<ol>
<li>Open <b>Apple Mail</b> and make sure your school account is syncing normally</li>
<li>In JobTracker → Settings → Email Accounts → click <b>Detect Accounts</b></li>
<li>Select your school account → click <b>Use for Reply Sync</b></li>
<li>Done — replies to your job applications will be detected automatically</li>
</ol>

<h2>How email tracking works</h2>
<p>Every campaign email is sent as HTML. A <b>14-digit TKEY</b> (SHA-256 of the subject)
is embedded as invisible 1px white text. When a company replies, JobTracker finds the TKEY,
links the reply to the right application, and Mistral 7B drafts a response for you.</p>
""")
        lay.addWidget(te)
        return w

    # ── Load / Save ───────────────────────────────────────────────────────────
    def load_settings(self):
        def g(k, d=""):
            return get_setting(k, d) or ""

        # Profile
        self.sName.setText(g("sender_name",    "Abhay Kumar Choudhary"))
        self.sRole.setText(g("sender_role",    "Product Manager - Digital Supply Chain"))
        self.sPitch.setText(g("sender_pitch",  "digital supply chain PM, Python automation, process improvement"))
        self.sLinkedin.setText(g("sender_linkedin"))
        resume = g("resume_path")
        self.sResume.setText(resume)
        self._update_resume_status(resume)

        # Google multi-account list
        self._rebuild_google_accounts_list()

        # Groq
        self.groqKey.setText(g("groq_api_key"))
        try:
            from modules.groq_client import is_configured
            if is_configured():
                self.groqStatusLbl.setText("✓  Groq configured — AI drafts use cloud AI")
                self.groqStatusLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
            else:
                self.groqStatusLbl.setText("○  Not configured — AI drafts use local model only")
                self.groqStatusLbl.setStyleSheet("color: rgba(0,0,0,0.5); font-size: 12px; background: transparent;")
        except Exception:
            pass

        # Apple Mail account
        saved_acct = g("apple_mail_account")
        if saved_acct:
            self.applMailAcct.clear()
            self.applMailAcct.addItem(saved_acct)
            self.applMailAcct.setCurrentIndex(0)
            if g("sync_mode") == "apple_mail":
                self.ssoStatusLbl.setText(f"✓  Active — {saved_acct}")
                self.ssoStatusLbl.setStyleSheet(
                    "color: #6CCB5F; font-size: 12px; background: transparent;"
                )

        # LLM
        default_model = "/Users/abhay1703/Desktop/Todays Folder/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
        self.llmPath.setText(g("llm_model_path", default_model))
        self.llmCtx.setText(g("llm_context",     "8192"))
        self.llmGpu.setText(g("llm_gpu_layers",  "35"))
        if ls._get_llm() is not None:
            self.modelStatusLbl.setText("● Mistral 7B loaded ✓")
            self.modelStatusLbl.setStyleSheet("color: #6CCB5F; background: transparent;")

    def _save(self):
        pairs = {
            "sender_name":     self.sName.text().strip(),
            "sender_role":     self.sRole.text().strip(),
            "sender_pitch":    self.sPitch.text().strip(),
            "sender_linkedin": self.sLinkedin.text().strip(),
            "resume_path":     self.sResume.text().strip(),
            "llm_model_path":  self.llmPath.text().strip(),
            "llm_context":     self.llmCtx.text().strip(),
            "llm_gpu_layers":  self.llmGpu.text().strip(),
            "groq_api_key":    self.groqKey.text().strip(),
        }
        for k, v in pairs.items():
            if v:
                set_setting(k, v)
        self._update_resume_status(pairs.get("resume_path", ""))

        # Update Groq status indicator
        from modules.groq_client import is_configured
        if is_configured():
            self.groqStatusLbl.setText("✓  Groq configured — AI drafts use cloud AI")
            self.groqStatusLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
        else:
            self.groqStatusLbl.setText("○  Not configured — AI drafts use local model only")
            self.groqStatusLbl.setStyleSheet("color: rgba(0,0,0,0.5); font-size: 12px; background: transparent;")

        QMessageBox.information(self, "Saved", "Settings saved.")
