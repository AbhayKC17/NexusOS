"""
Replies & AI Drafts page.

Two sections:
  1. AI Drafts — inbox_index entries with a TKEY match and an AI-generated reply draft.
     The draft is editable and can be sent directly from the app via Apple Mail.
  2. Tracked Replies — classic TRK-UUID matched replies stored in the replies table.

Header buttons:
  - Index Inbox  → scans ALL emails, detects TKEY, generates AI drafts (InboxIndexWorker)
  - Sync Replies → classic TRK-UUID scan (EmailSyncWorker)
"""

import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTextEdit, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from database import get_db, get_setting
from ui.workers import EmailSyncWorker, InboxIndexWorker, DraftRegenWorker
import modules.llm_summarizer as ls


# ── Draft card (TKEY-matched, AI reply) ──────────────────────────────────────

class DraftCard(QFrame):
    send_clicked   = pyqtSignal(int, str, str, str)  # row_id, to_email, subject, draft
    regen_clicked  = pyqtSignal(int)                 # row_id

    def __init__(self, d: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._row_id    = d["id"]
        self._to_email  = _parse_email(d.get("from_email", ""))
        self._subject   = "Re: " + (d.get("subject") or "")
        self._draft_txt = d.get("ai_reply_draft") or ""
        self._regen_worker = None

        self.setStyleSheet(
            "DraftCard { border: 1px solid rgba(0,200,100,0.35); border-radius: 10px; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        top = QHBoxLayout()
        has_draft = bool(self._draft_txt)
        badge_text  = "✦ AI DRAFT" if has_draft else "⏳ PENDING DRAFT"
        badge_color = "#00C864"    if has_draft else "#FCE100"
        badge_bg    = "rgba(0,200,100,0.2)" if has_draft else "rgba(252,225,0,0.15)"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_color}; "
            "font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 7px;"
        )
        top.addWidget(badge)
        top.addSpacing(8)

        company_lbl = QLabel(f"<b>{d.get('company') or d.get('from_email', '—')}</b>")
        company_lbl.setStyleSheet("font-size: 14px; color: #FFFFFF; background: transparent;")
        top.addWidget(company_lbl)
        top.addStretch()

        dt = QLabel((d.get("received_at") or "")[:10])
        dt.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 11px; background: transparent;")
        top.addWidget(dt)
        lay.addLayout(top)

        if d.get("position"):
            pos = QLabel(d["position"])
            pos.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px; background: transparent;")
            lay.addWidget(pos)

        from_lbl = QLabel(f"From: {d.get('from_email', '—')}")
        from_lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 11px; background: transparent;")
        lay.addWidget(from_lbl)

        subj_lbl = QLabel(f"Subject: {d.get('subject', '—')}")
        subj_lbl.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px; background: transparent;")
        lay.addWidget(subj_lbl)

        # ── Original reply body (collapsible) ─────────────────────────────────
        show_orig = QPushButton("▶  Show received email")
        show_orig.setObjectName("subtleBtn")
        show_orig.setFixedHeight(26)
        lay.addWidget(show_orig)

        orig_view = QTextEdit()
        orig_view.setReadOnly(True)
        orig_view.setPlainText(d.get("body") or "")
        orig_view.setMaximumHeight(160)
        orig_view.setVisible(False)
        orig_view.setStyleSheet(
            "background: #1C1C1C; border: 1px solid rgba(255,255,255,0.08); "
            "border-radius: 6px; font-size: 12px; font-family: 'Courier New', monospace; padding: 8px;"
        )
        lay.addWidget(orig_view)

        def _toggle_orig():
            v = not orig_view.isVisible()
            orig_view.setVisible(v)
            show_orig.setText("▼  Hide received email" if v else "▶  Show received email")
        show_orig.clicked.connect(_toggle_orig)

        # ── AI Draft section ───────────────────────────────────────────────────
        draft_hdr = QHBoxLayout()
        self.draftLabel = QLabel(
            "✦  AI Reply Draft  (edit before sending)" if has_draft
            else "⚡  Click 'Generate with AI' to create a reply draft"
        )
        self.draftLabel.setStyleSheet(
            f"color: {'#00C864' if has_draft else '#FCE100'}; "
            "font-size: 11px; font-weight: 700; background: transparent;"
        )
        draft_hdr.addWidget(self.draftLabel)
        draft_hdr.addStretch()

        self.regenBtn = QPushButton("✦  Generate with AI" if not has_draft else "↻  Regenerate")
        self.regenBtn.setObjectName("subtleBtn")
        self.regenBtn.setFixedHeight(26)
        self.regenBtn.clicked.connect(self._regen)
        draft_hdr.addWidget(self.regenBtn)
        lay.addLayout(draft_hdr)

        self.draftEdit = QTextEdit()
        self.draftEdit.setPlainText(self._draft_txt)
        self.draftEdit.setMinimumHeight(160)
        self.draftEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.draftEdit.setStyleSheet(
            "background: #1A2A1A; border: 1px solid rgba(0,200,100,0.3); "
            "border-radius: 6px; font-size: 13px; color: #E8FFE8; padding: 10px;"
        )
        if not has_draft:
            self.draftEdit.setPlaceholderText(
                "Draft will appear here after generation.\n\n"
                "Make sure the Mistral model is loaded in Settings, then click 'Generate with AI'."
            )
        lay.addWidget(self.draftEdit)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_row.addStretch()

        self.sendBtn = QPushButton("✉  Send Reply via Apple Mail")
        self.sendBtn.setObjectName("accentBtn")
        self.sendBtn.setFixedHeight(32)
        self.sendBtn.clicked.connect(self._on_send)
        btn_row.addWidget(self.sendBtn)

        mark_btn = QPushButton("✓  Mark as Handled")
        mark_btn.setObjectName("subtleBtn")
        mark_btn.setFixedHeight(32)
        mark_btn.clicked.connect(self._mark_handled)
        btn_row.addWidget(mark_btn)

        lay.addLayout(btn_row)

    def _regen(self):
        if self._regen_worker:
            return
        if ls._get_llm() is None:
            QMessageBox.warning(
                self, "Model Not Loaded",
                "The Mistral model is not loaded yet.\n\n"
                "Go to Settings and load the model, then try again.\n\n"
                "The model loads automatically ~5 seconds after the app starts."
            )
            return
        self.regenBtn.setEnabled(False)
        self.regenBtn.setText("Generating…")

        self._regen_worker = DraftRegenWorker(self._row_id)
        self._regen_worker.done.connect(self._on_regen_done)
        self._regen_worker.error.connect(self._on_regen_error)
        self._regen_worker.finished.connect(lambda: setattr(self, '_regen_worker', None))
        self._regen_worker.start()

    def _on_regen_done(self, row_id: int, draft: str):
        self.regenBtn.setEnabled(True)
        self.regenBtn.setText("↻  Regenerate")
        self.draftEdit.setPlainText(draft)
        self.draftLabel.setText("✦  AI Reply Draft  (edit before sending)")
        self.draftLabel.setStyleSheet("color: #00C864; font-size: 11px; font-weight: 700; background: transparent;")

    def _on_regen_error(self, row_id: int, msg: str):
        self.regenBtn.setEnabled(True)
        self.regenBtn.setText("↻  Regenerate")
        QMessageBox.critical(self, "Generation Failed", msg)

    def _on_send(self):
        draft = self.draftEdit.toPlainText().strip()
        if not draft:
            QMessageBox.warning(self, "Empty Draft", "The draft is empty — please write or generate something first.")
            return
        self.send_clicked.emit(self._row_id, self._to_email, self._subject, draft)

    def _mark_handled(self):
        conn = get_db()
        conn.execute("UPDATE inbox_index SET reply_status='handled' WHERE id=?", (self._row_id,))
        conn.commit()
        conn.close()
        self.setVisible(False)


