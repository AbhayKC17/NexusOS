"""
Campaign Manager — multi-run, status-aware bulk sender.

Layout
──────
  QTabWidget
  ├── Tab 1: Campaign Manager
  │    ├── Left panel (300px) — sender config + run controls + active runs
  │    └── Right panel — application queue table + AI preview
  └── Tab 2: AI Automation
"""
import json
import os
import uuid as _uuid_mod
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QSpinBox, QFrame, QProgressBar, QTextEdit, QMessageBox,
    QSplitter, QComboBox, QFormLayout, QSizePolicy, QScrollArea,
    QTabWidget, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from database import get_db, get_setting
from ui.workers import BulkSendWorker
import modules.llm_summarizer as ls


# ── Status colours (light theme) ──────────────────────────────────────────────

_STATUS_FG = {
    "pending":     "#9D5D00",
    "in_progress": "#0067C0",
    "sent":        "#107C10",
    "replied":     "#107C10",
    "rejected":    "#C42B1C",
    "offer":       "#6E4FBE",
    "interview":   "#0078D4",
}
_STATUS_BG = {
    "pending":     "rgba(251,191,36,0.12)",
    "in_progress": "rgba(0,103,192,0.10)",
    "sent":        "rgba(16,124,16,0.10)",
    "replied":     "rgba(16,124,16,0.12)",
    "rejected":    "rgba(196,43,28,0.10)",
    "offer":       "rgba(110,79,190,0.10)",
    "interview":   "rgba(0,120,212,0.10)",
}


def _sender_options() -> list[tuple[str, str, str]]:
    """Returns list of (label, mode, account_email)."""
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
    loc = ", ".join(filter(None, [raw.get("city", ""), raw.get("country", "")]))
    if loc:
        lines.append(f"Location:  {loc}")
    if raw.get("total_funding_usd"):
        try:
            f = float(str(raw["total_funding_usd"]).replace(",", ""))
            s = f"${f/1e9:.1f}B" if f >= 1e9 else f"${f/1e6:.0f}M" if f >= 1e6 else f"${f/1e3:.0f}K"
            lines.append(f"Funding:   {s}")
        except Exception:
            pass
    if raw.get("investors"):
        lines.append(f"Investors: {str(raw['investors'])[:80]}")
    return lines


# ── Run status badge widget ────────────────────────────────────────────────────

class _RunRow(QFrame):
    """Single run row — status dot, stats, Stop (running) or Delete (finished)."""

    def __init__(self, run_id: int, label: str, parent=None):
        super().__init__(parent)
        self.run_id = run_id
        self.setObjectName("card")
        self.setFixedHeight(64)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(4)

        # ── Row 1: status dot + label ──────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        self.statusDot = QLabel("●")
        self.statusDot.setStyleSheet(
            "color: #0067C0; font-size: 12px; background: transparent;"
        )
        top.addWidget(self.statusDot)

        self.labelLbl = QLabel(label)
        self.labelLbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; background: transparent; color: #1A1A1A;"
        )
        top.addWidget(self.labelLbl, 1)
        lay.addLayout(top)

        # ── Row 2: stats + buttons ─────────────────────────────────────────────
        bot = QHBoxLayout()
        bot.setSpacing(6)

        self.statsLbl = QLabel("—")
        self.statsLbl.setStyleSheet(
            "font-size: 11px; color: rgba(0,0,0,0.45); background: transparent;"
        )
        bot.addWidget(self.statsLbl, 1)

        # Stop button — only for running runs
        self.stopBtn = QPushButton("■  Stop")
        self.stopBtn.setObjectName("dangerBtn")
        self.stopBtn.setFixedHeight(26)
        self.stopBtn.setMinimumWidth(72)
        bot.addWidget(self.stopBtn)

        # Delete button — always shown; label changes based on state
        self.deleteBtn = QPushButton("🗑  Delete")
        self.deleteBtn.setObjectName("subtleBtn")
        self.deleteBtn.setFixedHeight(26)
        self.deleteBtn.setMinimumWidth(80)
        self.deleteBtn.setToolTip("Delete this run and free its applications")
        bot.addWidget(self.deleteBtn)
        lay.addLayout(bot)

    def update_run(self, run: dict):
        st = run.get("status", "")
        dot_color = {
            "running":   "#0067C0",
            "completed": "#107C10",
            "failed":    "#C42B1C",
            "stopped":   "#9D5D00",
            "pending":   "#9D5D00",
        }.get(st, "#9D5D00")
        self.statusDot.setStyleSheet(
            f"color: {dot_color}; font-size: 12px; background: transparent;"
        )

        sent    = run.get("sent", 0) or 0
        failed  = run.get("failed", 0) or 0
        skipped = run.get("skipped", 0) or 0
        status_label = {
            "running":   "● Running",
            "completed": "✓ Completed",
            "failed":    "✗ Failed",
            "stopped":   "■ Stopped",
            "pending":   "◌ Pending",
        }.get(st, st)
        self.statsLbl.setText(
            f"{status_label}  ·  ✓{sent}  ✗{failed}  ‒{skipped}"
        )

        is_running = (st == "running")
        self.stopBtn.setVisible(is_running)
        self.stopBtn.setEnabled(is_running)
        # Delete is always visible and always enabled
        self.deleteBtn.setText("⛔  Stop & Delete" if is_running else "🗑  Delete")


