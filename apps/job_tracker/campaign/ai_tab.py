"""
AI Automation Tab — natural-language campaign sender.

The user types anything:
  "I found these recruitment agencies, send them an email about my
   Digital Supply Chain PM role. Here are their details:
   ARWA Hamburg — hamburg@arwa.de — nationwide staffing agency
   xyz@recruit.de — tech-focused recruiter in Berlin"

Groq parses the intent, extracts emails, drafts personalised messages.
User reviews / edits each draft, then hits Send All.
Resume is attached automatically.
"""
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QScrollArea, QLineEdit, QComboBox,
    QCheckBox, QMessageBox, QSizePolicy, QProgressBar,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from database import get_setting, get_db
from ui.workers import GroqDraftWorker


# ── helpers ────────────────────────────────────────────────────────────────────

def _sender_options() -> list[tuple[str, str, str]]:
    opts: list[tuple[str, str, str]] = []
    try:
        from modules.oauth_manager import list_google_accounts
        for a in list_google_accounts():
            em = a.get("email", "")
            if em:
                opts.append((em, "smtp", em))
    except Exception:
        pass
    try:
        from modules.oauth_manager import is_ms_connected, ms_email
        if is_ms_connected():
            em = ms_email()
            opts.append((f"{em}  (Outlook)", "outlook", em))
    except Exception:
        pass
    opts.append(("Apple Mail", "apple_mail", ""))
    return opts


# ── Draft card ─────────────────────────────────────────────────────────────────

class _DraftCard(QFrame):
    """One editable email draft."""

    def __init__(self, d: dict, index: int, parent=None):
        super().__init__(parent)
        self.index   = index
        self._email  = d.get("email", "")
        self._company = d.get("company", "")
        self.setObjectName("card")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()

        num = QLabel(f"#{index + 1}")
        num.setStyleSheet(
            "font-size:10px; font-weight:700; color:#A5B4FC; "
            "background:rgba(99,102,241,0.15); padding:2px 7px; border-radius:4px;"
        )
        hdr.addWidget(num)

        em_lbl = QLabel(self._email)
        em_lbl.setStyleSheet("font-size:13px; font-weight:600; background:transparent;")
        hdr.addWidget(em_lbl)

        if self._company:
            co_lbl = QLabel(f"— {self._company}")
            co_lbl.setStyleSheet("font-size:12px; color:rgba(255,255,255,0.45); background:transparent;")
            hdr.addWidget(co_lbl)

        hdr.addStretch()

        self.includeChk = QCheckBox("Include")
        self.includeChk.setChecked(True)
        self.includeChk.setStyleSheet("font-size:11px;")
        hdr.addWidget(self.includeChk)
        lay.addLayout(hdr)

        # ── Subject ───────────────────────────────────────────────────────────
        subj_lbl = QLabel("Subject:")
        subj_lbl.setStyleSheet("font-size:10px; font-weight:700; letter-spacing:1px; "
                               "color:rgba(255,255,255,0.35); background:transparent;")
        lay.addWidget(subj_lbl)

        self.subjEdit = QLineEdit(d.get("subject", ""))
        self.subjEdit.setFixedHeight(34)
        lay.addWidget(self.subjEdit)

        # ── Body ──────────────────────────────────────────────────────────────
        body_lbl = QLabel("Body:")
        body_lbl.setStyleSheet("font-size:10px; font-weight:700; letter-spacing:1px; "
                               "color:rgba(255,255,255,0.35); background:transparent;")
        lay.addWidget(body_lbl)

        self.bodyEdit = QTextEdit()
        self.bodyEdit.setPlainText(d.get("body", ""))
        self.bodyEdit.setFont(QFont("Menlo, Courier New, monospace", 11))
        self.bodyEdit.setMinimumHeight(180)
        self.bodyEdit.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); "
            "border-radius:6px; padding:8px; color:rgba(255,255,255,0.85);}"
        )
        lay.addWidget(self.bodyEdit)

    def get_data(self) -> dict | None:
        if not self.includeChk.isChecked():
            return None
        return {
            "email":   self._email,
            "company": self._company,
            "subject": self.subjEdit.text().strip(),
            "body":    self.bodyEdit.toPlainText().strip(),
        }


