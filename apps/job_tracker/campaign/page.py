"""
Campaign Sender — clean two-column layout.

Left  : Send controls (fixed 260 px)
Right : QSplitter vertical
          Top  — Applications table (stretch 3)
          Bottom — AI email preview (stretch 2)
"""
import json
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QSpinBox, QFrame, QProgressBar, QTextEdit, QMessageBox,
    QSplitter, QComboBox, QFormLayout, QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from database import get_db, get_setting
from ui.style import STATUS_STYLE
from ui.workers import BulkSendWorker
import modules.llm_summarizer as ls


# ── helpers ────────────────────────────────────────────────────────────────────

def _sender_options() -> list[tuple[str, str, str]]:
    """(label, mode, account_email)"""
    opts: list[tuple[str, str, str]] = []
    try:
        from modules.oauth_manager import list_google_accounts
        for a in list_google_accounts():
            em = a.get("email", "")
            if em:
                opts.append((em, "smtp", em))
    except Exception:
        try:
            from modules.oauth_manager import is_google_connected, google_email
            if is_google_connected():
                em = google_email()
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


def _parse_raw(raw_json) -> dict:
    if not raw_json:
        return {}
    try:
        return json.loads(raw_json)
    except Exception:
        return {}


def _context_lines(raw: dict) -> list[str]:
    lines = []
    if raw.get("short_description"):
        lines.append(f"About:     {raw['short_description'][:110]}")
    if raw.get("categories"):
        lines.append(f"Sector:    {raw['categories'].split(',')[0].strip()[:60]}")
    loc = ", ".join(filter(None, [raw.get("city",""), raw.get("country","")]))
    if loc:
        lines.append(f"Location:  {loc}")
    if raw.get("total_funding_usd"):
        try:
            f = float(str(raw["total_funding_usd"]).replace(",",""))
            s = f"${f/1e9:.1f}B" if f>=1e9 else f"${f/1e6:.0f}M" if f>=1e6 else f"${f/1e3:.0f}K"
            lines.append(f"Funding:   {s}")
        except Exception:
            pass
    if raw.get("investors"):
        lines.append(f"Investors: {str(raw['investors'])[:80]}")
    if raw.get("num_employees"):
        lines.append(f"Team:      {raw['num_employees']} employees")
    return lines


# ── page ───────────────────────────────────────────────────────────────────────

class CampaignPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._opts: list[tuple[str, str, str]] = []
        self._build()

    # ─────────────────────────────────────────────────────────── build ──────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setObjectName("pageHeader")
        bar.setFixedHeight(52)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 8, 16, 8)
        bl.setSpacing(10)

        title = QLabel("Campaign Sender")
        title.setStyleSheet("font-size:16px; font-weight:700; background:transparent;")
        bl.addWidget(title)
        bl.addSpacing(12)

        self.aiBadge = QLabel("")
        self.aiBadge.setStyleSheet(
            "font-size:11px; padding:2px 10px; border-radius:5px; background:transparent;"
        )
        bl.addWidget(self.aiBadge)
        bl.addStretch()

        self.sendBtn = QPushButton("✉  Send Selected")
        self.sendBtn.setObjectName("accentBtn")
        self.sendBtn.setFixedHeight(34)
        self.sendBtn.setMinimumWidth(130)
        self.sendBtn.clicked.connect(self._send)
        bl.addWidget(self.sendBtn)

        root.addWidget(bar)

        # ── Body splitter (left controls | right content) ─────────────────────
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        body.setStyleSheet("QSplitter::handle{background:rgba(255,255,255,0.07);}")
        root.addWidget(body, 1)

        body.addWidget(self._left_panel())
        body.addWidget(self._right_panel())
        body.setSizes([260, 740])
        body.setCollapsible(0, False)
        body.setCollapsible(1, False)

        self._reload_sender_combo()
        self._on_sender_changed(0)

    # ─────────────────────────────────────────────── left controls panel ────────

    def _left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;}")

        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 12, 16)
        lay.setSpacing(14)

        # ── Sender ────────────────────────────────────────────────────────────
        lay.addWidget(self._section_label("SEND FROM"))

        self.senderCombo = QComboBox()
        self.senderCombo.setFixedHeight(34)
        self.senderCombo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.senderCombo.currentIndexChanged.connect(self._on_sender_changed)
        lay.addWidget(self.senderCombo)

        self.appleRow = QWidget(); self.appleRow.setStyleSheet("background:transparent;")
        ar = QHBoxLayout(self.appleRow); ar.setContentsMargins(0,0,0,0); ar.setSpacing(6)
        ar.addWidget(QLabel("Account:"))
        self.appleCombo = QComboBox()
        self.appleCombo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.appleCombo.addItem("Default", "")
        ar.addWidget(self.appleCombo, 1)
        self.appleRow.setVisible(False)
        lay.addWidget(self.appleRow)

        # ── Resume ────────────────────────────────────────────────────────────
        self.resumeLbl = QLabel("Resume: —")
        self.resumeLbl.setWordWrap(True)
        self.resumeLbl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.5); background:transparent;")
        lay.addWidget(self.resumeLbl)

        # ── Divider ───────────────────────────────────────────────────────────
        lay.addWidget(self._divider())

        # ── Options form ──────────────────────────────────────────────────────
        lay.addWidget(self._section_label("OPTIONS"))

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        self.delaySpin = QSpinBox()
        self.delaySpin.setRange(0, 300); self.delaySpin.setValue(10)
        self.delaySpin.setFixedWidth(68); self.delaySpin.setSuffix(" s")
        form.addRow("Delay:", self.delaySpin)

        self.batchSpin = QSpinBox()
        self.batchSpin.setRange(0, 999); self.batchSpin.setValue(0)
        self.batchSpin.setSpecialValueText("all"); self.batchSpin.setFixedWidth(68)
        form.addRow("Batch:", self.batchSpin)
        lay.addLayout(form)

        self.dryChk = QCheckBox("Dry run")
        self.dryChk.setStyleSheet("font-size:12px;")
        lay.addWidget(self.dryChk)

        # ── AI status ─────────────────────────────────────────────────────────
        lay.addWidget(self._divider())
        self.aiLbl = QLabel("AI: checking…")
        self.aiLbl.setWordWrap(True)
        self.aiLbl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.4); background:transparent;")
        lay.addWidget(self.aiLbl)

        # ── Preview button ────────────────────────────────────────────────────
        lay.addWidget(self._divider())
        self.previewBtn = QPushButton("✦  Preview Email")
        self.previewBtn.setFixedHeight(34)
        self.previewBtn.clicked.connect(self._preview)
        lay.addWidget(self.previewBtn)

        # ── Progress ──────────────────────────────────────────────────────────
        self.progressBar = QProgressBar()
        self.progressBar.setVisible(False)
        self.progressBar.setFixedHeight(4)
        self.progressBar.setTextVisible(False)
        lay.addWidget(self.progressBar)

        self.statusLbl = QLabel("")
        self.statusLbl.setWordWrap(True)
        self.statusLbl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.45); background:transparent;")
        lay.addWidget(self.statusLbl)

        lay.addStretch()
        scroll.setWidget(w)
        return scroll

    # ──────────────────────────────────────────────── right content panel ───────

    def _right_panel(self) -> QWidget:
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setHandleWidth(4)
        vsplit.setStyleSheet("QSplitter::handle{background:rgba(255,255,255,0.06);}")

        # ── Application table ─────────────────────────────────────────────────
        tbl_w = QWidget()
        tl = QVBoxLayout(tbl_w); tl.setContentsMargins(12, 12, 12, 6); tl.setSpacing(8)

        top_row = QHBoxLayout()
        self.appCountLbl = QLabel("Applications")
        self.appCountLbl.setStyleSheet("font-size:12px; font-weight:600; background:transparent;")
        top_row.addWidget(self.appCountLbl)
        top_row.addStretch()
        for text, fn in [("Select All", lambda: self._sel_all(True)), ("Clear", lambda: self._sel_all(False))]:
            b = QPushButton(text); b.setObjectName("subtleBtn"); b.setFixedHeight(26)
            b.clicked.connect(fn); top_row.addWidget(b)
        tl.addLayout(top_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Company", "Sector", "Location", "Status"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed);   self.table.setColumnWidth(0, 28)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed);   self.table.setColumnWidth(2, 130)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed);   self.table.setColumnWidth(3, 100)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed);   self.table.setColumnWidth(4, 76)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_context(row))
        tl.addWidget(self.table, 1)
        vsplit.addWidget(tbl_w)

        # ── Preview pane ──────────────────────────────────────────────────────
        prev_w = QWidget()
        pl = QVBoxLayout(prev_w); pl.setContentsMargins(12, 6, 12, 12); pl.setSpacing(6)

        prev_hdr = QHBoxLayout()
        prev_hdr.addWidget(self._section_label("AI EMAIL PREVIEW"))
        prev_hdr.addStretch()
        self.ctxLbl = QLabel("")
        self.ctxLbl.setStyleSheet(
            "font-size:10px; color:#A5B4FC; background:rgba(99,102,241,0.12); "
            "padding:2px 8px; border-radius:4px;"
        )
        prev_hdr.addWidget(self.ctxLbl)
        pl.addLayout(prev_hdr)

        self.previewEdit = QTextEdit()
        self.previewEdit.setReadOnly(True)
        self.previewEdit.setFont(QFont("Menlo, Courier New, monospace", 11))
        self.previewEdit.setPlaceholderText(
            "Click a startup row or press  ✦ Preview Email  to generate a personalised draft.\n\n"
            "The AI uses: description · sector · location · funding · investors."
        )
        self.previewEdit.setStyleSheet(
            "QTextEdit{border:none; background:rgba(255,255,255,0.03); "
            "border-radius:8px; padding:12px; color:rgba(255,255,255,0.82);}"
        )
        pl.addWidget(self.previewEdit, 1)
        vsplit.addWidget(prev_w)

        vsplit.setSizes([420, 280])
        return vsplit

    # ─────────────────────────────────────────────────── small helpers ───────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-size:10px; font-weight:700; letter-spacing:1px; "
            "color:rgba(255,255,255,0.35); background:transparent;"
        )
        return lbl

    @staticmethod
    def _divider() -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color:rgba(255,255,255,0.07);")
        return f

    # ──────────────────────────────────────────────── sender combo ───────────────

    def _reload_sender_combo(self):
        prev_mode, prev_acct = self._get_mode()
        self._opts = _sender_options()
        self.senderCombo.blockSignals(True)
        self.senderCombo.clear()
        for label, _, _ in self._opts:
            self.senderCombo.addItem(label)
        for i, (_, m, a) in enumerate(self._opts):
            if m == prev_mode and a == prev_acct:
                self.senderCombo.setCurrentIndex(i); break
        self.senderCombo.blockSignals(False)
        self._on_sender_changed(self.senderCombo.currentIndex())

    def _get_mode(self) -> tuple[str, str]:
        idx = self.senderCombo.currentIndex()
        if self._opts and 0 <= idx < len(self._opts):
            _, mode, acct = self._opts[idx]
            return mode, acct
        return "smtp", ""

    def _on_sender_changed(self, idx):
        if not self._opts:
            return
        label, mode, _ = self._opts[idx] if 0 <= idx < len(self._opts) else ("", "smtp", "")
        short = label.split("(")[0].strip() or "Mail"
        self.sendBtn.setText(f"✉  Send via {short}")
        is_apple = (mode == "apple_mail")
        if hasattr(self, "appleRow"):
            self.appleRow.setVisible(is_apple)
            if is_apple and self.appleCombo.count() <= 1:
                self._load_apple_accounts()

    def _load_apple_accounts(self):
        from modules.apple_mail_sender import get_apple_mail_accounts
        prev = self.appleCombo.currentData() or ""
        self.appleCombo.blockSignals(True)
        self.appleCombo.clear()
        self.appleCombo.addItem("Default", "")
        for lbl, em in get_apple_mail_accounts():
            self.appleCombo.addItem(lbl, em)
        for i in range(self.appleCombo.count()):
            if self.appleCombo.itemData(i) == prev:
                self.appleCombo.setCurrentIndex(i); break
        self.appleCombo.blockSignals(False)

    # ──────────────────────────────────────────────── refresh ────────────────────

    def refresh(self):
        self._reload_sender_combo()

        # AI badge
        try:
            from modules.groq_client import is_configured
            if is_configured():
                self.aiLbl.setText("✦ Groq cloud AI — ready")
                self.aiLbl.setStyleSheet("font-size:11px; color:#A78BFA; background:transparent;")
                self.aiBadge.setText("✦ Groq")
                self.aiBadge.setStyleSheet(
                    "font-size:11px; padding:2px 10px; border-radius:5px; "
                    "background:rgba(167,139,250,0.15); color:#A78BFA;"
                )
                return
        except Exception:
            pass
        if ls._get_llm() is not None:
            self.aiLbl.setText("● Mistral 7B — ready")
            self.aiLbl.setStyleSheet("font-size:11px; color:#6CCB5F; background:transparent;")
            self.aiBadge.setText("● LLM")
            self.aiBadge.setStyleSheet(
                "font-size:11px; padding:2px 10px; border-radius:5px; "
                "background:rgba(108,203,95,0.15); color:#6CCB5F;"
            )
        else:
            self.aiLbl.setText("○ No AI model — template fallback")
            self.aiLbl.setStyleSheet("font-size:11px; color:#FCE100; background:transparent;")
            self.aiBadge.setText("")

        # Resume
        r = get_setting("resume_path", "")
        if r and os.path.isfile(r):
            self.resumeLbl.setText(f"✓  {os.path.basename(r)}")
            self.resumeLbl.setStyleSheet("font-size:11px; color:#6CCB5F; background:transparent;")
        elif r:
            self.resumeLbl.setText("✗  Resume file not found")
            self.resumeLbl.setStyleSheet("font-size:11px; color:#FF99A4; background:transparent;")
        else:
            self.resumeLbl.setText("Resume not set → Settings")
            self.resumeLbl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.35); background:transparent;")

        # Applications
        conn = get_db()
        rows = conn.execute(
            "SELECT id, company, position, contact_email, status, raw_data "
            "FROM applications WHERE status IN ('pending','sent') ORDER BY created_at DESC"
        ).fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for i, (aid, co, pos, em, st, raw_json) in enumerate(rows):
            self.table.setRowHeight(i, 36)
            raw = _parse_raw(raw_json)

            sector = (raw.get("categories") or "").split(",")[0].strip()[:20] or "—"
            loc    = ", ".join(filter(None, [raw.get("city",""), raw.get("country","")])) or "—"
            loc    = loc[:16]

            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, aid)
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 0, chk)

            for j, v in enumerate([co or "—", sector, loc, st or "pending"]):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if j == 3:
                    fg, _ = STATUS_STYLE.get(v, ("#EFEFEF", ""))
                    item.setForeground(QColor(fg))
                self.table.setItem(i, j + 1, item)

        self.appCountLbl.setText(f"Applications  ·  {len(rows)} total")

    # ──────────────────────────────────────────────── selection ──────────────────

    def _sel_all(self, v: bool):
        s = Qt.CheckState.Checked if v else Qt.CheckState.Unchecked
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item: item.setCheckState(s)

    def _checked_ids(self) -> list[int]:
        ids = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _row_app_id(self, row: int) -> int | None:
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ──────────────────────────────────────────── context / preview ──────────────

    def _show_context(self, row: int):
        """Instant (no AI) preview of startup data when a row is clicked."""
        if row < 0: return
        aid = self._row_app_id(row)
        if not aid: return
        conn = get_db()
        app = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
        conn.close()
        if not app: return

        raw  = _parse_raw(app["raw_data"])
        ctx  = _context_lines(raw)
        em   = app["contact_email"] or "—"
        co   = app["company"] or "—"

        lines = [f"  {co}", f"  {em}", ""]
        if ctx:
            lines.append("  Context the AI will use:")
            for c in ctx:
                lines.append(f"  {c}")
        else:
            lines.append("  No startup data — only company name used.")
            lines.append("  Import an Excel with descriptions to enrich emails.")
        lines += ["", "  Press  ✦ Preview Email  to generate the draft."]

        self.previewEdit.setPlainText("\n".join(lines))
        self.ctxLbl.setText(f"{len(ctx)} fields" if ctx else "no data")

    def _preview(self):
        ids = self._checked_ids()
        if not ids:
            row = self.table.currentRow()
            if row >= 0:
                aid = self._row_app_id(row)
                if aid: ids = [aid]
        if not ids:
            QMessageBox.information(self, "Preview", "Select or click a startup first.")
            return

        conn = get_db()
        app = conn.execute("SELECT * FROM applications WHERE id=?", (ids[0],)).fetchone()
        conn.close()
        if not app: return

        raw     = _parse_raw(app["raw_data"])
        ctx     = _context_lines(raw)
        company = app["company"] or ""
        pos     = (app["position"] or "").strip()
        em      = app["contact_email"] or "—"
        resume  = get_setting("resume_path", "")
        sname   = get_setting("sender_name", "")
        domain  = em.split("@")[-1] if "@" in em else ""

        subject = (
            f"Exploring {pos} opportunities at {company}" if pos
            else f"Joining {company}'s journey — {sname}"
        )

        self.previewEdit.setPlainText("⟳  Generating…")
        self.previewBtn.setEnabled(False)

        try:
            from modules.apple_mail_sender import generate_personalized_intro, build_email_body
            intro = generate_personalized_intro(
                company_name=company,
                short_desc=raw.get("short_description") or app["notes"] or "",
                long_desc=raw.get("long_description") or "",
                categories=raw.get("categories") or "",
                website=raw.get("homepage_url") or "",
                city=raw.get("city") or "",
                country=raw.get("country") or "",
                investors=str(raw.get("investors") or ""),
                funding=str(raw.get("total_funding_usd") or ""),
                employees=str(raw.get("num_employees") or ""),
            )
            body = build_email_body(company, intro, pos)
        except Exception as exc:
            self.previewEdit.setPlainText(f"Error: {exc}")
            self.previewBtn.setEnabled(True)
            return

        self.ctxLbl.setText(f"{len(ctx)} fields used" if ctx else "template only")

        resume_tag = (f"✓ {os.path.basename(resume)}" if resume and os.path.isfile(resume) else "✗ not set")

        out = [
            f"To:      {em}",
            f"Subject: {subject}",
            f"Resume:  {resume_tag}",
            "─" * 52,
            body,
        ]
        if ctx:
            out = ["Context used by AI:", *[f"  {c}" for c in ctx], "", *out]

        self.previewEdit.setPlainText("\n".join(out))
        self.previewBtn.setEnabled(True)

    # ──────────────────────────────────────────────────────── send ────────────────

    def _send(self):
        if self._worker:
            return
        ids   = self._checked_ids()
        limit = self.batchSpin.value()

        if not ids and limit > 0:
            conn = get_db()
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM applications WHERE status='pending' "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()]
            conn.close()

        if not ids:
            QMessageBox.information(self, "Nothing to send",
                "Check some rows, or set a Batch limit to auto-select pending applications.")
            return

        if limit > 0 and self._checked_ids():
            ids = ids[:limit]

        mode, g_acct = self._get_mode()
        dry = self.dryChk.isChecked()
        idx = self.senderCombo.currentIndex()
        via = self._opts[idx][0] if self._opts else "Mail"

        apple_acct = self.appleCombo.currentData() or "" if mode == "apple_mail" else ""
        hint = (f"\nFrom: {g_acct}" if g_acct else "") + (f"\nAccount: {apple_acct}" if apple_acct else "")

        if QMessageBox.question(
            self, "Confirm Send",
            f"{'[DRY RUN]  ' if dry else ''}Send {len(ids)} email(s) via {via}?{hint}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        self.sendBtn.setEnabled(False)
        self.progressBar.setVisible(True)
        self.progressBar.setMaximum(len(ids)); self.progressBar.setValue(0)
        self._sent = 0

        self._worker = BulkSendWorker(
            app_ids=ids,
            sleep_seconds=self.delaySpin.value(),
            dry_run=dry,
            send_to_careers=False,
            sender_mode=mode,
            apple_mail_account=apple_acct,
            google_account_email=g_acct,
        )
        self._worker.progress.connect(self._on_prog)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.start()

    def _on_prog(self, _id, company, status):
        self._sent += 1
        self.progressBar.setValue(self._sent)
        icon = "✓" if "sent" in status else "✗"
        self.statusLbl.setText(f"{icon}  {company}")

    def _on_done(self, r):
        self.sendBtn.setEnabled(True)
        self._on_sender_changed(self.senderCombo.currentIndex())
        self.progressBar.setVisible(False)
        self.statusLbl.setText(
            f"✓ {r['sent']} sent   ✗ {r['failed']} failed   — {r['skipped']} skipped"
        )
        if r["errors"]:
            QMessageBox.warning(self, "Errors", "\n".join(r["errors"][:5]))
        self.refresh()
