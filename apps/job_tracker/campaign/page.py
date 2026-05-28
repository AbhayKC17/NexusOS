from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QSpinBox, QFrame, QProgressBar, QTextEdit, QMessageBox,
    QSplitter, QComboBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from database import get_db, get_setting
from ui.style import STATUS_STYLE
from ui.workers import BulkSendWorker
import modules.llm_summarizer as ls


def _build_sender_options() -> list[tuple[str, str]]:
    """Build sender list dynamically from currently connected accounts."""
    options = []

    # Google OAuth — if connected, show the actual email address
    try:
        from modules.oauth_manager import is_google_connected, google_email
        if is_google_connected():
            em = google_email()
            options.append((f"Gmail  ({em})", "smtp"))
    except Exception:
        pass

    # Microsoft OAuth token
    try:
        from modules.oauth_manager import is_ms_connected, ms_email
        if is_ms_connected():
            em = ms_email()
            options.append((f"Outlook OAuth  ({em})", "smtp"))
    except Exception:
        pass

    # SMTP configured with a host (App Password / manual)
    smtp_host = get_setting("smtp_host", "")
    smtp_user = get_setting("smtp_user", "")
    if smtp_host and smtp_user:
        label = f"Outlook SMTP  ({smtp_user})" if "office365" in smtp_host or "outlook" in smtp_host else f"SMTP  ({smtp_user})"
        # Only add if not already covered by OAuth above
        if not any(smtp_user in lbl for lbl, _ in options):
            options.append((label, "smtp"))

    # Apple Mail — always available on macOS
    options.append(("Apple Mail", "apple_mail"))

    # Fallback: generic SMTP entry if nothing else
    if not options or all(m != "smtp" for _, m in options):
        options.append(("Built-in Mail  (SMTP)", "smtp"))

    return options


class CampaignPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._sender_options: list[tuple[str, str]] = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        # Title
        t = QLabel("Campaign Sender")
        t.setObjectName("pageTitle")
        root.addWidget(t)
        sub = QLabel("Select applications → preview AI intro → send via Apple Mail with your resume attached")
        sub.setObjectName("pageSubtitle")
        root.addWidget(sub)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # ── LEFT panel ───────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 12, 0); ll.setSpacing(12)

        # Options card
        opt = QFrame(); opt.setObjectName("card")
        ol = QVBoxLayout(opt); ol.setContentsMargins(16, 14, 16, 16); ol.setSpacing(12)

        hdr = QLabel("SEND OPTIONS"); hdr.setObjectName("sectionTitle")
        ol.addWidget(hdr)

        # Sender selection
        sender_row = QHBoxLayout()
        sender_row.addWidget(QLabel("Send via:"))
        self.senderCombo = QComboBox()
        self.senderCombo.currentIndexChanged.connect(self._on_sender_changed)
        sender_row.addWidget(self.senderCombo, 1)
        ol.addLayout(sender_row)

        # Sender hint label
        self.senderHint = QLabel("")
        self.senderHint.setStyleSheet(
            "color: rgba(255,255,255,0.4); font-size: 11px; background: transparent;"
        )
        self.senderHint.setWordWrap(True)
        ol.addWidget(self.senderHint)

        # Apple Mail account selector — only visible when Apple Mail mode is active
        self.appleAccountRow = QWidget()
        self.appleAccountRow.setStyleSheet("background: transparent;")
        aar = QHBoxLayout(self.appleAccountRow)
        aar.setContentsMargins(0, 0, 0, 0)
        aar.setSpacing(8)
        aar.addWidget(QLabel("From account:"))
        self.appleAccountCombo = QComboBox()
        self.appleAccountCombo.addItem("Default (system)", "")
        aar.addWidget(self.appleAccountCombo, 1)
        self.appleAccountRow.setVisible(False)
        ol.addWidget(self.appleAccountRow)

        # Resume path display
        resume_row = QHBoxLayout()
        self.resumeLabel = QLabel("Resume: not set")
        self.resumeLabel.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px; background: transparent;")
        self.resumeLabel.setWordWrap(True)
        resume_row.addWidget(self.resumeLabel)
        ol.addLayout(resume_row)

        sleep_row = QHBoxLayout()
        sleep_row.addWidget(QLabel("Delay between emails (s):"))
        self.sleepSpin = QSpinBox(); self.sleepSpin.setRange(0,120); self.sleepSpin.setValue(10)
        sleep_row.addWidget(self.sleepSpin); sleep_row.addStretch()
        ol.addLayout(sleep_row)

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Send only first N (0 = all):"))
        self.limitSpin = QSpinBox()
        self.limitSpin.setRange(0, 999)
        self.limitSpin.setValue(0)
        self.limitSpin.setSpecialValueText("all")
        self.limitSpin.setToolTip("0 = send all selected. Set to N to send only the first N applications from your selection.")
        limit_row.addWidget(self.limitSpin)
        limit_row.addStretch()
        ol.addLayout(limit_row)

        self.careersChk = QCheckBox("Also send to careers@domain")
        self.careersChk.setChecked(True)
        ol.addWidget(self.careersChk)

        self.dryRunChk = QCheckBox("Dry run — preview only, don't send")
        ol.addWidget(self.dryRunChk)

        self.llmStatusLbl = QLabel("LLM: checking…")
        self.llmStatusLbl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px; background: transparent;")
        ol.addWidget(self.llmStatusLbl)
        ll.addWidget(opt)

        # Action buttons
        self.previewBtn = QPushButton("Preview First Selected")
        self.previewBtn.clicked.connect(self._preview)
        ll.addWidget(self.previewBtn)

        self.sendBtn = QPushButton("✉  Send Emails")
        self.sendBtn.setObjectName("accentBtn")
        self.sendBtn.clicked.connect(self._send)
        ll.addWidget(self.sendBtn)

        # Combo is populated in refresh(); call once now with empty list so button gets a label
        self._refresh_sender_combo()
        self._on_sender_changed(0)

        self.progressBar = QProgressBar()
        self.progressBar.setVisible(False)
        ll.addWidget(self.progressBar)

        self.statusLbl = QLabel("")
        self.statusLbl.setWordWrap(True)
        self.statusLbl.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px; background: transparent;")
        ll.addWidget(self.statusLbl)

        # Preview box
        prev_card = QFrame(); prev_card.setObjectName("card")
        pl = QVBoxLayout(prev_card); pl.setContentsMargins(0,0,0,0); pl.setSpacing(0)

        ph = QWidget()
        ph.setStyleSheet("background:transparent; border-bottom: 1px solid rgba(255,255,255,0.06);")
        phl = QHBoxLayout(ph); phl.setContentsMargins(14,11,14,11)
        phl.addWidget(QLabel("EMAIL PREVIEW"))
        pl.addWidget(ph)

        self.previewText = QTextEdit()
        self.previewText.setReadOnly(True)
        self.previewText.setPlaceholderText("Select an app and click Preview to see the LLM-generated email…")
        self.previewText.setStyleSheet(
            "border:none; background: transparent; padding: 12px; "
            "font-family: 'Courier New', monospace; font-size: 12px; color: rgba(255,255,255,0.8);"
        )
        pl.addWidget(self.previewText)
        ll.addWidget(prev_card, 1)
        splitter.addWidget(left)

        # ── RIGHT panel — application table ──────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(8)

        tbl_top = QHBoxLayout()
        tbl_top.addWidget(QLabel("Select Applications"))
        tbl_top.addStretch()
        for lbl, fn in [("Select All", lambda: self._sel_all(True)), ("Clear", lambda: self._sel_all(False))]:
            b = QPushButton(lbl); b.setObjectName("subtleBtn"); b.setFixedHeight(28)
            b.clicked.connect(fn); tbl_top.addWidget(b)
        rl.addLayout(tbl_top)

        tbl_card = QFrame(); tbl_card.setObjectName("card")
        tbl_lay = QVBoxLayout(tbl_card); tbl_lay.setContentsMargins(0,0,0,0)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["","Company","Position","Email","Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        for col in [1,2,3]:
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        tbl_lay.addWidget(self.table)
        rl.addWidget(tbl_card, 1)
        splitter.addWidget(right)
        splitter.setSizes([360, 640])

    def _populate_apple_accounts(self):
        """Fetch Apple Mail accounts via AppleScript and fill the account combo."""
        from modules.apple_mail_sender import get_apple_mail_accounts
        accounts = get_apple_mail_accounts()
        self.appleAccountCombo.blockSignals(True)
        prev = self.appleAccountCombo.currentData() or ""
        self.appleAccountCombo.clear()
        self.appleAccountCombo.addItem("Default (system)", "")
        for label, email in accounts:
            self.appleAccountCombo.addItem(label, email)
        # Restore previous selection
        for i in range(self.appleAccountCombo.count()):
            if self.appleAccountCombo.itemData(i) == prev:
                self.appleAccountCombo.setCurrentIndex(i)
                break
        self.appleAccountCombo.blockSignals(False)

    def _refresh_sender_combo(self):
        """Rebuild sender dropdown from currently connected accounts."""
        prev_mode = self._sender_mode()
        self._sender_options = _build_sender_options()
        self.senderCombo.blockSignals(True)
        self.senderCombo.clear()
        for label, _ in self._sender_options:
            self.senderCombo.addItem(label)
        # Restore previous selection if still present
        for i, (_, mode) in enumerate(self._sender_options):
            if mode == prev_mode:
                self.senderCombo.setCurrentIndex(i)
                break
        self.senderCombo.blockSignals(False)
        self._on_sender_changed(self.senderCombo.currentIndex())

    def refresh(self):
        self._refresh_sender_combo()

        # Update LLM status
        if ls._get_llm() is not None:
            self.llmStatusLbl.setText("● LLM: Mistral 7B ready — personalised intros active")
            self.llmStatusLbl.setStyleSheet("color: #6CCB5F; font-size: 12px; background: transparent;")
        else:
            self.llmStatusLbl.setText("● LLM: not loaded — will use canned intro")
            self.llmStatusLbl.setStyleSheet("color: #FCE100; font-size: 12px; background: transparent;")

        # Update resume status
        resume = get_setting("resume_path", "")
        if resume:
            import os
            fname = os.path.basename(resume)
            exists = os.path.isfile(resume)
            self.resumeLabel.setText(f"Resume: {fname} {'✓' if exists else '✗ FILE NOT FOUND'}")
            self.resumeLabel.setStyleSheet(
                f"color: {'#6CCB5F' if exists else '#FF99A4'}; font-size: 12px; background: transparent;"
            )
        else:
            self.resumeLabel.setText("Resume: not set — go to Settings")
            self.resumeLabel.setStyleSheet("color: #FF99A4; font-size: 12px; background: transparent;")

        # Load applications
        conn = get_db()
        apps = conn.execute(
            "SELECT id,company,position,contact_email,status FROM applications "
            "WHERE status IN ('pending','sent') ORDER BY created_at DESC"
        ).fetchall()
        conn.close()

        self.table.setRowCount(len(apps))
        for i, (aid, co, pos, em, st) in enumerate(apps):
            self.table.setRowHeight(i, 44)

            # Checkbox item — stores app_id in UserRole
            check_item = QTableWidgetItem()
            check_item.setCheckState(Qt.CheckState.Unchecked)
            check_item.setData(Qt.ItemDataRole.UserRole, aid)
            check_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable |
                Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable
            )
            self.table.setItem(i, 0, check_item)

            domain = em.split("@")[1] if em and "@" in em else "?"
            email_display = f"{em or '—'}  →  careers@{domain}"
            for j, v in enumerate([co or "—", pos or "—", email_display, st or "pending"]):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if j == 3:
                    fg, _ = STATUS_STYLE.get(v, ("#FFFFFF", ""))
                    item.setForeground(QColor(fg))
                self.table.setItem(i, j + 1, item)

    def _sel_all(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item: item.setCheckState(state)

    def _selected_ids(self):
        ids = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _preview(self):
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "Preview", "Select at least one application first.")
            return
        conn = get_db()
        app = conn.execute("SELECT * FROM applications WHERE id=?", (ids[0],)).fetchone()
        conn.close()

        from modules.apple_mail_sender import generate_personalized_intro, build_email_body, transform_to_careers
        import os
        company  = app["company"] or ""
        position = (app["position"] or "").strip()
        intro    = generate_personalized_intro(company, app["notes"] or "")
        body     = build_email_body(company, intro, position)
        domain   = (app["contact_email"] or "").split("@")[-1]
        resume      = get_setting("resume_path", "")
        sender_name = get_setting("sender_name", "")
        if position:
            subject = f"Exploring {position} opportunities at {company or 'your company'}"
        else:
            subject = f"Joining {company or 'your company'}'s journey — {sender_name}"

        preview = (
            f"To: {app['contact_email']}"
            + (f"\n    careers@{domain}" if self.careersChk.isChecked() and domain else "")
            + f"\nSubject: {subject}"
            + f"\nResume: {'✓ ' + os.path.basename(resume) if resume and os.path.isfile(resume) else '✗ not attached'}"
            + "\n" + "─" * 52 + "\n"
            + body
        )
        self.previewText.setPlainText(preview)

    def _sender_mode(self) -> str:
        idx = self.senderCombo.currentIndex()
        if self._sender_options and 0 <= idx < len(self._sender_options):
            return self._sender_options[idx][1]
        return "smtp"

    def _on_sender_changed(self, idx):
        if not self._sender_options:
            return
        label, mode = self._sender_options[idx] if 0 <= idx < len(self._sender_options) else ("", "smtp")
        hints = {
            "smtp":       "Sends directly via your connected account (Gmail OAuth or Outlook SMTP). No extra apps needed.",
            "apple_mail": "Apple Mail must be open. Sends via AppleScript with TKEY tracking.",
            "outlook":    "Uses Microsoft Graph API. Connect in Settings → Microsoft Graph.",
        }
        self.senderHint.setText(hints.get(mode, ""))
        short = label.split("(")[0].strip()
        self.sendBtn.setText(f"✉  Send via {short}")

        is_apple = (mode == "apple_mail")
        if hasattr(self, "appleAccountRow"):
            self.appleAccountRow.setVisible(is_apple)
            if is_apple and self.appleAccountCombo.count() <= 1:
                self._populate_apple_accounts()

    def _send(self):
        if self._worker is not None:
            return
        ids   = self._selected_ids()
        limit = self.limitSpin.value()

        # If nothing is manually selected but a limit is set, auto-pick the
        # first N unsent/pending applications so the user doesn't have to
        # tick rows individually.
        if not ids and limit > 0:
            conn = get_db()
            rows = conn.execute(
                "SELECT id FROM applications WHERE status='pending' "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            ids = [r[0] for r in rows]

        if not ids:
            QMessageBox.information(self, "Send", "No unsent applications found. "
                                    "Select applications manually or check that unsent rows exist.")
            return

        # Apply limit to manually-selected ids (auto-fetch already respects it)
        if limit > 0 and self._selected_ids():
            ids = ids[:limit]

        mode = self._sender_mode()
        dry  = self.dryRunChk.isChecked()
        idx  = self.senderCombo.currentIndex()
        mode_label = self._sender_options[idx][0].split("(")[0].strip() if self._sender_options else "Mail"

        apple_account = ""
        if mode == "apple_mail":
            apple_account = self.appleAccountCombo.currentData() or ""
            acct_hint = f"\nAccount: {apple_account}" if apple_account else ""
        else:
            acct_hint = ""

        if QMessageBox.question(
            self, "Confirm",
            f"{'[DRY RUN] ' if dry else ''}Send {len(ids)} email(s) via {mode_label}?{acct_hint}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        self.sendBtn.setEnabled(False)
        self.sendBtn.setText("Sending…")
        self.progressBar.setVisible(True)
        self.progressBar.setMaximum(len(ids))
        self.progressBar.setValue(0)
        self._sent = 0

        self._worker = BulkSendWorker(
            app_ids=ids,
            sleep_seconds=self.sleepSpin.value(),
            dry_run=dry,
            send_to_careers=self.careersChk.isChecked(),
            sender_mode=mode,
            apple_mail_account=apple_account,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
        self._worker.start()

    def _on_progress(self, app_id, company, status):
        self._sent += 1
        self.progressBar.setValue(self._sent)
        icon = "✓" if "sent" in status else "✗"
        self.statusLbl.setText(f"{icon}  {company} — {status}")

    def _on_done(self, result):
        self.sendBtn.setEnabled(True)
        self._on_sender_changed(self.senderCombo.currentIndex())
        self.progressBar.setVisible(False)
        self.statusLbl.setText(
            f"Done — Sent: {result['sent']} | Failed: {result['failed']} | Skipped: {result['skipped']}"
        )
        if result["errors"]:
            QMessageBox.warning(self, "Errors", "\n".join(result["errors"][:5]))
        self.refresh()