# ── Main tab ───────────────────────────────────────────────────────────────────

class AIAutomationTab(QWidget):
    """
    Natural-language AI campaign automation.
    Groq parses intent + emails → drafts → user reviews → send.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._draft_worker   = None
        self._send_worker    = None
        self._cards: list[_DraftCard] = []
        self._total_contacts = 0
        self._sender_opts: list[tuple[str, str, str]] = []
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top area (input) ──────────────────────────────────────────────────
        top = QWidget()
        top.setStyleSheet("background:transparent;")
        top.setMaximumHeight(340)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(20, 16, 20, 12)
        tl.setSpacing(10)

        inst_lbl = QLabel("Tell the AI what to send:")
        inst_lbl.setStyleSheet(
            "font-size:12px; font-weight:600; color:rgba(255,255,255,0.7); background:transparent;"
        )
        tl.addWidget(inst_lbl)

        self.inputArea = QTextEdit()
        self.inputArea.setPlaceholderText(
            "Describe what you want to send and paste the email addresses with company details.\n\n"
            "Example:\n"
            "I'm looking for Digital Supply Chain PM roles. Please send professional outreach emails "
            "to these recruitment agencies:\n\n"
            "ARWA Personaldienstleistungen Hamburg — hamburg@arwa.de\n"
            "Nationwide staffing agency, specialises in supply chain & logistics talent.\n\n"
            "Heidrick & Struggles — hamburg@heidrick.com\n"
            "Executive search firm, strong presence in operations and supply chain roles."
        )
        self.inputArea.setFont(QFont("SF Pro Display, Helvetica Neue, Arial", 12))
        self.inputArea.setStyleSheet(
            "QTextEdit{"
            "background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.10); "
            "border-radius:10px; padding:12px; color:rgba(255,255,255,0.85);"
            "}"
            "QTextEdit:focus{border:1px solid rgba(99,102,241,0.6);}"
        )
        tl.addWidget(self.inputArea, 1)

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout(); ctrl.setSpacing(10)

        sender_lbl = QLabel("Send from:")
        sender_lbl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.5); background:transparent;")
        ctrl.addWidget(sender_lbl)

        self.senderCombo = QComboBox()
        self.senderCombo.setFixedHeight(32)
        self.senderCombo.setMinimumWidth(200)
        ctrl.addWidget(self.senderCombo)

        self.resumeChk = QCheckBox("Attach resume")
        self.resumeChk.setChecked(True)
        self.resumeChk.setStyleSheet("font-size:11px;")
        ctrl.addWidget(self.resumeChk)

        self.dryChk = QCheckBox("Dry run")
        self.dryChk.setStyleSheet("font-size:11px;")
        ctrl.addWidget(self.dryChk)

        ctrl.addStretch()

        self.aiStatusLbl = QLabel("")
        self.aiStatusLbl.setStyleSheet("font-size:11px; color:#A78BFA; background:transparent;")
        ctrl.addWidget(self.aiStatusLbl)

        tl.addLayout(ctrl)

        gen_row = QHBoxLayout(); gen_row.setSpacing(8)

        self.generateBtn = QPushButton("✦  Generate Drafts")
        self.generateBtn.setObjectName("accentBtn")
        self.generateBtn.setFixedHeight(38)
        self.generateBtn.setStyleSheet(
            "QPushButton{background:rgba(99,102,241,0.85); border-radius:8px; "
            "font-size:13px; font-weight:600; color:#fff; border:none;}"
            "QPushButton:hover{background:#6366F1;}"
            "QPushButton:disabled{background:rgba(99,102,241,0.3);}"
        )
        self.generateBtn.clicked.connect(self._generate)
        gen_row.addWidget(self.generateBtn, 1)

        self.stopBtn = QPushButton("■  Stop")
        self.stopBtn.setFixedHeight(38)
        self.stopBtn.setFixedWidth(80)
        self.stopBtn.setVisible(False)
        self.stopBtn.setStyleSheet(
            "QPushButton{background:rgba(255,80,80,0.18); border:1px solid rgba(255,80,80,0.4); "
            "border-radius:8px; font-size:12px; color:#FF99A4;}"
            "QPushButton:hover{background:rgba(255,80,80,0.30);}"
        )
        self.stopBtn.clicked.connect(self._stop_generation)
        gen_row.addWidget(self.stopBtn)

        tl.addLayout(gen_row)

        root.addWidget(top)

        # Divider
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color:rgba(255,255,255,0.07); margin:0;")
        root.addWidget(div)

        # ── Draft cards area ──────────────────────────────────────────────────
        draft_container = QWidget()
        dl = QVBoxLayout(draft_container)
        dl.setContentsMargins(20, 12, 20, 12)
        dl.setSpacing(10)

        draft_hdr = QHBoxLayout()
        self.draftCountLbl = QLabel("")
        self.draftCountLbl.setStyleSheet(
            "font-size:11px; font-weight:700; letter-spacing:1px; "
            "color:rgba(255,255,255,0.35); background:transparent;"
        )
        draft_hdr.addWidget(self.draftCountLbl)
        draft_hdr.addStretch()

        self.sendAllBtn = QPushButton("✉  Send All")
        self.sendAllBtn.setObjectName("accentBtn")
        self.sendAllBtn.setFixedHeight(34)
        self.sendAllBtn.setVisible(False)
        self.sendAllBtn.clicked.connect(self._send_all)
        draft_hdr.addWidget(self.sendAllBtn)
        dl.addLayout(draft_hdr)

        self.progressBar = QProgressBar()
        self.progressBar.setVisible(False)
        self.progressBar.setFixedHeight(4)
        self.progressBar.setTextVisible(False)
        dl.addWidget(self.progressBar)

        self.resultLbl = QLabel("")
        self.resultLbl.setWordWrap(True)
        self.resultLbl.setStyleSheet(
            "font-size:11px; color:rgba(255,255,255,0.5); background:transparent;"
        )
        dl.addWidget(self.resultLbl)

        # Scrollable cards
        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background:transparent;")
        self._cards_lay = QVBoxLayout(self._cards_widget)
        self._cards_lay.setContentsMargins(0, 0, 0, 0)
        self._cards_lay.setSpacing(10)

        placeholder = QLabel(
            "Drafts will appear here after generation.\n\n"
            "Each draft is fully editable before sending."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(
            "color:rgba(255,255,255,0.2); font-size:13px; "
            "background:rgba(255,255,255,0.02); border-radius:10px; padding:40px;"
        )
        self._cards_lay.addWidget(placeholder)
        self._placeholder = placeholder

        scroll = QScrollArea()
        scroll.setWidget(self._cards_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        dl.addWidget(scroll, 1)

        root.addWidget(draft_container, 1)

        # Seed combo
        self.refresh()

    # ── Sender combo ──────────────────────────────────────────────────────────

    def refresh(self):
        self._sender_opts = _sender_options()
        prev = self.senderCombo.currentText()
        self.senderCombo.blockSignals(True)
        self.senderCombo.clear()
        for lbl, _, _ in self._sender_opts:
            self.senderCombo.addItem(lbl)
        idx = self.senderCombo.findText(prev)
        if idx >= 0:
            self.senderCombo.setCurrentIndex(idx)
        self.senderCombo.blockSignals(False)

        # AI status
        try:
            from modules.groq_client import is_configured
            if is_configured():
                self.aiStatusLbl.setText("✦ Groq ready")
                return
        except Exception:
            pass
        self.aiStatusLbl.setText("⚠ Set Groq API key in Settings → AI")
        self.aiStatusLbl.setStyleSheet("font-size:11px; color:#FCE100; background:transparent;")

    def _get_mode(self) -> tuple[str, str]:
        idx = self.senderCombo.currentIndex()
        if self._sender_opts and 0 <= idx < len(self._sender_opts):
            _, mode, acct = self._sender_opts[idx]
            return mode, acct
        return "smtp", ""

    # ── Generate ──────────────────────────────────────────────────────────────

    def _generate(self):
        if self._draft_worker:
            return
        msg = self.inputArea.toPlainText().strip()
        if not msg:
            QMessageBox.information(self, "Nothing to parse",
                "Type your message and paste the email addresses, then try again.")
            return

        try:
            from modules.groq_client import is_configured
            if not is_configured():
                QMessageBox.warning(self, "Groq Not Configured",
                    "Go to Settings → AI and add your Groq API key.\n"
                    "Get a free key at console.groq.com.")
                return
        except Exception:
            pass

        self.generateBtn.setEnabled(False)
        self.generateBtn.setText("Scanning…")
        self.stopBtn.setVisible(True)
        self.resultLbl.setText("⟳  Extracting email addresses…")
        self._clear_cards()
        self.sendAllBtn.setVisible(False)
        self._total_contacts = 0

        self._draft_worker = GroqDraftWorker(msg)
        self._draft_worker.contacts_found.connect(self._on_contacts_found)
        self._draft_worker.draft_ready.connect(self._on_single_draft_ready)
        self._draft_worker.done.connect(self._on_all_drafts_done)
        self._draft_worker.error.connect(self._on_draft_error)
        self._draft_worker.finished.connect(lambda: setattr(self, "_draft_worker", None))
        self._draft_worker.start()

    def _stop_generation(self):
        if self._draft_worker:
            self._draft_worker.cancel()
        self.stopBtn.setVisible(False)
        self.resultLbl.setText("Stopped.")

    def _on_contacts_found(self, total: int):
        self._total_contacts = total
        self.generateBtn.setText(f"Drafting 0 / {total}…")
        self.resultLbl.setText(
            f"Found {total} contact{'s' if total != 1 else ''}. "
            f"Drafting one email at a time…"
        )
        self.progressBar.setVisible(True)
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(0)

    def _on_single_draft_ready(self, index: int, total: int, draft: dict):
        card = _DraftCard(draft, index)
        self._cards.append(card)
        self._cards_lay.addWidget(card)
        self.progressBar.setValue(index + 1)
        self.generateBtn.setText(f"Drafting {index + 1} / {total}…")
        n = len(self._cards)
        self.draftCountLbl.setText(f"DRAFTS  —  {n} of {total}")
        self.sendAllBtn.setText(f"✉  Send All  ({n})")
        self.sendAllBtn.setVisible(True)

    def _on_all_drafts_done(self, drafted: int):
        self.generateBtn.setEnabled(True)
        self.generateBtn.setText("✦  Generate Drafts")
        self.stopBtn.setVisible(False)
        self.progressBar.setVisible(False)
        n = drafted
        self.draftCountLbl.setText(f"DRAFTS  —  {n} email{'s' if n != 1 else ''} ready")
        self.resultLbl.setText(
            f"✓ All {n} draft{'s' if n!=1 else ''} generated. "
            "Review and edit before sending."
        )

    def _on_draft_error(self, msg: str):
        self.generateBtn.setEnabled(True)
        self.generateBtn.setText("✦  Generate Drafts")
        self.stopBtn.setVisible(False)
        self.progressBar.setVisible(False)
        self.resultLbl.setText(f"Error: {msg[:160]}")
        QMessageBox.critical(self, "Generation Failed", msg)

    def _clear_cards(self):
        self._cards = []
        while self._cards_lay.count():
            item = self._cards_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._placeholder.setParent(None)

    # ── Send all ──────────────────────────────────────────────────────────────

    def _send_all(self):
        if self._send_worker:
            return

        selected = [c.get_data() for c in self._cards if c.get_data()]
        if not selected:
            QMessageBox.information(self, "Nothing selected",
                "All drafts are unchecked. Check at least one.")
            return

        mode, g_acct = self._get_mode()
        dry = self.dryChk.isChecked()
        attach = self.resumeChk.isChecked()
        via = self.senderCombo.currentText()

        confirm = QMessageBox.question(
            self, "Send Emails",
            f"{'[DRY RUN]  ' if dry else ''}"
            f"Send {len(selected)} email(s) via {via}?\n"
            f"Resume: {'attached' if attach else 'not attached'}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.sendAllBtn.setEnabled(False)
        self.generateBtn.setEnabled(False)
        self.progressBar.setVisible(True)
        self.progressBar.setMaximum(len(selected))
        self.progressBar.setValue(0)
        self._sent_count = 0

        self._send_worker = _AIBatchSendWorker(
            drafts=selected,
            sender_mode=mode,
            google_account_email=g_acct,
            attach_resume=attach,
            dry_run=dry,
        )
        self._send_worker.progress.connect(self._on_send_progress)
        self._send_worker.done.connect(self._on_send_done)
        self._send_worker.finished.connect(lambda: setattr(self, "_send_worker", None))
        self._send_worker.start()

    def _on_send_progress(self, email: str, ok: bool):
        self._sent_count += 1
        self.progressBar.setValue(self._sent_count)
        icon = "✓" if ok else "✗"
        self.resultLbl.setText(f"{icon}  {email}")

    def _on_send_done(self, sent: int, failed: int, errors: list):
        self.sendAllBtn.setEnabled(True)
        self.generateBtn.setEnabled(True)
        self.progressBar.setVisible(False)
        self.resultLbl.setText(
            f"✓ {sent} sent   ✗ {failed} failed"
        )
        if errors:
            QMessageBox.warning(self, "Some Sends Failed", "\n".join(errors[:5]))


# ── Batch send worker ─────────────────────────────────────────────────────────

from PyQt6.QtCore import QThread, pyqtSignal as _sig


class _AIBatchSendWorker(QThread):
    progress = _sig(str, bool)     # email, success
    done     = _sig(int, int, list) # sent, failed, errors

    def __init__(self, drafts, sender_mode, google_account_email,
                 attach_resume, dry_run):
        super().__init__()
        self.drafts               = drafts
        self.sender_mode          = sender_mode
        self.google_account_email = google_account_email
        self.attach_resume        = attach_resume
        self.dry_run              = dry_run

    def run(self):
        import os, uuid as _uuid
        from database import get_setting, get_db, subject_to_tracking_key
        from modules.apple_mail_sender import _profile, transform_to_careers, send_via_apple_mail

        p = _profile()
        resume = None
        if self.attach_resume:
            rp = p.get("resume") or get_setting("resume_path", "")
            if rp and os.path.isfile(rp):
                resume = rp

        sent = failed = 0
        errors = []
        conn = get_db()

        for d in self.drafts:
            email   = (d.get("email") or "").strip().lower()
            company = d.get("company", "")
            subject = d.get("subject", "").strip()
            body    = d.get("body", "").strip()

            # Never send a draft that failed to generate
            if not email or "@" not in email:
                continue
            if not subject or not body:
                errors.append(f"{email}: empty draft — skipped")
                self.progress.emit(email, False)
                continue
            if body.startswith("[Draft error:") or body.startswith("[Error"):
                errors.append(f"{email}: draft had an error — skipped")
                self.progress.emit(email, False)
                continue

            tkey = subject_to_tracking_key(subject)

            try:
                if self.dry_run:
                    print(f"[AI DRY RUN] To: {email} | {subject}")
                elif self.sender_mode == "smtp" and self.google_account_email:
                    from modules.mail_client import send_email
                    send_email([email], subject, body,
                               attachment_path=resume, tracking_key=tkey,
                               from_account_email=self.google_account_email)
                elif self.sender_mode == "outlook":
                    from modules.outlook_sender import send_via_outlook
                    send_via_outlook([email], subject, body, resume, tkey)
                else:
                    send_via_apple_mail([email], subject, body, resume, tkey)

                # Save to applications
                now = __import__("datetime").datetime.utcnow().isoformat()
                existing = conn.execute(
                    "SELECT id FROM applications WHERE contact_email=?", (email,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE applications SET status='sent', sent_at=?, "
                        "email_subject=?, email_body=?, tkey=? WHERE id=?",
                        (now, subject, body, tkey, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO applications "
                        "(uuid, company, contact_email, status, sent_at, email_subject, email_body, tkey) "
                        "VALUES (?,?,?,'sent',?,?,?,?)",
                        (str(_uuid.uuid4()), company, email, now, subject, body, tkey),
                    )
                conn.commit()
                sent += 1
                self.progress.emit(email, True)

            except Exception as exc:
                failed += 1
                errors.append(f"{email}: {str(exc)[:100]}")
                self.progress.emit(email, False)

        conn.close()
        self.done.emit(sent, failed, errors)