def _parse_email(raw: str) -> str:
    """Extract bare email from 'Name <email>' format."""
    if "<" in raw and ">" in raw:
        return raw.split("<")[1].rstrip(">").strip()
    return raw.strip()


# ── Classic TRK reply card ────────────────────────────────────────────────────

class ReplyCard(QFrame):
    def __init__(self, d: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        top = QHBoxLayout()
        co = QLabel(f"<b>{d.get('company') or d.get('from_email', '—')}</b>")
        co.setStyleSheet("font-size: 14px; color: #FFFFFF; background: transparent;")
        top.addWidget(co); top.addStretch()
        dt = QLabel((d.get("received_at") or "")[:10])
        dt.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 11px; background: transparent;")
        top.addWidget(dt)
        lay.addLayout(top)

        pos = QLabel(d.get("position") or "")
        pos.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px; background: transparent;")
        lay.addWidget(pos)

        subj = QLabel(f"Subject: {d.get('subject') or '—'}")
        subj.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px; background: transparent;")
        lay.addWidget(subj)

        from_lbl = QLabel(f"From: {d.get('from_email') or '—'}")
        from_lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 11px; background: transparent;")
        lay.addWidget(from_lbl)

        if d.get("summary"):
            ai_frame = QFrame()
            ai_frame.setStyleSheet(
                "QFrame { background: rgba(0,120,212,0.1); "
                "border: 1px solid rgba(0,120,212,0.25); border-radius: 6px; }"
            )
            ai_l = QVBoxLayout(ai_frame)
            ai_l.setContentsMargins(12, 10, 12, 10)
            ai_l.setSpacing(4)
            ai_tag = QLabel("✦  AI Summary")
            ai_tag.setStyleSheet("color: #60CDFF; font-size: 11px; font-weight: 700; background: transparent;")
            ai_l.addWidget(ai_tag)
            ai_txt = QLabel(d["summary"])
            ai_txt.setWordWrap(True)
            ai_txt.setStyleSheet(
                "color: rgba(255,255,255,0.85); font-size: 13px; line-height: 1.5; background: transparent;"
            )
            ai_l.addWidget(ai_txt)
            lay.addWidget(ai_frame)

        toggle = QPushButton("▶  Show full email")
        toggle.setObjectName("subtleBtn")
        toggle.setFixedHeight(28)
        lay.addWidget(toggle)

        body_view = QTextEdit()
        body_view.setReadOnly(True)
        body_view.setPlainText(d.get("body") or "")
        body_view.setMaximumHeight(200)
        body_view.setVisible(False)
        body_view.setStyleSheet(
            "background: #1C1C1C; border: 1px solid rgba(255,255,255,0.08); "
            "border-radius: 6px; font-size: 12px; font-family: 'Courier New', monospace; padding: 8px;"
        )
        lay.addWidget(body_view)

        def _toggle():
            v = not body_view.isVisible()
            body_view.setVisible(v)
            toggle.setText("▼  Hide email" if v else "▶  Show full email")
        toggle.clicked.connect(_toggle)


# ── Section header ────────────────────────────────────────────────────────────

class _SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px; font-weight: 700; "
            "letter-spacing: 1px; background: transparent; padding: 4px 0px;"
        )