# ── Main page ──────────────────────────────────────────────────────────────────

class CampaignPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker  = None
        self._opts: list[tuple[str, str, str]] = []
        self._run_rows: dict[int, _RunRow] = {}      # run_id → _RunRow
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_runs)
        self._build()

    # ─────────────────────────────────────────────────────── build ──────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(
            "QTabWidget::pane{border:none; margin:0;}"
            "QTabBar::tab{padding:8px 18px; font-size:12px; font-weight:600;}"
            "QTabBar::tab:selected{border-bottom:2px solid #0067C0; color:#0067C0;}"
        )

        campaign_w = QWidget()
        self._build_campaign_tab(campaign_w)
        tabs.addTab(campaign_w, "✉  Campaign")

        from campaign.ai_tab import AIAutomationTab
        self._ai_tab = AIAutomationTab()
        tabs.addTab(self._ai_tab, "✦  AI Automation")

        root.addWidget(tabs)

    def _build_campaign_tab(self, container: QWidget):
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setObjectName("pageHeader")
        bar.setFixedHeight(52)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 8, 16, 8)
        bl.setSpacing(10)

        title = QLabel("Campaign Manager")
        title.setStyleSheet(
            "font-size:16px; font-weight:700; background:transparent; color:#1A1A1A;"
        )
        bl.addWidget(title)
        bl.addSpacing(12)

        self.aiBadge = QLabel("")
        self.aiBadge.setStyleSheet(
            "font-size:11px; padding:2px 10px; border-radius:5px; background:transparent;"
        )
        bl.addWidget(self.aiBadge)
        bl.addStretch()

        self.sendBtn = QPushButton("▶  Start Run")
        self.sendBtn.setObjectName("accentBtn")
        self.sendBtn.setFixedHeight(34)
        self.sendBtn.setMinimumWidth(120)
        self.sendBtn.clicked.connect(self._start_run)
        bl.addWidget(self.sendBtn)

        root.addWidget(bar)

        # ── Body splitter ─────────────────────────────────────────────────────
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        body.setStyleSheet(
            "QSplitter::handle{background:rgba(0,0,0,0.07);}"
        )
        root.addWidget(body, 1)

        body.addWidget(self._left_panel())
        body.addWidget(self._right_panel())
        body.setSizes([300, 700])
        body.setCollapsible(0, False)
        body.setCollapsible(1, False)

        self._reload_sender_combo()

    # ─────────────────────────────────────────────────── left panel ─────────────

    def _left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 12, 16)
        lay.setSpacing(14)

        # ── Sender ────────────────────────────────────────────────────────────
        lay.addWidget(self._section("SEND FROM"))

        self.senderCombo = QComboBox()
        self.senderCombo.setFixedHeight(34)
        self.senderCombo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.senderCombo.currentIndexChanged.connect(self._on_sender_changed)
        lay.addWidget(self.senderCombo)

        self.accountStatusLbl = QLabel("")
        self.accountStatusLbl.setWordWrap(True)
        self.accountStatusLbl.setStyleSheet(
            "font-size:11px; background:transparent;"
        )
        lay.addWidget(self.accountStatusLbl)

        self.appleRow = QWidget()
        ar = QHBoxLayout(self.appleRow)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(6)
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
        self.resumeLbl.setStyleSheet(
            "font-size:11px; color:rgba(0,0,0,0.5); background:transparent;"
        )
        lay.addWidget(self.resumeLbl)

        lay.addWidget(self._divider())

        # ── Options ───────────────────────────────────────────────────────────
        lay.addWidget(self._section("OPTIONS"))

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.delaySpin = QSpinBox()
        self.delaySpin.setRange(0, 300)
        self.delaySpin.setValue(10)
        self.delaySpin.setFixedWidth(68)
        self.delaySpin.setSuffix(" s")
        form.addRow("Delay:", self.delaySpin)

        self.batchSpin = QSpinBox()
        self.batchSpin.setRange(0, 999)
        self.batchSpin.setValue(0)
        self.batchSpin.setSpecialValueText("all")
        self.batchSpin.setFixedWidth(68)
        form.addRow("Batch:", self.batchSpin)
        lay.addLayout(form)

        self.dryChk = QCheckBox("Dry run (no actual emails sent)")
        self.dryChk.setStyleSheet("font-size:12px;")
        lay.addWidget(self.dryChk)

        # ── AI status ─────────────────────────────────────────────────────────
        lay.addWidget(self._divider())
        self.aiLbl = QLabel("AI: checking…")
        self.aiLbl.setWordWrap(True)
        self.aiLbl.setStyleSheet(
            "font-size:11px; color:rgba(0,0,0,0.4); background:transparent;"
        )
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
        self.statusLbl.setStyleSheet(
            "font-size:11px; color:rgba(0,0,0,0.5); background:transparent;"
        )
        lay.addWidget(self.statusLbl)

        lay.addWidget(self._divider())

        # ── Active runs ───────────────────────────────────────────────────────
        lay.addWidget(self._section("ACTIVE RUNS"))

        self.runsContainer = QWidget()
        self._runs_lay = QVBoxLayout(self.runsContainer)
        self._runs_lay.setContentsMargins(0, 0, 0, 0)
        self._runs_lay.setSpacing(6)
        self._runs_lay.addStretch()
        lay.addWidget(self.runsContainer)

        self.statsLbl = QLabel("")
        self.statsLbl.setWordWrap(True)
        self.statsLbl.setStyleSheet(
            "font-size:11px; color:rgba(0,0,0,0.5); background:transparent;"
        )
        lay.addWidget(self.statsLbl)

        lay.addStretch()
        scroll.setWidget(w)
        return scroll

    # ─────────────────────────────────────────────── right panel ────────────────

    def _right_panel(self) -> QWidget:
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setHandleWidth(4)
        vsplit.setStyleSheet(
            "QSplitter::handle{background:rgba(0,0,0,0.07);}"
        )

        # ── Application table ─────────────────────────────────────────────────
        tbl_w = QWidget()
        tl = QVBoxLayout(tbl_w)
        tl.setContentsMargins(12, 12, 12, 6)
        tl.setSpacing(8)

        top_row = QHBoxLayout()
        self.appCountLbl = QLabel("Applications")
        self.appCountLbl.setStyleSheet(
            "font-size:12px; font-weight:600; background:transparent; color:#1A1A1A;"
        )
        top_row.addWidget(self.appCountLbl)
        top_row.addStretch()

        self.filterCombo = QComboBox()
        self.filterCombo.addItems(["All", "Pending only", "Sent only", "In Progress"])
        self.filterCombo.setFixedHeight(26)
        self.filterCombo.currentIndexChanged.connect(self._reload_table_full)
        top_row.addWidget(self.filterCombo)

        for text, fn in [("Select All", lambda: self._sel_all(True)),
                         ("Clear", lambda: self._sel_all(False))]:
            b = QPushButton(text)
            b.setObjectName("subtleBtn")
            b.setFixedHeight(26)
            b.clicked.connect(fn)
            top_row.addWidget(b)
        tl.addLayout(top_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["", "Company", "Contact Email", "Sector", "Location", "Status"]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 28)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 120)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 100)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 90)
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
        pl = QVBoxLayout(prev_w)
        pl.setContentsMargins(12, 6, 12, 12)
        pl.setSpacing(6)

        prev_hdr = QHBoxLayout()
        prev_hdr.addWidget(self._section("AI EMAIL PREVIEW"))
        prev_hdr.addStretch()
        self.ctxLbl = QLabel("")
        self.ctxLbl.setStyleSheet(
            "font-size:10px; color:#0067C0; background:rgba(0,103,192,0.08); "
            "padding:2px 8px; border-radius:4px;"
        )
        prev_hdr.addWidget(self.ctxLbl)
        pl.addLayout(prev_hdr)

        self.previewEdit = QTextEdit()
        self.previewEdit.setReadOnly(True)
        self.previewEdit.setFont(QFont("Menlo, Courier New, monospace", 11))
        self.previewEdit.setPlaceholderText(
            "Click a row or press  ✦ Preview Email  to generate a personalised draft.\n\n"
            "The AI uses: description · sector · location · funding · investors."
        )
        self.previewEdit.setStyleSheet(
            "QTextEdit{border:1px solid rgba(0,0,0,0.08); "
            "border-radius:8px; padding:12px; color:#1A1A1A; "
            "background:#FAFAFA;}"
        )
        pl.addWidget(self.previewEdit, 1)
        vsplit.addWidget(prev_w)

        vsplit.setSizes([420, 280])
        return vsplit

    # ─────────────────────────────────────────────────── helpers ─────────────────

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-size:10px; font-weight:700; letter-spacing:1px; "
            "color:rgba(0,0,0,0.38); background:transparent;"
        )
        return lbl

    @staticmethod
    def _divider() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color:rgba(0,0,0,0.08);")
        return f

    # ─────────────────────────────────────────────────── sender combo ────────────

    def _reload_sender_combo(self):
        prev_mode, prev_acct = self._get_mode()
        self._opts = _sender_options()
        self.senderCombo.blockSignals(True)
        self.senderCombo.clear()
        for label, _, _ in self._opts:
            self.senderCombo.addItem(label)
        for i, (_, m, a) in enumerate(self._opts):
            if m == prev_mode and a == prev_acct:
                self.senderCombo.setCurrentIndex(i)
                break
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
        label, mode, acct = self._opts[idx] if 0 <= idx < len(self._opts) else ("", "smtp", "")
        short = label.split("(")[0].strip() or "Mail"
        self.sendBtn.setText(f"▶  Run via {short}")
        is_apple = (mode == "apple_mail")
        if hasattr(self, "appleRow"):
            self.appleRow.setVisible(is_apple)
            if is_apple and self.appleCombo.count() <= 1:
                self._load_apple_accounts()

        # Show connection status for the selected account
        if not hasattr(self, "accountStatusLbl"):
            return
        if mode == "smtp" and acct:
            try:
                from modules.oauth_manager import list_google_accounts
                connected = [a.get("email", "") for a in list_google_accounts()]
                if acct in connected:
                    self.accountStatusLbl.setText(f"✓  {acct}")
                    self.accountStatusLbl.setStyleSheet(
                        "font-size:11px; color:#107C10; background:transparent;"
                    )
                else:
                    self.accountStatusLbl.setText(
                        f"✗  {acct} not found — go to Settings → Re-connect"
                    )
                    self.accountStatusLbl.setStyleSheet(
                        "font-size:11px; color:#C42B1C; background:transparent;"
                    )
            except Exception:
                self.accountStatusLbl.setText("")
        else:
            self.accountStatusLbl.setText("")

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
                self.appleCombo.setCurrentIndex(i)
                break
        self.appleCombo.blockSignals(False)

    # ─────────────────────────────────────────────────── refresh ─────────────────

    def refresh(self):
        if hasattr(self, "_ai_tab"):
            self._ai_tab.refresh()
        self._reload_sender_combo()

        # AI badge
        try:
            from modules.groq_client import is_configured
            if is_configured():
                self.aiLbl.setText("✦ Groq cloud AI — ready")
                self.aiLbl.setStyleSheet(
                    "font-size:11px; color:#6E4FBE; background:transparent;"
                )
                self.aiBadge.setText("✦ Groq")
                self.aiBadge.setStyleSheet(
                    "font-size:11px; padding:2px 10px; border-radius:5px; "
                    "background:rgba(110,79,190,0.10); color:#6E4FBE;"
                )
                return
        except Exception:
            pass

        if ls._get_llm() is not None:
            self.aiLbl.setText("● Mistral 7B — ready")
            self.aiLbl.setStyleSheet(
                "font-size:11px; color:#107C10; background:transparent;"
            )
            self.aiBadge.setText("● LLM")
            self.aiBadge.setStyleSheet(
                "font-size:11px; padding:2px 10px; border-radius:5px; "
                "background:rgba(16,124,16,0.10); color:#107C10;"
            )
        else:
            self.aiLbl.setText("○ No AI model — template fallback")
            self.aiLbl.setStyleSheet(
                "font-size:11px; color:#9D5D00; background:transparent;"
            )
            self.aiBadge.setText("")

        # Resume
        r = get_setting("resume_path", "")
        if r and os.path.isfile(r):
            self.resumeLbl.setText(f"✓  {os.path.basename(r)}")
            self.resumeLbl.setStyleSheet(
                "font-size:11px; color:#107C10; background:transparent;"
            )
        elif r:
            self.resumeLbl.setText("✗  Resume file not found")
            self.resumeLbl.setStyleSheet(
                "font-size:11px; color:#C42B1C; background:transparent;"
            )
        else:
            self.resumeLbl.setText("Resume not set → Settings")
            self.resumeLbl.setStyleSheet(
                "font-size:11px; color:rgba(0,0,0,0.4); background:transparent;"
            )

        self._reload_table_full()
        self._refresh_runs_panel()

    def _reload_table(self):
        """Load applications ordered by id (same as Data tab)."""
        flt = self.filterCombo.currentText() if hasattr(self, "filterCombo") else "All"
        status_filter = {
            "Pending only": "status='pending'",
            "Sent only":    "status='sent'",
            "In Progress":  "status='in_progress'",
        }.get(flt, "status IN ('pending','in_progress','sent')")

        conn = get_db()
        # Omit raw_data — we don't need it during polls; saves JSON parsing time
        rows = conn.execute(
            f"SELECT id, company, contact_email, status FROM applications "
            f"WHERE {status_filter} ORDER BY id ASC"
        ).fetchall()
        conn.close()

        # Preserve checked IDs by application ID (not row position) before
        # reassigning rows — prevents check-state drift when rows shift.
        checked_ids = set(self._checked_ids())

        n = len(rows)
        self.table.setRowCount(n)
        self.table.blockSignals(True)

        for i, (aid, co, em, st) in enumerate(rows):
            self.table.setRowHeight(i, 36)

            # Always create a fresh checkbox item so the check state is tied
            # to the application ID, not the row index.
            chk = QTableWidgetItem()
            chk.setCheckState(
                Qt.CheckState.Checked if aid in checked_ids
                else Qt.CheckState.Unchecked
            )
            chk.setData(Qt.ItemDataRole.UserRole, aid)
            chk.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable |
                Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable
            )
            self.table.setItem(i, 0, chk)

            for j, v in enumerate([co or "—", em or "—", st or "pending"]):
                existing = self.table.item(i, j + 1)
                if existing and existing.text() == v:
                    continue  # skip unchanged cells
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if j == 2:  # status column
                    item.setForeground(QColor(_STATUS_FG.get(v, "#1A1A1A")))
                    item.setBackground(QColor(_STATUS_BG.get(v, "transparent")))
                self.table.setItem(i, j + 1, item)

        self.table.blockSignals(False)
        self.appCountLbl.setText(f"Applications  ·  {n} total")

    def _reload_table_full(self):
        """Full reload including sector/location from raw_data — called on first load."""
        flt = self.filterCombo.currentText() if hasattr(self, "filterCombo") else "All"
        status_filter = {
            "Pending only": "status='pending'",
            "Sent only":    "status='sent'",
            "In Progress":  "status='in_progress'",
        }.get(flt, "status IN ('pending','in_progress','sent')")

        conn = get_db()
        rows = conn.execute(
            f"SELECT id, company, contact_email, status, raw_data "
            f"FROM applications WHERE {status_filter} ORDER BY id ASC"
        ).fetchall()
        conn.close()

        # Update column count for full view (6 cols)
        if self.table.columnCount() != 6:
            self.table.setColumnCount(6)
            self.table.setHorizontalHeaderLabels(
                ["", "Company", "Contact Email", "Sector", "Location", "Status"]
            )
            h = self.table.horizontalHeader()
            h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(0, 28)
            h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(3, 120)
            h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(4, 90)
            h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(5, 90)

        n = len(rows)
        self.table.setRowCount(n)
        self.table.blockSignals(True)

        for i, (aid, co, em, st, raw_json) in enumerate(rows):
            self.table.setRowHeight(i, 36)
            raw = _parse_raw(raw_json)
            sector = (raw.get("categories") or "").split(",")[0].strip()[:18] or "—"
            loc = ", ".join(filter(None, [raw.get("city", ""), raw.get("country", "")])) or "—"

            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, aid)
            chk.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable |
                Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable
            )
            self.table.setItem(i, 0, chk)

            for j, v in enumerate([co or "—", em or "—", sector, loc[:18], st or "pending"]):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if j == 4:
                    item.setForeground(QColor(_STATUS_FG.get(v, "#1A1A1A")))
                    item.setBackground(QColor(_STATUS_BG.get(v, "transparent")))
                self.table.setItem(i, j + 1, item)

        self.table.blockSignals(False)
        self.appCountLbl.setText(f"Applications  ·  {n} total")

    # ─────────────────────────────────────────────────── runs panel ──────────────

    def _refresh_runs_panel(self):
        """Show all campaign runs (recent 10) + stats in one DB connection."""
        conn = get_db()
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM campaign_runs ORDER BY id DESC LIMIT 10"
        ).fetchall()]
        # Batch stats query with GROUP BY — single pass over applications table
        stats_rows = conn.execute(
            "SELECT status, COUNT(*) FROM applications "
            "WHERE status IN ('pending','in_progress','sent') GROUP BY status"
        ).fetchall()
        conn.close()

        stats = {r[0]: r[1] for r in stats_rows}
        self.statsLbl.setText(
            f"Pending: {stats.get('pending', 0)}  ·  "
            f"In Progress: {stats.get('in_progress', 0)}  ·  "
            f"Sent: {stats.get('sent', 0)}"
        )

        existing_ids = set(self._run_rows.keys())
        new_ids = {r["id"] for r in runs}

        # Remove stale rows
        for rid in existing_ids - new_ids:
            w = self._run_rows.pop(rid, None)
            if w:
                self._runs_lay.removeWidget(w)
                w.deleteLater()

        for run in runs:
            rid   = run["id"]
            acct  = run.get("apple_mail_account") or ""
            mode  = run.get("sender_mode") or ""
            label = f"#{rid}  {acct or mode}"
            if rid not in self._run_rows:
                row = _RunRow(rid, label)
                row.stopBtn.clicked.connect(lambda _, r=rid: self._stop_run(r))
                row.deleteBtn.clicked.connect(lambda _, r=rid: self._remove_run(r))
                self._runs_lay.insertWidget(self._runs_lay.count() - 1, row)
                self._run_rows[rid] = row
            self._run_rows[rid].update_run(run)

        any_running = any(r.get("status") == "running" for r in runs)
        if any_running and not self._poll_timer.isActive():
            self._poll_timer.start(2500)
        elif not any_running and self._poll_timer.isActive():
            self._poll_timer.stop()

    def _poll_runs(self):
        """Light-weight poll: update run badges and stats without a full table reload."""
        conn = get_db()
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM campaign_runs ORDER BY id DESC LIMIT 10"
        ).fetchall()]
        stats_rows = conn.execute(
            "SELECT status, COUNT(*) FROM applications "
            "WHERE status IN ('pending','in_progress','sent') GROUP BY status"
        ).fetchall()
        conn.close()

        stats = {r[0]: r[1] for r in stats_rows}
        self.statsLbl.setText(
            f"Pending: {stats.get('pending', 0)}  ·  "
            f"In Progress: {stats.get('in_progress', 0)}  ·  "
            f"Sent: {stats.get('sent', 0)}"
        )

        any_running = False
        for run in runs:
            rid = run["id"]
            if rid in self._run_rows:
                self._run_rows[rid].update_run(run)
            if run.get("status") == "running":
                any_running = True

        # Only reload the full table when a run is actively sending
        if any_running:
            self._reload_table()

        if not any_running and self._poll_timer.isActive():
            self._poll_timer.stop()

    # ─────────────────────────────────────────────────── selection ────────────────

    def _sel_all(self, v: bool):
        s = Qt.CheckState.Checked if v else Qt.CheckState.Unchecked
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                item.setCheckState(s)

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

    # ─────────────────────────────────────────────── context / preview ────────────

    def _show_context(self, row: int):
        if row < 0:
            return
        aid = self._row_app_id(row)
        if not aid:
            return
        conn = get_db()
        app = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
        conn.close()
        if not app:
            return

        raw = _parse_raw(app["raw_data"])
        ctx = _context_lines(raw)
        em  = app["contact_email"] or "—"
        co  = app["company"] or "—"
        st  = app["status"] or "pending"

        lines = [f"  {co}", f"  {em}", f"  Status: {st}", ""]
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
                if aid:
                    ids = [aid]
        if not ids:
            QMessageBox.information(self, "Preview", "Select or click a startup first.")
            return

        conn = get_db()
        app = conn.execute("SELECT * FROM applications WHERE id=?", (ids[0],)).fetchone()
        conn.close()
        if not app:
            return

        raw     = _parse_raw(app["raw_data"])
        ctx     = _context_lines(raw)
        company = app["company"] or ""
        pos     = (app["position"] or "").strip()
        em      = app["contact_email"] or "—"
        resume  = get_setting("resume_path", "")
        sname   = get_setting("sender_name", "")

        from modules.apple_mail_sender import generate_subject
        srole   = get_setting("sender_role", "")
        subject = generate_subject(company, pos, sname, srole)

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
        resume_tag = (
            f"✓ {os.path.basename(resume)}" if resume and os.path.isfile(resume) else "✗ not set"
        )
        out = [f"To:      {em}", f"Subject: {subject}", f"Resume:  {resume_tag}", "─" * 52, body]
        if ctx:
            out = ["Context used by AI:", *[f"  {c}" for c in ctx], "", *out]

        self.previewEdit.setPlainText("\n".join(out))
        self.previewBtn.setEnabled(True)

    # ─────────────────────────────────────────────────── run control ──────────────

    def _start_run(self):
        """Create a campaign_run record and start it via campaign_runner."""
        mode, g_acct   = self._get_mode()
        dry             = self.dryChk.isChecked()
        delay           = self.delaySpin.value()
        idx             = self.senderCombo.currentIndex()
        via             = self._opts[idx][0] if self._opts else "Mail"
        # For apple_mail: store the mailbox account.
        # For smtp/outlook: store the email address in the same field so the
        # campaign_runner thread can look up which account to send from.
        if mode == "apple_mail":
            apple_acct = self.appleCombo.currentData() or ""
        else:
            apple_acct = g_acct  # Gmail or Outlook email — stored so runner can use it

        # Collect checked IDs (optional — if none checked, run uses pending queue)
        checked = self._checked_ids()
        limit   = self.batchSpin.value()

        if QMessageBox.question(
            self, "Confirm Run",
            f"{'[DRY RUN]  ' if dry else ''}Start campaign run via {via}?\n"
            f"Delay: {delay}s  Batch: {'all' if not limit else limit}\n\n"
            "The run will process pending applications in Data tab order.\n"
            "Multiple runs from different accounts will not overlap.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        # If specific apps are checked, set them to pending temporarily scoped
        # (the campaign_runner will claim them atomically)
        conn = get_db()
        if checked:
            # Only include the selected applications for this run — reset others to pending
            placeholders = ",".join("?" * len(checked))
            conn.execute(
                f"UPDATE applications SET status='pending' "
                f"WHERE id IN ({placeholders}) AND status NOT IN ('sent','replied')",
                checked,
            )
            conn.commit()

        import json as _json
        run_name = f"Run {datetime.now().strftime('%H:%M')} via {via[:20]}"
        conn.execute("""
            INSERT INTO campaign_runs
                (name, sender_mode, apple_mail_account, sleep_seconds,
                 send_to_careers, dry_run, status, target_ids)
            VALUES (?, ?, ?, ?, 0, ?, 'pending', ?)
        """, (run_name, mode, apple_acct, delay, int(dry),
              _json.dumps(checked) if checked else '[]'))
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()

        try:
            from modules.campaign_runner import start_run
            started = start_run(run_id)
            if started:
                self.statusLbl.setText(f"▶  Run #{run_id} started")
            else:
                self.statusLbl.setText(f"Run #{run_id} already active")
        except Exception as e:
            self.statusLbl.setText(f"Error: {str(e)[:60]}")

        self._refresh_runs_panel()
        self._reload_table_full()
        self._poll_timer.start(2500)

    def _stop_run(self, run_id: int):
        try:
            from modules.campaign_runner import stop_run
            stop_run(run_id)
            self.statusLbl.setText(f"■  Run #{run_id} stopping…")
        except Exception as e:
            self.statusLbl.setText(f"Stop error: {str(e)[:60]}")

    def _remove_run(self, run_id: int):
        """Stop (if running) and delete the run. Confirmation only for running runs."""
        conn = get_db()
        run = conn.execute(
            "SELECT status, sent, failed, skipped FROM campaign_runs WHERE id=?", (run_id,)
        ).fetchone()
        conn.close()

        if not run:
            self._drop_run_row(run_id)
            return

        run = dict(run)
        is_running = run.get("status") == "running"

        if is_running:
            reply = QMessageBox.question(
                self, "Stop & Delete Run",
                f"Run #{run_id} is still active.\n\n"
                f"Stop it and delete it?\n\n"
                f"✓ {run.get('sent',0)} sent  ✗ {run.get('failed',0)} failed  "
                f"‒ {run.get('skipped',0)} skipped",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                from modules.campaign_runner import stop_run
                stop_run(run_id)
            except Exception:
                pass

        # Delete from DB and free any claimed apps
        conn = get_db()
        conn.execute("DELETE FROM campaign_runs WHERE id=?", (run_id,))
        conn.execute(
            "UPDATE applications SET status='pending', campaign_run_id=NULL "
            "WHERE campaign_run_id=? AND status='in_progress'",
            (run_id,),
        )
        conn.commit()
        conn.close()

        self._drop_run_row(run_id)
        self.statusLbl.setText(f"Run #{run_id} deleted.")
        self._reload_table_full()
        self._refresh_runs_panel()

    def _drop_run_row(self, run_id: int):
        """Remove the _RunRow widget from the panel without a DB call."""
        w = self._run_rows.pop(run_id, None)
        if w:
            self._runs_lay.removeWidget(w)
            w.deleteLater()

    def _on_prog(self, _id, company, status):
        self._sent = getattr(self, "_sent", 0) + 1
        if hasattr(self, "progressBar"):
            self.progressBar.setValue(self._sent)
        icon = "✓" if "sent" in status else "✗"
        self.statusLbl.setText(f"{icon}  {company}")

    def _on_done(self, r):
        self.sendBtn.setEnabled(True)
        if hasattr(self, "progressBar"):
            self.progressBar.setVisible(False)
        self.statusLbl.setText(
            f"✓ {r['sent']} sent   ✗ {r['failed']} failed   — {r['skipped']} skipped"
        )
        if r.get("errors"):
            QMessageBox.warning(self, "Errors", "\n".join(r["errors"][:5]))
        self.refresh()
