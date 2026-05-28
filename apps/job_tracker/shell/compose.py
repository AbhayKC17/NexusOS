"""
ComposeDialog — standalone email compose window.
Extracted from the main window to keep shell/window.py clean.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QMessageBox,
)

from database import get_db
import modules.llm_summarizer as ls


class ComposeDialog(QDialog):
    def __init__(self, app_id: int, parent=None):
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
        self.setWindowTitle(f"Compose — {self._app.get('company', '')}")
        self.setMinimumSize(680, 580)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 22, 24, 20)

        # Template picker row
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Template:"))
        self.tmplCb = QComboBox()
        self.tmplCb.addItem("— select —", None)
        for t in self._tmpls:
            self.tmplCb.addItem(t["name"], t["id"])
        trow.addWidget(self.tmplCb, 1)
        load_btn = QPushButton("Load")
        load_btn.setObjectName("subtleBtn")
        load_btn.setFixedWidth(60)
        load_btn.clicked.connect(self._load_tmpl)
        trow.addWidget(load_btn)
        lay.addLayout(trow)

        # Fields
        self.toField = QLineEdit(self._app.get("contact_email", "") or "")
        self.toField.setReadOnly(True)
        self.toField.setPlaceholderText("Recipient")

        self.subjField = QLineEdit()
        self.subjField.setPlaceholderText(
            f"Application for {self._app.get('position', 'role')} "
            f"at {self._app.get('company', 'company')}"
        )

        self.bodyField = QTextEdit()
        self.bodyField.setMinimumHeight(300)
        self.bodyField.setPlaceholderText("Email body…")

        for label, widget in [
            ("To:", self.toField),
            ("Subject:", self.subjField),
            ("Body:", self.bodyField),
        ]:
            row_lbl = QLabel(label)
            row_lbl.setFixedWidth(58)
            row = QHBoxLayout()
            row.addWidget(row_lbl)
            row.addWidget(widget)
            lay.addLayout(row)

        # AI generate
        ai_btn = QPushButton("✦  Generate with Mistral")
        ai_btn.clicked.connect(self._ai_gen)
        lay.addWidget(ai_btn)

        # Action buttons
        btns = QHBoxLayout()
        btns.setSpacing(8)

        self.appleBtn = QPushButton("Send via Apple Mail")
        self.appleBtn.setObjectName("accentBtn")
        self.appleBtn.clicked.connect(self._send_apple)

        smtp_btn = QPushButton("Send via SMTP (tracked)")
        smtp_btn.clicked.connect(self._send_smtp)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("subtleBtn")
        cancel.clicked.connect(self.reject)

        btns.addWidget(self.appleBtn)
        btns.addWidget(smtp_btn)
        btns.addStretch()
        btns.addWidget(cancel)
        lay.addLayout(btns)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _load_tmpl(self):
        tid = self.tmplCb.currentData()
        if not tid:
            return
        conn = get_db()
        t = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
        conn.close()
        if not t:
            return

        def fill(s):
            return (s or "").replace(
                "{company}", self._app.get("company", "") or ""
            ).replace(
                "{position}", self._app.get("position", "") or ""
            ).replace(
                "{contact_name}", self._app.get("contact_name", "Hiring Manager") or ""
            )

        self.subjField.setText(fill(t["subject"]))
        self.bodyField.setPlainText(fill(t["body"]))

    def _ai_gen(self):
        if ls._get_llm() is None:
            QMessageBox.warning(self, "LLM", "Load the model in Settings first.")
            return
        from modules.apple_mail_sender import generate_personalized_intro, build_email_body
        intro = generate_personalized_intro(
            self._app.get("company", ""), self._app.get("notes", "")
        )
        self.bodyField.setPlainText(
            build_email_body(self._app.get("company", ""), intro)
        )
        self.subjField.setText(
            f"Exploring {self._app.get('position', 'product')} opportunities "
            f"at {self._app.get('company', 'your company')}"
        )

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
                self, "Sent", f"Sent with tracking!\nUUID: {r['uuid']}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "SMTP Error", str(e))