# ── Main page ─────────────────────────────────────────────────────────────────

class RepliesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sync_worker  = None
        self._index_worker = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        # ── Header ────────────────────────────────────────────────────────────
        top = QHBoxLayout(); top.setSpacing(8)
        t = QLabel("Replies  &  AI Drafts"); t.setObjectName("pageTitle")
        top.addWidget(t); top.addStretch()

        self.statusLbl = QLabel("")
        self.statusLbl.setObjectName("pageSubtitle")
        top.addWidget(self.statusLbl)

        self.indexBtn = QPushButton("⚡  Index Inbox")
        self.indexBtn.setObjectName("accentBtn")
        self.indexBtn.setFixedHeight(32)
        self.indexBtn.setToolTip(
            "Scan ALL emails in your inbox.\n"
            "Messages with a TKEY get an AI-generated reply draft."
        )
        self.indexBtn.clicked.connect(self._index_inbox)
        top.addWidget(self.indexBtn)

        self.syncBtn = QPushButton("↻  Sync Replies")
        self.syncBtn.setObjectName("subtleBtn")
        self.syncBtn.setFixedHeight(32)
        self.syncBtn.setToolTip("Scan for [TRK-UUID] replies and update application statuses.")
        self.syncBtn.clicked.connect(self._sync)
        top.addWidget(self.syncBtn)

        root.addLayout(top)

        self.countLbl = QLabel("")
        self.countLbl.setObjectName("pageSubtitle")
        root.addWidget(self.countLbl)

        # ── Scrollable card list ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listWidget = QWidget()
        self.listLayout = QVBoxLayout(self.listWidget)
        self.listLayout.setContentsMargins(0, 0, 8, 0)
        self.listLayout.setSpacing(10)
        self.listLayout.addStretch()
        scroll.setWidget(self.listWidget)
        root.addWidget(scroll, 1)

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self):
        conn = get_db()

        # TKEY-matched drafts (not yet handled)
        drafts = conn.execute('''
            SELECT i.id, i.from_email, i.subject, i.body, i.received_at,
                   i.ai_reply_draft, i.reply_status,
                   a.company, a.position
            FROM inbox_index i
            LEFT JOIN applications a ON i.application_id = a.id
            WHERE i.tkey IS NOT NULL AND i.reply_status != 'handled'
            ORDER BY i.received_at DESC
        ''').fetchall()

        # Classic TRK replies
        trk_replies = conn.execute('''
            SELECT r.id, r.application_id, r.received_at, r.from_email, r.from_name,
                   r.subject, r.body, r.summary,
                   a.company, a.position
            FROM replies r JOIN applications a ON r.application_id = a.id
            ORDER BY r.received_at DESC
        ''').fetchall()
        conn.close()

        # Clear existing cards
        while self.listLayout.count() > 1:
            item = self.listLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pos = 0

        # ── AI Draft cards ────────────────────────────────────────────────────
        if drafts:
            hdr = _SectionHeader("AI DRAFTS  —  TKEY MATCHED")
            self.listLayout.insertWidget(pos, hdr); pos += 1

            draft_cols = ["id","from_email","subject","body","received_at",
                          "ai_reply_draft","reply_status","company","position"]
            for row in drafts:
                d = dict(zip(draft_cols, row))
                card = DraftCard(d)
                card.send_clicked.connect(self._send_draft)
                self.listLayout.insertWidget(pos, card); pos += 1

        # ── TRK reply cards ───────────────────────────────────────────────────
        if trk_replies:
            hdr2 = _SectionHeader("TRACKED REPLIES  —  TRK UUID")
            self.listLayout.insertWidget(pos, hdr2); pos += 1

            trk_cols = ["id","application_id","received_at","from_email","from_name",
                        "subject","body","summary","company","position"]
            for row in trk_replies:
                self.listLayout.insertWidget(pos, ReplyCard(dict(zip(trk_cols, row)))); pos += 1

        if not drafts and not trk_replies:
            empty = QLabel(
                "No replies yet.\n\n"
                "• Click  ⚡ Index Inbox  to scan all emails for TKEY matches and generate AI drafts.\n"
                "• Click  ↻ Sync Replies  to check for [TRK-UUID] tracking replies.\n\n"
                "Make sure Apple Mail or Outlook sync mode is configured in Settings."
            )
            empty.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.listLayout.insertWidget(0, empty)

        n_d = len(drafts); n_t = len(trk_replies)
        parts = []
        if n_d: parts.append(f"{n_d} AI draft{'s' if n_d!=1 else ''}")
        if n_t: parts.append(f"{n_t} tracked repl{'ies' if n_t!=1 else 'y'}")
        self.countLbl.setText("  ·  ".join(parts) if parts else "")

    # ── Index inbox ───────────────────────────────────────────────────────────

    def _index_inbox(self):
        if self._index_worker:
            return
        self.indexBtn.setEnabled(False)
        self.indexBtn.setText("Indexing…")
        self.statusLbl.setText("Scanning all emails…")

        self._index_worker = InboxIndexWorker()
        self._index_worker.done.connect(self._on_index_done)
        self._index_worker.finished.connect(lambda: setattr(self, '_index_worker', None))
        self._index_worker.start()

    def _on_index_done(self, result: dict):
        self.indexBtn.setEnabled(True)
        self.indexBtn.setText("⚡  Index Inbox")
        errors = result.get("errors", [])
        indexed = result.get("indexed", 0)
        matches = result.get("tkey_matches", 0)

        if errors and not indexed:
            self.statusLbl.setText(f"Error: {errors[0][:80]}")
        else:
            parts = []
            if indexed: parts.append(f"{indexed} new email{'s' if indexed!=1 else ''} indexed")
            if matches: parts.append(f"{matches} TKEY match{'es' if matches!=1 else ''}")
            self.statusLbl.setText("  ·  ".join(parts) if parts else "No new emails found")
        if indexed or matches:
            self.refresh()

    # ── Sync TRK replies ──────────────────────────────────────────────────────

    def _sync(self):
        if self._sync_worker:
            return
        self.syncBtn.setEnabled(False)
        self.syncBtn.setText("Syncing…")
        self.statusLbl.setText("Checking for TRK replies…")

        self._sync_worker = EmailSyncWorker()
        self._sync_worker.done.connect(self._on_sync_done)
        self._sync_worker.finished.connect(lambda: setattr(self, '_sync_worker', None))
        self._sync_worker.start()

    def _on_sync_done(self, count: int, errors: list):
        self.syncBtn.setEnabled(True)
        self.syncBtn.setText("↻  Sync Replies")
        if errors and not count:
            self.statusLbl.setText(f"Sync error: {errors[0][:70]}")
        else:
            self.statusLbl.setText(
                f"{count} new {'reply' if count==1 else 'replies'}" if count else "No new TRK replies"
            )
        if count:
            self.refresh()

    # ── Send reply draft ──────────────────────────────────────────────────────

    def _send_draft(self, row_id: int, to_email: str, subject: str, draft: str):
        if not to_email or "@" not in to_email:
            QMessageBox.warning(self, "No Recipient",
                                "Could not determine recipient email from the original sender address.")
            return

        confirm = QMessageBox.question(
            self, "Send Reply",
            f"Send this reply via Apple Mail?\n\nTo: {to_email}\nSubject: {subject[:60]}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            from modules.apple_mail_sender import send_via_apple_mail
            send_via_apple_mail(
                to_emails=[to_email],
                subject=subject,
                body=draft,
                tracking_key="",  # reply — no new TKEY needed
            )
            # Mark as handled in DB
            conn = get_db()
            conn.execute("UPDATE inbox_index SET reply_status='sent' WHERE id=?", (row_id,))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Sent", f"Reply sent to {to_email}")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Send Failed", str(e))
