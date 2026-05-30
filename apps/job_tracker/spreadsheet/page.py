"""
Data tab — full spreadsheet view with sortable/filterable columns.
All raw_data columns shown; cells editable and auto-saved.
Sort state is persisted and reflected in Campaign tab ordering.
"""
import json
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QLineEdit, QMessageBox, QMenu, QFileDialog, QApplication,
    QProgressBar, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon

from database import get_db, get_setting, set_setting
from ui.workers import ExcelImportWorker


_DISPLAY = {
    "name":              "Company Name",
    "permalink":         "Permalink",
    "uuid":              "UUID",
    "operating_status":  "Status",
    "company_type":      "Company Type",
    "ipo_status":        "IPO Status",
    "founded_on":        "Founded",
    "num_employees":     "Employees",
    "short_description": "Description",
    "full_description":  "Full Description",
    "linkedin":          "LinkedIn",
    "twitter":           "Twitter",
    "facebook":          "Facebook",
    "website":           "Website",
    "contact_email":     "Email",
    "phone_number":      "Phone",
    "founders":          "Founders",
    "last_funding_type": "Last Funding",
    "last_funding_date": "Funding Date",
    "total_funding_usd": "Total Funding ($)",
    "num_funding_rounds": "Funding Rounds",
    "investors":         "Investors",
    "hub_tags":          "Hub Tags",
    "rank":              "Rank",
    "categories":        "Categories",
    "city":              "City",
    "country":           "Country",
    "departments":       "Departments",
    "Status":            "Status",
}


class SpreadsheetPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_ids: list[int]       = []
        self._all_cols: list[str]      = []
        self._hidden_cols: set         = set()
        self._rows_data: list          = []
        self._editing                  = False
        self._sort_col: str | None     = None
        self._sort_asc: bool           = True
        self._col_filters: dict        = {}   # col_key → filter text
        self._worker                   = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(14)

        # ── Header ────────────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)
        t = QLabel("Data  ·  Spreadsheet View")
        t.setObjectName("pageTitle")
        top.addWidget(t)
        top.addStretch()

        self.searchBox = QLineEdit()
        self.searchBox.setPlaceholderText("Search all columns…")
        self.searchBox.setFixedWidth(220)
        self.searchBox.textChanged.connect(self._filter_rows)
        top.addWidget(self.searchBox)

        self.importBtn = QPushButton("↑  Import Excel / CSV")
        self.importBtn.setObjectName("accentBtn")
        self.importBtn.setFixedHeight(32)
        self.importBtn.clicked.connect(self._import)
        top.addWidget(self.importBtn)

        self.dedupBtn = QPushButton("⊘  Remove Duplicates")
        self.dedupBtn.setObjectName("subtleBtn")
        self.dedupBtn.setFixedHeight(32)
        self.dedupBtn.clicked.connect(self._remove_duplicates)
        top.addWidget(self.dedupBtn)

        self.colBtn = QPushButton("⊞  Columns")
        self.colBtn.setObjectName("subtleBtn")
        self.colBtn.setFixedHeight(32)
        self.colBtn.clicked.connect(self._manage_columns)
        top.addWidget(self.colBtn)

        self.exportBtn = QPushButton("↓  Export CSV")
        self.exportBtn.setObjectName("subtleBtn")
        self.exportBtn.setFixedHeight(32)
        self.exportBtn.clicked.connect(self._export_csv)
        top.addWidget(self.exportBtn)

        self.clearBtn = QPushButton("✕  Clear All")
        self.clearBtn.setObjectName("dangerBtn")
        self.clearBtn.setFixedHeight(32)
        self.clearBtn.clicked.connect(self._clear_all)
        top.addWidget(self.clearBtn)
        root.addLayout(top)

        # ── Progress bar ──────────────────────────────────────────────────────
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 0)
        self.progressBar.setFixedHeight(3)
        self.progressBar.setTextVisible(False)
        self.progressBar.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            "QProgressBar::chunk { background: #0078D4; border-radius: 2px; }"
        )
        self.progressBar.setVisible(False)
        root.addWidget(self.progressBar)

        # ── Column filter bar (hidden until data loaded) ───────────────────────
        self.filterBar = QFrame()
        self.filterBar.setObjectName("card")
        self.filterBar.setVisible(False)
        filter_lay = QHBoxLayout(self.filterBar)
        filter_lay.setContentsMargins(12, 8, 12, 8)
        filter_lay.setSpacing(8)
        filter_icon = QLabel("⊿  Active filters:")
        filter_icon.setStyleSheet(
            "font-size:11px; font-weight:700; color:rgba(0,0,0,0.5); background:transparent;"
        )
        filter_lay.addWidget(filter_icon)
        self.filterTagsLay = QHBoxLayout()
        self.filterTagsLay.setSpacing(6)
        filter_lay.addLayout(self.filterTagsLay, 1)
        clear_filters_btn = QPushButton("Clear All Filters")
        clear_filters_btn.setObjectName("subtleBtn")
        clear_filters_btn.setFixedHeight(26)
        clear_filters_btn.clicked.connect(self._clear_all_filters)
        filter_lay.addWidget(clear_filters_btn)
        root.addWidget(self.filterBar)

        # ── Subtitle ──────────────────────────────────────────────────────────
        self.subtitle = QLabel(
            "Import an Excel or CSV file to view all company data here."
        )
        self.subtitle.setObjectName("pageSubtitle")
        root.addWidget(self.subtitle)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl_card = QFrame()
        tbl_card.setObjectName("card")
        tbl_lay = QVBoxLayout(tbl_card)
        tbl_lay.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setGridStyle(Qt.PenStyle.SolidLine)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: rgba(0,0,0,0.06); }"
            "QTableWidget::item { padding: 4px 8px; color: #1A1A1A; }"
            "QTableWidget::item:selected { background: rgba(0,103,192,0.12); }"
        )
        hdr = self.table.horizontalHeader()
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._header_ctx)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setMinimumSectionSize(80)
        hdr.sectionClicked.connect(self._on_header_click)
        hdr.setSortIndicatorShown(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.table.cellChanged.connect(self._on_cell_changed)
        tbl_lay.addWidget(self.table)
        root.addWidget(tbl_card, 1)

        # ── Status bar ────────────────────────────────────────────────────────
        self.statusLbl = QLabel("")
        self.statusLbl.setObjectName("pageSubtitle")
        root.addWidget(self.statusLbl)

    # ── Refresh / load ────────────────────────────────────────────────────────

    def refresh(self):
        self._load_hidden()
        self._reload()

    def _needs_reload(self) -> bool:
        """Quick row-count check — skip expensive reload if data unchanged."""
        conn = get_db()
        n = conn.execute(
            "SELECT COUNT(*) FROM applications WHERE raw_data IS NOT NULL AND raw_data != ''"
        ).fetchone()[0]
        conn.close()
        return n != len(self._rows_data)

    def _load_hidden(self):
        raw = get_setting("spreadsheet_hidden_cols", "[]")
        try:
            self._hidden_cols = set(json.loads(raw))
        except Exception:
            self._hidden_cols = set()

    def _save_hidden(self):
        set_setting("spreadsheet_hidden_cols", json.dumps(list(self._hidden_cols)))

    def _reload(self):
        conn = get_db()
        rows = conn.execute(
            "SELECT id, raw_data FROM applications "
            "WHERE raw_data IS NOT NULL AND raw_data != '' ORDER BY id ASC"
        ).fetchall()
        conn.close()

        self._rows_data = []
        for r in rows:
            try:
                data = json.loads(r[1])
                self._rows_data.append((r[0], data))
            except Exception:
                pass

        # Build ordered column list
        seen, seen_set = [], set()
        for _, data in self._rows_data:
            for k in data.keys():
                if k not in seen_set:
                    seen.append(k)
                    seen_set.add(k)
        self._all_cols = seen

        self._apply_sort_and_filter()

    def _apply_sort_and_filter(self):
        rows = list(self._rows_data)

        # Apply column filter
        for col_key, flt_text in self._col_filters.items():
            if flt_text:
                rows = [
                    (aid, d) for aid, d in rows
                    if flt_text.lower() in str(d.get(col_key, "")).lower()
                ]

        # Apply sort
        if self._sort_col and self._sort_col in self._all_cols:
            def sort_key(item):
                v = item[1].get(self._sort_col, "") or ""
                try:
                    return (0, float(v))
                except (ValueError, TypeError):
                    return (1, str(v).lower())
            rows.sort(key=sort_key, reverse=not self._sort_asc)

        visible_cols = [c for c in self._all_cols if c not in self._hidden_cols]
        self._render(rows, visible_cols)

        # Update filter bar
        self._update_filter_bar()

    def _render(self, rows_data, visible_cols):
        self._editing = True
        self.table.blockSignals(True)

        self.table.setRowCount(len(rows_data))
        self.table.setColumnCount(len(visible_cols))

        # Build header labels with sort indicator
        labels = []
        for c in visible_cols:
            disp = _DISPLAY.get(c, c.replace("_", " ").title())
            if c == self._sort_col:
                disp += "  ↑" if self._sort_asc else "  ↓"
            labels.append(disp)
        self.table.setHorizontalHeaderLabels(labels)

        for r_idx, (app_id, data) in enumerate(rows_data):
            self.table.setRowHeight(r_idx, 36)
            for c_idx, col in enumerate(visible_cols):
                val = data.get(col, "")
                item = QTableWidgetItem(str(val) if val else "")
                item.setData(Qt.ItemDataRole.UserRole, (app_id, col))
                if col in ("full_description", "investors", "hub_tags", "departments"):
                    item.setForeground(QColor("rgba(0,0,0,0.45)"))
                # Highlight filtered columns
                if col in self._col_filters and self._col_filters[col]:
                    item.setBackground(QColor("rgba(0,103,192,0.06)"))
                self.table.setItem(r_idx, c_idx, item)

        # Column widths
        for c_idx, col in enumerate(visible_cols):
            if col in ("full_description", "investors", "short_description"):
                self.table.setColumnWidth(c_idx, 260)
            elif col in ("name", "founders", "categories"):
                self.table.setColumnWidth(c_idx, 180)
            elif col in ("uuid", "permalink", "website", "linkedin"):
                self.table.setColumnWidth(c_idx, 200)
            else:
                self.table.setColumnWidth(c_idx, 120)

        self.table.blockSignals(False)
        self._editing = False

        n = len(rows_data)
        nh = len(self._hidden_cols)
        self.subtitle.setText(
            f"{n} companies · {len(visible_cols)} columns shown"
            + (f" · {nh} hidden" if nh else "")
        )
        self.statusLbl.setText(
            "Click any cell to edit · Click column header to sort · "
            "Right-click header for filter/hide options"
        )

    # ── Header click → sort ───────────────────────────────────────────────────

    def _on_header_click(self, logical_idx: int):
        visible_cols = [c for c in self._all_cols if c not in self._hidden_cols]
        if logical_idx >= len(visible_cols):
            return
        col_key = visible_cols[logical_idx]
        if self._sort_col == col_key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_key
            self._sort_asc = True
        # Save sort state so Campaign tab can read it
        set_setting("data_sort_col", col_key)
        set_setting("data_sort_asc", "1" if self._sort_asc else "0")
        self._apply_sort_and_filter()

    # ── Column filter ─────────────────────────────────────────────────────────

    def _update_filter_bar(self):
        # Clear existing tags
        while self.filterTagsLay.count():
            item = self.filterTagsLay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active = {k: v for k, v in self._col_filters.items() if v}
        self.filterBar.setVisible(bool(active))

        for col_key, flt_text in active.items():
            disp = _DISPLAY.get(col_key, col_key)
            tag = QPushButton(f'{disp}: "{flt_text}"  ×')
            tag.setFixedHeight(24)
            tag.setObjectName("subtleBtn")
            tag.setStyleSheet(
                "QPushButton { background: rgba(0,103,192,0.10); "
                "border: 1px solid rgba(0,103,192,0.25); "
                "border-radius: 12px; font-size: 11px; padding: 2px 10px; color: #0067C0; }"
                "QPushButton:hover { background: rgba(0,103,192,0.20); }"
            )
            tag.clicked.connect(lambda _, k=col_key: self._remove_filter(k))
            self.filterTagsLay.addWidget(tag)

    def _remove_filter(self, col_key: str):
        self._col_filters.pop(col_key, None)
        self._apply_sort_and_filter()

    def _clear_all_filters(self):
        self._col_filters.clear()
        self._apply_sort_and_filter()

    def _filter_rows(self, text):
        """Global search — hide rows not matching the search text."""
        q = text.lower()
        for r in range(self.table.rowCount()):
            match = not q
            if not match:
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    if item and q in item.text().lower():
                        match = True
                        break
            self.table.setRowHidden(r, not match)

    # ── Cell editing ──────────────────────────────────────────────────────────

    def _on_cell_changed(self, row, col):
        if self._editing:
            return
        item = self.table.item(row, col)
        if not item:
            return
        meta = item.data(Qt.ItemDataRole.UserRole)
        if not meta:
            return
        app_id, col_key = meta
        new_val = item.text()

        conn = get_db()
        row_db = conn.execute(
            "SELECT raw_data FROM applications WHERE id=?", (app_id,)
        ).fetchone()
        if row_db and row_db[0]:
            try:
                data = json.loads(row_db[0])
                data[col_key] = new_val
                conn.execute(
                    "UPDATE applications SET raw_data=? WHERE id=?",
                    (json.dumps(data, ensure_ascii=False), app_id),
                )
                conn.commit()
                if col_key in ("name", "company", "company name", "Company Name"):
                    conn.execute(
                        "UPDATE applications SET company=? WHERE id=?", (new_val, app_id)
                    )
                    conn.commit()
            except Exception as e:
                print(f"[Spreadsheet] Save error: {e}")
        conn.close()

    # ── Column management ─────────────────────────────────────────────────────

    def _header_ctx(self, pos):
        col_idx = self.table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0:
            return
        visible_cols = [c for c in self._all_cols if c not in self._hidden_cols]
        if col_idx >= len(visible_cols):
            return
        col_key = visible_cols[col_idx]
        display = _DISPLAY.get(col_key, col_key)

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; color: #1A1A1A; "
            "border: 1px solid rgba(0,0,0,0.12); border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 7px 18px; border-radius: 5px; }"
            "QMenu::item:selected { background: rgba(0,103,192,0.10); color: #0067C0; }"
        )

        sort_asc  = menu.addAction(f"Sort A → Z")
        sort_desc = menu.addAction(f"Sort Z → A")
        menu.addSeparator()

        flt_action = menu.addAction(f"Filter  '{display}'…")
        if col_key in self._col_filters and self._col_filters[col_key]:
            clear_flt = menu.addAction(f"Clear filter on  '{display}'")
        else:
            clear_flt = None
        menu.addSeparator()

        hide_act     = menu.addAction(f"Hide  '{display}'")
        show_all_act = menu.addAction("Show All Hidden Columns")

        action = menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

        if action == sort_asc:
            self._sort_col = col_key
            self._sort_asc = True
            set_setting("data_sort_col", col_key)
            set_setting("data_sort_asc", "1")
            self._apply_sort_and_filter()
        elif action == sort_desc:
            self._sort_col = col_key
            self._sort_asc = False
            set_setting("data_sort_col", col_key)
            set_setting("data_sort_asc", "0")
            self._apply_sort_and_filter()
        elif action == flt_action:
            self._show_filter_dialog(col_key, display)
        elif clear_flt and action == clear_flt:
            self._remove_filter(col_key)
        elif action == hide_act:
            self._hidden_cols.add(col_key)
            self._save_hidden()
            self._reload()
        elif action == show_all_act:
            self._hidden_cols.clear()
            self._save_hidden()
            self._reload()

    def _show_filter_dialog(self, col_key: str, display: str):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Filter: {display}")
        dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)

        lay.addWidget(QLabel(f"Show rows where  '{display}'  contains:"))

        current = self._col_filters.get(col_key, "")
        edit = QLineEdit(current)
        edit.setPlaceholderText("Filter text…")
        lay.addWidget(edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            flt = edit.text().strip()
            if flt:
                self._col_filters[col_key] = flt
            else:
                self._col_filters.pop(col_key, None)
            self._apply_sort_and_filter()

    def _manage_columns(self):
        if not self._hidden_cols:
            QMessageBox.information(
                self, "Columns",
                "No columns are hidden.\nRight-click any column header to hide it.",
            )
            return
        hidden_list = "\n".join(
            f"  • {_DISPLAY.get(c, c)}" for c in sorted(self._hidden_cols)
        )
        reply = QMessageBox.question(
            self, "Hidden Columns",
            f"Currently hidden:\n{hidden_list}\n\nRestore all?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._hidden_cols.clear()
            self._save_hidden()
            self._reload()

    # ── Duplicate removal ─────────────────────────────────────────────────────

    def _remove_duplicates(self):
        """Remove duplicate applications (same company name or same contact email)."""
        conn = get_db()
        rows = conn.execute(
            "SELECT id, company, contact_email FROM applications ORDER BY id ASC"
        ).fetchall()

        seen_company = {}
        seen_email   = {}
        to_delete    = []

        for app_id, company, email in rows:
            c_key = (company or "").strip().lower()
            e_key = (email or "").strip().lower()
            is_dup = False
            if c_key and c_key in seen_company:
                is_dup = True
            if e_key and e_key in seen_email:
                is_dup = True
            if is_dup:
                to_delete.append(app_id)
            else:
                if c_key:
                    seen_company[c_key] = app_id
                if e_key:
                    seen_email[e_key] = app_id

        if not to_delete:
            QMessageBox.information(self, "No Duplicates", "No duplicate entries found.")
            conn.close()
            return

        reply = QMessageBox.question(
            self, "Remove Duplicates",
            f"Found {len(to_delete)} duplicate entries (same company name or email).\n\n"
            "Remove them? The first occurrence of each will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            conn.close()
            return

        placeholders = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM replies WHERE application_id IN ({placeholders})", to_delete)
        conn.execute(f"DELETE FROM applications WHERE id IN ({placeholders})", to_delete)
        conn.commit()
        conn.close()

        QMessageBox.information(
            self, "Done", f"Removed {len(to_delete)} duplicate entries."
        )
        self._reload()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "export.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            visible_cols = [c for c in self._all_cols if c not in self._hidden_cols]
            lines = [",".join(f'"{_DISPLAY.get(c, c)}"' for c in visible_cols)]
            for _, data in self._rows_data:
                row_vals = [
                    f'"{str(data.get(c, "")).replace(chr(34), chr(39))}"'
                    for c in visible_cols
                ]
                lines.append(",".join(row_vals))
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    # ── Import ────────────────────────────────────────────────────────────────

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel / CSV File", "", "Spreadsheets (*.xlsx *.xls *.csv)"
        )
        if not path:
            return
        self.importBtn.setEnabled(False)
        self.importBtn.setText("Importing…")
        self.progressBar.setVisible(True)

        self._worker = ExcelImportWorker(path, os.path.basename(path))
        self._worker.done.connect(self._import_done)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.start()

    def _import_done(self, result):
        self.importBtn.setEnabled(True)
        self.importBtn.setText("↑  Import Excel / CSV")
        self.progressBar.setVisible(False)

        if "error" in result:
            QMessageBox.critical(self, "Import Error", result["error"])
        else:
            cols = result.get("columns", [])
            col_info = f"\n{len(cols)} columns detected" if cols else ""
            QMessageBox.information(
                self, "Import Complete",
                f"Imported:            {result['imported']}\n"
                f"Duplicates skipped:  {result['duplicates_skipped']}\n"
                f"Auto-UUIDs:          {result['new_uuid_generated']}"
                f"{col_info}",
            )
        self._reload()

    # ── Clear ─────────────────────────────────────────────────────────────────

    def _clear_all(self):
        reply = QMessageBox.question(
            self, "Clear All Data",
            "This will permanently delete ALL applications and their replies.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        conn = get_db()
        conn.execute("DELETE FROM replies")
        conn.execute("DELETE FROM scheduled_emails")
        conn.execute("DELETE FROM applications")
        conn.commit()
        conn.close()
        self._reload()
        QMessageBox.information(self, "Cleared", "All data has been deleted.")
