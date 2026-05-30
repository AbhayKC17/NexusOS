"""
Dashboard / Overview page.
Stat cards, Graph-RAG AI search, recent applications table, AI reply summaries.
"""
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QScrollArea, QSizePolicy, QLineEdit, QGridLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from database import get_db
from core.widgets import StatCard, SectionHeader, EmptyState
from core.theme import STATUS_STYLE


# ── AI search worker ──────────────────────────────────────────────────────────

class _AISearchWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, query: str, context: str):
        super().__init__()
        self._query   = query
        self._context = context

    def run(self):
        from modules.llm_summarizer import _get_llm
        llm = _get_llm()
        if llm is None:
            self.error.emit("LLM not loaded — load the model in Settings to use AI search.")
            return
        prompt = (
            "[INST] You are an intelligent business analyst assistant.\n"
            "Below is a dataset of companies in the user's job application tracker.\n\n"
            f"DATASET SUMMARY:\n{self._context}\n\n"
            f"USER QUESTION: {self._query}\n\n"
            "Give a concise, insightful answer in 2-4 sentences. "
            "Be specific — mention company names, numbers, and patterns from the data. [/INST]"
        )
        try:
            out = llm(prompt, max_tokens=300, temperature=0.4,
                      stop=["[INST]", "USER QUESTION:"])
            self.done.emit(out["choices"][0]["text"].strip())
        except Exception as e:
            self.error.emit(str(e))


# ── Dashboard page ────────────────────────────────────────────────────────────

class DashboardPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_worker = None
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # Outer layout holds only a scroll area so all content is reachable at any window size
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)

        _inner = QWidget()
        _scroll.setWidget(_inner)
        outer.addWidget(_scroll)

        root = QVBoxLayout(_inner)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(14)

        # ── Title row ─────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("Overview")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        self.syncBtn = QPushButton("⟳  Sync Replies")
        self.syncBtn.setObjectName("subtleBtn")
        self.syncBtn.setFixedHeight(32)
        self.syncBtn.clicked.connect(self._manual_sync)
        title_row.addWidget(self.syncBtn)
        root.addLayout(title_row)

        # ── Graph RAG search bar ───────────────────────────────────────────────
        search_card = QFrame()
        search_card.setObjectName("cardElevated")
        search_card.setStyleSheet(
            "QFrame#cardElevated { background: rgba(0,120,212,0.07); "
            "border: 1px solid rgba(0,120,212,0.28); border-radius: 10px; }"
        )
        sc = QVBoxLayout(search_card)
        sc.setContentsMargins(16, 12, 16, 12)
        sc.setSpacing(8)

        lbl_row = QHBoxLayout()
        ai_lbl = QLabel("✦  Graph RAG  ·  Ask anything about your companies")
        ai_lbl.setStyleSheet(
            "color: #60CDFF; font-size: 12px; font-weight: 600; background: transparent;"
        )
        lbl_row.addWidget(ai_lbl)
        lbl_row.addStretch()
        hint = QLabel("Powered by Mistral 7B")
        hint.setStyleSheet(
            "color: rgba(0,0,0,0.42); font-size: 11px; background: transparent;"
        )
        lbl_row.addWidget(hint)
        sc.addLayout(lbl_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.aiSearch = QLineEdit()
        self.aiSearch.setPlaceholderText(
            "e.g. Which companies are in logistics?  ·  Find German startups  ·  Who are the investors?"
        )
        self.aiSearch.setFixedHeight(38)
        self.aiSearch.returnPressed.connect(self._run_search)
        input_row.addWidget(self.aiSearch, 1)

        self.aiSearchBtn = QPushButton("Search")
        self.aiSearchBtn.setObjectName("accentBtn")
        self.aiSearchBtn.setFixedSize(90, 38)
        self.aiSearchBtn.clicked.connect(self._run_search)
        input_row.addWidget(self.aiSearchBtn)

        self.aiClearBtn = QPushButton("✕")
        self.aiClearBtn.setObjectName("subtleBtn")
        self.aiClearBtn.setFixedSize(38, 38)
        self.aiClearBtn.setToolTip("Clear results")
        self.aiClearBtn.clicked.connect(self._clear_search)
        self.aiClearBtn.setVisible(False)
        input_row.addWidget(self.aiClearBtn)
        sc.addLayout(input_row)

        self.aiResult = QLabel("")
        self.aiResult.setWordWrap(True)
        self.aiResult.setVisible(False)
        self.aiResult.setStyleSheet(
            "color: #FFFFFF; font-size: 13px; background: transparent; padding: 4px 0;"
        )
        sc.addWidget(self.aiResult)
        root.addWidget(search_card)

        # ── Stat cards — responsive QGridLayout (4 per row) ────────────────────
        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(10)
        root.addLayout(self._stats_grid)

        # ── Middle split: recent table + right column ──────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(12)
        root.addLayout(mid, 1)

        # Left: Recent applications
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        left_card = QFrame()
        left_card.setObjectName("card")
        lc = QVBoxLayout(left_card)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(0)

        lc_hdr = QWidget()
        lc_hdr.setStyleSheet(
            "background: transparent; border-bottom: 1px solid rgba(255,255,255,0.06);"
        )
        lc_hdr_lay = QHBoxLayout(lc_hdr)
        lc_hdr_lay.setContentsMargins(16, 11, 16, 11)
        lc_hdr_lay.addWidget(SectionHeader("Recent Applications"))
        self.filterSearch = QLineEdit()
        self.filterSearch.setPlaceholderText("Filter…")
        self.filterSearch.setFixedWidth(140)
        self.filterSearch.setFixedHeight(26)
        self.filterSearch.textChanged.connect(self._filter_table)
        lc_hdr_lay.addWidget(self.filterSearch)
        lc.addWidget(lc_hdr)

        self.recentTable = QTableWidget(0, 6)
        self.recentTable.setHorizontalHeaderLabels(
            ["Company", "City", "Category", "Status", "Funding", "Reply"]
        )
        h = self.recentTable.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.recentTable.setColumnWidth(1, 90)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.recentTable.setColumnWidth(3, 84)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.recentTable.setColumnWidth(4, 100)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.recentTable.setColumnWidth(5, 82)
        self.recentTable.verticalHeader().setVisible(False)
        self.recentTable.setAlternatingRowColors(True)
        self.recentTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recentTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.recentTable.setShowGrid(False)
        lc.addWidget(self.recentTable)
        left_col.addWidget(left_card, 2)

        # Insights chips strip
        self._insights_row = QHBoxLayout()
        self._insights_row.setSpacing(8)
        left_col.addLayout(self._insights_row)
        mid.addLayout(left_col, 3)

        # Right: AI summaries + graph nodes
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        right_card = QFrame()
        right_card.setObjectName("card")
        rc = QVBoxLayout(right_card)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(0)

        rc_hdr = QWidget()
        rc_hdr.setStyleSheet(
            "background: transparent; border-bottom: 1px solid rgba(255,255,255,0.06);"
        )
        rc_hdr_lay = QHBoxLayout(rc_hdr)
        rc_hdr_lay.setContentsMargins(16, 11, 16, 11)
        rc_hdr_lay.addWidget(SectionHeader("AI Reply Summaries"))
        rc.addWidget(rc_hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.repliesWidget = QWidget()
        self.repliesLayout = QVBoxLayout(self.repliesWidget)
        self.repliesLayout.setContentsMargins(14, 12, 14, 12)
        self.repliesLayout.setSpacing(10)
        self.repliesLayout.addStretch()
        scroll.setWidget(self.repliesWidget)
        rc.addWidget(scroll)
        right_col.addWidget(right_card, 2)

        # Graph nodes card
        graph_card = QFrame()
        graph_card.setObjectName("card")
        gc = QVBoxLayout(graph_card)
        gc.setContentsMargins(14, 12, 14, 14)
        gc.setSpacing(8)
        gc.addWidget(SectionHeader("Graph Nodes  ·  Top Connections"))
        self._graph_nodes_lay = QVBoxLayout()
        self._graph_nodes_lay.setSpacing(6)
        gc.addLayout(self._graph_nodes_lay)
        right_col.addWidget(graph_card, 1)

        mid.addLayout(right_col, 2)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        conn = get_db()
        total     = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        pending   = conn.execute(
            "SELECT COUNT(*) FROM applications WHERE status='pending'"
        ).fetchone()[0]
        sent      = conn.execute(
            "SELECT COUNT(*) FROM applications "
            "WHERE status IN ('sent','replied','interview','offer','rejected')"
        ).fetchone()[0]
        replied   = conn.execute(
            "SELECT COUNT(*) FROM applications WHERE status='replied'"
        ).fetchone()[0]
        interview = conn.execute(
            "SELECT COUNT(*) FROM applications WHERE status='interview'"
        ).fetchone()[0]
        rate = f"{round(replied / sent * 100, 1)}%" if sent else "0%"

        rows_raw = conn.execute(
            "SELECT raw_data FROM applications WHERE raw_data IS NOT NULL AND raw_data != ''"
        ).fetchall()

        countries, categories, investors_set, funded = set(), set(), set(), 0
        total_funding = 0
        for r in rows_raw:
            try:
                d = json.loads(r[0])
                if d.get("country"):
                    countries.add(d["country"])
                for cat in str(d.get("categories", "")).split(","):
                    c = cat.strip()
                    if c and c != "nan":
                        categories.add(c)
                for inv in str(d.get("investors", "")).split(","):
                    inv = inv.strip()
                    if inv and inv != "nan":
                        investors_set.add(inv)
                fund = d.get("total_funding_usd", "")
                if fund and fund not in ("", "nan"):
                    try:
                        total_funding += float(str(fund).replace(",", ""))
                        funded += 1
                    except Exception:
                        pass
            except Exception:
                pass

        if total_funding >= 1_000_000_000:
            funding_str = f"${total_funding / 1e9:.1f}B"
        elif total_funding >= 1_000_000:
            funding_str = f"${total_funding / 1e6:.0f}M"
        elif total_funding > 0:
            funding_str = f"${total_funding / 1e3:.0f}K"
        else:
            funding_str = "N/A"

        # Rebuild stat cards grid (4 per row)
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = [
            (total,           "Total Companies",  "#60CDFF", f"{len(countries)} countries"),
            (pending,         "Pending",           "#FCE100", "not yet sent"),
            (sent,            "Sent",              "#0078D4", f"{replied} replied"),
            (interview,       "Interviews",        "#6CCB5F", "in process"),
            (rate,            "Reply Rate",        "#A78BFA", "email response rate"),
            (len(categories), "Categories",        "#F97316", f"{len(investors_set)} investors"),
            (funding_str,     "Total Funding",     "#22C55E", f"across {funded} companies"),
        ]
        cols = 3
        for i, (val, lbl, color, sub) in enumerate(stats):
            card = StatCard(val, lbl, color, sub)
            self._stats_grid.addWidget(card, i // cols, i % cols)

        # Recent applications table
        rows = conn.execute("""
            SELECT a.company, a.status, a.raw_data,
                   MAX(r.received_at) AS reply_date
            FROM applications a
            LEFT JOIN replies r ON a.id = r.application_id
            GROUP BY a.id
            ORDER BY a.created_at DESC LIMIT 20
        """).fetchall()

        self.recentTable.setRowCount(len(rows))
        for i, (co, st, raw_d, rep) in enumerate(rows):
            self.recentTable.setRowHeight(i, 36)
            city = cat = funding = ""
            if raw_d:
                try:
                    d = json.loads(raw_d)
                    city = d.get("city", "") or ""
                    cats = d.get("categories", "") or ""
                    cat  = cats.split(",")[0].strip() if cats and cats != "nan" else ""
                    fund = d.get("total_funding_usd", "") or ""
                    if fund and fund not in ("nan", ""):
                        try:
                            f_val = float(str(fund).replace(",", ""))
                            if f_val >= 1e9:   funding = f"${f_val/1e9:.1f}B"
                            elif f_val >= 1e6: funding = f"${f_val/1e6:.0f}M"
                            elif f_val >= 1e3: funding = f"${f_val/1e3:.0f}K"
                            else:              funding = f"${f_val:.0f}"
                        except Exception:
                            pass
                except Exception:
                    pass

            for j, v in enumerate([
                co or "—", city or "—", cat or "—",
                st or "pending", funding or "—",
                (rep or "")[:10] or "—",
            ]):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if j == 3:
                    fg, _ = STATUS_STYLE.get(v, ("#FFFFFF", ""))
                    item.setForeground(QColor(fg))
                elif j == 4 and v not in ("—", ""):
                    item.setForeground(QColor("#6CCB5F"))
                self.recentTable.setItem(i, j, item)

        # Insights: top countries
        while self._insights_row.count():
            item = self._insights_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        country_counts: dict = {}
        cat_counts: dict = {}
        for r in rows_raw:
            try:
                d = json.loads(r[0])
                c = d.get("country", "")
                if c and c != "nan":
                    country_counts[c] = country_counts.get(c, 0) + 1
                for cat in str(d.get("categories", "")).split(","):
                    cat = cat.strip()
                    if cat and cat != "nan":
                        cat_counts[cat] = cat_counts.get(cat, 0) + 1
            except Exception:
                pass

        for country, cnt in sorted(country_counts.items(), key=lambda x: -x[1])[:3]:
            chip = QLabel(f"🌍 {country}  {cnt}")
            chip.setStyleSheet(
                "color: #60CDFF; background: rgba(0,120,212,0.12); border-radius: 10px; "
                "padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            self._insights_row.addWidget(chip)
        self._insights_row.addStretch()

        # Graph nodes
        while self._graph_nodes_lay.count():
            item = self._graph_nodes_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        top_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:8]
        for cat, cnt in top_cats:
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)

            dot = QLabel("●")
            dot.setStyleSheet(
                "color: #0078D4; font-size: 8px; background: transparent;"
            )
            rl.addWidget(dot)

            name_lbl = QLabel(cat[:40])
            name_lbl.setStyleSheet(
                "color: #1A1A1A; font-size: 12px; background: transparent;"
            )
            rl.addWidget(name_lbl, 1)

            cnt_lbl = QLabel(str(cnt))
            cnt_lbl.setStyleSheet(
                "color: rgba(0,0,0,0.42); font-size: 11px; background: transparent;"
            )
            rl.addWidget(cnt_lbl)

            pct = max(int((cnt / max(top_cats[0][1], 1)) * 100), 8)
            bar = QFrame()
            bar.setFixedHeight(3)
            bar.setMaximumWidth(pct * 2)
            bar.setStyleSheet(
                "background: rgba(0,120,212,0.5); border-radius: 2px;"
            )
            rl.addWidget(bar)
            self._graph_nodes_lay.addWidget(row_w)

        # AI reply summaries
        conn2 = get_db()
        while self.repliesLayout.count() > 1:
            item = self.repliesLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recent = conn2.execute("""
            SELECT r.summary, r.received_at, a.company, a.position
            FROM replies r JOIN applications a ON r.application_id = a.id
            ORDER BY r.received_at DESC LIMIT 5
        """).fetchall()
        conn.close()
        conn2.close()

        if not recent:
            lbl = EmptyState("No replies yet — send emails and sync to see AI summaries.")
            self.repliesLayout.insertWidget(0, lbl)
        else:
            for summary, recv, company, position in recent:
                card = QFrame()
                card.setObjectName("cardElevated")
                card.setStyleSheet(
                    "QFrame#cardElevated { background: #252530; border-radius: 8px; "
                    "border: 1px solid rgba(255,255,255,0.07); }"
                )
                cl = QVBoxLayout(card)
                cl.setContentsMargins(12, 10, 12, 10)
                cl.setSpacing(4)

                top = QHBoxLayout()
                co_lbl = QLabel(f"<b>{company or '—'}</b>")
                co_lbl.setStyleSheet(
                    "color: #FFFFFF; font-size: 13px; background: transparent;"
                )
                top.addWidget(co_lbl)
                top.addStretch()
                d_lbl = QLabel((recv or "")[:10])
                d_lbl.setStyleSheet(
                    "color: rgba(0,0,0,0.42); font-size: 11px; background: transparent;"
                )
                top.addWidget(d_lbl)
                cl.addLayout(top)

                if summary:
                    s_lbl = QLabel(summary[:140] + ("…" if len(summary) > 140 else ""))
                    s_lbl.setWordWrap(True)
                    s_lbl.setStyleSheet(
                        "color: #60CDFF; font-size: 12px; background: transparent;"
                    )
                    cl.addWidget(s_lbl)

                self.repliesLayout.insertWidget(
                    self.repliesLayout.count() - 1, card
                )

    # ── Graph RAG search ──────────────────────────────────────────────────────

    def _run_search(self):
        query = self.aiSearch.text().strip()
        if not query:
            return

        self.aiResult.setText("⟳  Searching with Mistral 7B…")
        self.aiResult.setStyleSheet(
            "color: #FCE100; font-size: 13px; background: transparent; padding: 4px 0;"
        )
        self.aiResult.setVisible(True)
        self.aiClearBtn.setVisible(True)
        self.aiSearchBtn.setEnabled(False)

        conn = get_db()
        rows = conn.execute(
            "SELECT company, status, raw_data FROM applications ORDER BY id LIMIT 100"
        ).fetchall()
        conn.close()

        lines = []
        for co, st, raw_d in rows:
            parts = [f"Company: {co or '(unknown)'}"]
            if raw_d:
                try:
                    d = json.loads(raw_d)
                    if d.get("city"):      parts.append(f"City: {d['city']}")
                    if d.get("country"):   parts.append(f"Country: {d['country']}")
                    if d.get("categories"):parts.append(f"Categories: {d['categories'][:80]}")
                    if d.get("investors"): parts.append(f"Investors: {d['investors'][:80]}")
                    if d.get("total_funding_usd"):
                        parts.append(f"Funding: ${d['total_funding_usd']}")
                    if d.get("short_description"):
                        parts.append(f"About: {d['short_description'][:100]}")
                    if d.get("founders"):  parts.append(f"Founders: {d['founders'][:60]}")
                    if d.get("num_employees"):
                        parts.append(f"Employees: {d['num_employees']}")
                except Exception:
                    pass
            parts.append(f"Status: {st}")
            lines.append(" | ".join(parts))

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.quit()

        self._search_worker = _AISearchWorker(query, "\n".join(lines[:60]))
        self._search_worker.done.connect(self._on_search_result)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.finished.connect(
            lambda: self.aiSearchBtn.setEnabled(True)
        )
        self._search_worker.start()

    def _on_search_result(self, text: str):
        self.aiResult.setText(text)
        self.aiResult.setStyleSheet(
            "color: #FFFFFF; font-size: 13px; background: transparent; padding: 4px 0;"
        )

    def _on_search_error(self, err: str):
        self.aiResult.setText(f"⚠  {err}")
        self.aiResult.setStyleSheet(
            "color: #FCE100; font-size: 12px; background: transparent; padding: 4px 0;"
        )

    def _clear_search(self):
        self.aiSearch.clear()
        self.aiResult.setVisible(False)
        self.aiResult.setText("")
        self.aiClearBtn.setVisible(False)

    # ── Table filter ──────────────────────────────────────────────────────────

    def _filter_table(self, text: str):
        text = text.lower()
        for r in range(self.recentTable.rowCount()):
            match = any(
                self.recentTable.item(r, c)
                and text in self.recentTable.item(r, c).text().lower()
                for c in range(self.recentTable.columnCount())
            )
            self.recentTable.setRowHidden(r, not match if text else False)

    # ── Manual sync ───────────────────────────────────────────────────────────

    def _manual_sync(self):
        from ui.workers import EmailSyncWorker
        self.syncBtn.setEnabled(False)
        self.syncBtn.setText("⟳  Syncing…")
        self._sync_w = EmailSyncWorker()
        self._sync_w.done.connect(self._on_sync_done)
        self._sync_w.finished.connect(lambda: setattr(self, "_sync_w", None))
        self._sync_w.start()

    def _on_sync_done(self, count: int, errors: list):
        self.syncBtn.setEnabled(True)
        self.syncBtn.setText("⟳  Sync Replies")
        if count:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Sync Complete",
                f"{count} new repl{'y' if count == 1 else 'ies'} received."
            )
        self.refresh()
