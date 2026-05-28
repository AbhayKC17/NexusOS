"""
Built-in Mail page — compose, inbox, view, reply.
Uses direct SMTP + IMAP. No Apple Mail, no Outlook, no AppleScript.

Layout:
  Left sidebar   — folder list + account status
  Centre panel   — message list
  Right panel    — message view / compose form
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QLineEdit, QFrame,
    QSplitter, QSizePolicy, QMessageBox, QScrollArea, QCheckBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from database import get_setting, subject_to_tracking_key as _subject_to_tkey
from ui.workers import MailFetchWorker, MailBodyWorker, MailSendWorker



# ── Compose panel (shown on right when composing) ────────────────────────────

class ComposePanel(QWidget):
    sent    = pyqtSignal()
    cancel  = pyqtSignal()

    def __init__(self, to: str = "", subject: str = "", body: str = "", parent=None):
        super().__init__(parent)
        self._worker = None
        self._build(to, subject, body)

    def _build(self, to, subject, body):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        hdr = QLabel("✉  New Email")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700; color: #FFFFFF; background: transparent;")
        lay.addWidget(hdr)

        def field(placeholder, text=""):
            e = QLineEdit()
            e.setPlaceholderText(placeholder)
            if text: e.setText(text)
            e.setFixedHeight(34)
            return e

        self.toField   = field("To:  recipient@company.com  (comma-separate multiple)", to)
        self.ccField   = field("CC:  (optional)")
        self.subjField = field("Subject", subject)
        lay.addWidget(self.toField)
        lay.addWidget(self.ccField)
        lay.addWidget(self.subjField)

        self.bodyEdit = QTextEdit()
        self.bodyEdit.setPlaceholderText("Write your email here…")
        self.bodyEdit.setPlainText(body)
        self.bodyEdit.setStyleSheet(
            "background: #1E1E1E; border: 1px solid rgba(255,255,255,0.1); "
            "border-radius: 6px; font-size: 13px; color: #E8E8E8; padding: 10px;"
        )
        lay.addWidget(self.bodyEdit, 1)

        opts_row = QHBoxLayout(); opts_row.setSpacing(16)
        self.trackChk  = QCheckBox("Embed TKEY tracking")
        self.trackChk.setChecked(True)
        self.trackChk.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
        opts_row.addWidget(self.trackChk)

        self.resumeChk = QCheckBox("Attach resume")
        resume = get_setting("resume_path", "")
        self.resumeChk.setEnabled(bool(resume))
        self.resumeChk.setChecked(bool(resume))
        self.resumeChk.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
        opts_row.addWidget(self.resumeChk)
        opts_row.addStretch()
        lay.addLayout(opts_row)

        self.statusLbl = QLabel("")
        self.statusLbl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px; background: transparent;")
        lay.addWidget(self.statusLbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.sendBtn = QPushButton("✉  Send Email")
        self.sendBtn.setObjectName("accentBtn")
        self.sendBtn.setFixedHeight(36)
        self.sendBtn.clicked.connect(self._send)
        btn_row.addWidget(self.sendBtn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("subtleBtn")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.cancel.emit)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def _send(self):
        to_raw  = self.toField.text().strip()
        subject = self.subjField.text().strip()
        body    = self.bodyEdit.toPlainText().strip()

        if not to_raw or not subject or not body:
            QMessageBox.warning(self, "Required", "To, Subject and Body are all required.")
            return

        to_emails = [e.strip() for e in to_raw.replace(";", ",").split(",") if e.strip() and "@" in e]
        cc_raw = self.ccField.text().strip()
        if cc_raw:
            to_emails += [e.strip() for e in cc_raw.replace(";", ",").split(",") if e.strip() and "@" in e]

        tkey = _subject_to_tkey(subject) if self.trackChk.isChecked() else ""
        resume = get_setting("resume_path", "") if self.resumeChk.isChecked() else None

        self.sendBtn.setEnabled(False)
        self.sendBtn.setText("Sending…")
        self.statusLbl.setText("Connecting to SMTP…")

        self._worker = MailSendWorker(to_emails, subject, body, resume, tkey)
        self._worker.done.connect(self._on_sent)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
        self._worker.start()

    def _on_sent(self):
        self.sendBtn.setEnabled(True)
        self.sendBtn.setText("✉  Send Email")
        self.statusLbl.setText("✓  Sent successfully!")
        self.statusLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
        self.sent.emit()

    def _on_error(self, msg: str):
        self.sendBtn.setEnabled(True)
        self.sendBtn.setText("✉  Send Email")
        self.statusLbl.setText("")
        QMessageBox.critical(self, "Send Failed", msg)


# ── Message view panel ────────────────────────────────────────────────────────

class MessageView(QWidget):
    reply_requested = pyqtSignal(str, str, str)  # to, subject, quote

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        self.fromLbl    = QLabel("")
        self.fromLbl.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.6); background: transparent;")
        self.subjectLbl = QLabel("")
        self.subjectLbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #FFFFFF; background: transparent;")
        self.subjectLbl.setWordWrap(True)
        self.dateLbl    = QLabel("")
        self.dateLbl.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.35); background: transparent;")

        lay.addWidget(self.subjectLbl)
        lay.addWidget(self.fromLbl)
        lay.addWidget(self.dateLbl)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.07);")
        lay.addWidget(sep)

        self.bodyEdit = QTextEdit()
        self.bodyEdit.setReadOnly(True)
        self.bodyEdit.setStyleSheet(
            "background: transparent; border: none; font-size: 13px; "
            "color: rgba(255,255,255,0.85); line-height: 1.7; padding: 4px;"
        )
        lay.addWidget(self.bodyEdit, 1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.replyBtn = QPushButton("↩  Reply")
        self.replyBtn.setObjectName("accentBtn")
        self.replyBtn.setFixedHeight(32)
        self.replyBtn.clicked.connect(self._reply)
        btn_row.addWidget(self.replyBtn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._data = {}

    def show_message(self, d: dict):
        self._data = d
        self.subjectLbl.setText(d.get("subject", ""))
        self.fromLbl.setText(f"From: {d.get('from', '—')}")
        self.dateLbl.setText(d.get("date", ""))
        self.bodyEdit.setPlainText(d.get("body", ""))

    def clear(self):
        self._data = {}
        self.subjectLbl.setText("")
        self.fromLbl.setText("")
        self.dateLbl.setText("")
        self.bodyEdit.clear()

    def _reply(self):
        if not self._data:
            return
        to      = self._data.get("reply_to") or self._data.get("from", "")
        subject = "Re: " + self._data.get("subject", "")
        body    = self._data.get("body", "")
        quote   = "\n\n---\n" + "\n".join("> " + l for l in body.splitlines()[:20])
        self.reply_requested.emit(to, subject, quote)


# ── Main Mail page ────────────────────────────────────────────────────────────

class MailPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fetch_worker = None
        self._body_worker  = None
        self._current_folder = "INBOX"
        self._messages: list = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        topbar = QWidget()
        topbar.setStyleSheet("background: #1C1C1C; border-bottom: 1px solid rgba(255,255,255,0.07);")
        tbl = QHBoxLayout(topbar); tbl.setContentsMargins(20, 10, 20, 10); tbl.setSpacing(10)

        title = QLabel("Mail"); title.setObjectName("pageTitle")
        tbl.addWidget(title)
        tbl.addStretch()

        self.accountLbl = QLabel("Not configured")
        self.accountLbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 12px; background: transparent;")
        tbl.addWidget(self.accountLbl)

        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setObjectName("subtleBtn"); refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self.refresh)
        tbl.addWidget(refresh_btn)

        self.composeBtn = QPushButton("✉  Compose")
        self.composeBtn.setObjectName("accentBtn"); self.composeBtn.setFixedHeight(30)
        self.composeBtn.clicked.connect(self._compose_new)
        tbl.addWidget(self.composeBtn)

        root.addWidget(topbar)

        # ── Body (three-panel splitter) ───────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # LEFT: folder list — min-width so it scales with the window
        left = QWidget()
        left.setMinimumWidth(148)
        left.setMaximumWidth(200)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left.setStyleSheet("background: #181818; border-right: 1px solid rgba(255,255,255,0.06);")
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 12, 0, 12); ll.setSpacing(2)

        ll.addWidget(self._folder_btn("Inbox",  "📥", "INBOX"))
        ll.addWidget(self._folder_btn("Sent",   "📤", "Sent Items"))
        ll.addWidget(self._folder_btn("Drafts", "📝", "Drafts"))
        ll.addWidget(self._folder_btn("Junk",   "🗑", "Junk Email"))
        ll.addStretch()

        self.statusLbl = QLabel("")
        self.statusLbl.setWordWrap(True)
        self.statusLbl.setStyleSheet(
            "color: rgba(255,255,255,0.3); font-size: 10px; background: transparent; padding: 8px;"
        )
        ll.addWidget(self.statusLbl)
        splitter.addWidget(left)

        # CENTRE: message list
        centre = QWidget()
        centre.setStyleSheet("background: #1A1A1A; border-right: 1px solid rgba(255,255,255,0.06);")
        cl = QVBoxLayout(centre); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        self.msgList = QListWidget()
        self.msgList.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.05); }"
            "QListWidget::item:selected { background: rgba(0,120,212,0.25); }"
            "QListWidget::item:hover { background: rgba(255,255,255,0.04); }"
        )
        self.msgList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.msgList.currentRowChanged.connect(self._on_message_selected)
        cl.addWidget(self.msgList)

        self.loadingLbl = QLabel("Select a folder to load messages.")
        self.loadingLbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loadingLbl.setStyleSheet(
            "color: rgba(255,255,255,0.3); font-size: 13px; background: transparent; padding: 30px;"
        )
        cl.addWidget(self.loadingLbl)
        splitter.addWidget(centre)

        # RIGHT: message view / compose
        self._right = QWidget()
        rl = QVBoxLayout(self._right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        self.msgView = MessageView()
        self.msgView.reply_requested.connect(self._compose_reply)
        rl.addWidget(self.msgView)

        self.composeView = ComposePanel()
        self.composeView.sent.connect(self._on_sent)
        self.composeView.cancel.connect(self._show_msg_view)
        self.composeView.setVisible(False)
        rl.addWidget(self.composeView)
        splitter.addWidget(self._right)

        splitter.setSizes([160, 340, 540])

    def _folder_btn(self, label: str, icon: str, folder: str) -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setFlat(True)
        btn.setFixedHeight(36)
        btn.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,0.6); text-align: left; "
            "padding: 0 12px; border: none; font-size: 13px; background: transparent; }"
            "QPushButton:hover { background: rgba(255,255,255,0.05); color: #FFFFFF; }"
            "QPushButton:pressed { background: rgba(0,120,212,0.2); }"
        )
        btn.clicked.connect(lambda: self._load_folder(folder))
        return btn

    # ── Folder / message loading ───────────────────────────────────────────────

    def refresh(self):
        from modules.mail_client import is_configured
        cfg = is_configured()
        if cfg["imap"]:
            user = get_setting("imap_user", "")
            self.accountLbl.setText(user)
        else:
            self.accountLbl.setText("IMAP not configured — see Settings")
        self._load_folder(self._current_folder)

    def _load_folder(self, folder: str):
        if self._fetch_worker:
            return
        self._current_folder = folder
        self.msgList.clear()
        self.loadingLbl.setText(f"Loading {folder}…")
        self.loadingLbl.setVisible(True)
        self.statusLbl.setText(f"Loading {folder}…")

        self._fetch_worker = MailFetchWorker(folder, limit=60)
        self._fetch_worker.done.connect(self._on_messages_loaded)
        self._fetch_worker.error.connect(self._on_load_error)
        self._fetch_worker.finished.connect(lambda: setattr(self, '_fetch_worker', None))
        self._fetch_worker.start()

    def _on_messages_loaded(self, messages: list):
        self._messages = messages
        self.msgList.clear()
        self.loadingLbl.setVisible(False)

        if not messages:
            self.loadingLbl.setText("No messages.")
            self.loadingLbl.setVisible(True)
        else:
            for m in messages:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, m["uid"])
                subject = m["subject"][:50] or "(no subject)"
                sender  = m["from"][:30]
                date    = m["date"][:16] if m["date"] else ""
                item.setText(f"{'● ' if m['unread'] else '  '}{sender}\n  {subject}\n  {date}")
                if m["unread"]:
                    f = item.font(); f.setBold(True); item.setFont(f)
                    item.setForeground(QColor("#FFFFFF"))
                else:
                    item.setForeground(QColor("rgba(255,255,255,0.6)"))
                self.msgList.addItem(item)

        self.statusLbl.setText(f"{len(messages)} messages")

    def _on_load_error(self, msg: str):
        self.loadingLbl.setText(f"Failed to load.\n{msg[:100]}")
        self.loadingLbl.setVisible(True)
        self.statusLbl.setText("Error")

    def _on_message_selected(self, row: int):
        if row < 0 or row >= len(self._messages):
            return
        uid = self._messages[row]["uid"]
        self._show_msg_view()
        self.msgView.clear()
        self.msgView.subjectLbl.setText("Loading…")

        if self._body_worker:
            return
        self._body_worker = MailBodyWorker(uid, self._current_folder)
        self._body_worker.done.connect(self._on_body_loaded)
        self._body_worker.error.connect(lambda e: self.msgView.bodyEdit.setPlainText(f"Error: {e}"))
        self._body_worker.finished.connect(lambda: setattr(self, '_body_worker', None))
        self._body_worker.start()

    def _on_body_loaded(self, d: dict):
        self.msgView.show_message(d)

    # ── Compose / reply ────────────────────────────────────────────────────────

    def _compose_new(self):
        self._replace_compose(ComposePanel())

    def _compose_reply(self, to: str, subject: str, quote: str):
        self._replace_compose(ComposePanel(to=to, subject=subject, body=quote))

    def _replace_compose(self, panel: ComposePanel):
        lay = self._right.layout()
        # Remove old compose if any
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, ComposePanel):
                lay.removeWidget(w); w.deleteLater(); break
        panel.sent.connect(self._on_sent)
        panel.cancel.connect(self._show_msg_view)
        self.msgView.setVisible(False)
        lay.addWidget(panel)
        panel.setVisible(True)

    def _show_msg_view(self):
        lay = self._right.layout()
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, ComposePanel):
                lay.removeWidget(w); w.deleteLater(); break
        self.msgView.setVisible(True)

    def _on_sent(self):
        self._show_msg_view()
        QMessageBox.information(self, "Sent", "Email sent successfully!")
        if self._current_folder in ("INBOX", "Sent Items", "Sent"):
            self._load_folder(self._current_folder)
