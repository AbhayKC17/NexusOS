"""
Spreadsheet page — full Excel-like editable view of all imported data.
All raw_data columns are shown; cells are editable and saved on change.
Right-click a column header to hide/show it.
"""
import json
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QLineEdit, QMessageBox, QMenu, QFileDialog, QApplication,
    QProgressBar,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from database import get_db, get_setting, set_setting
from ui.workers import ExcelImportWorker


# Friendly display names for known columns
_DISPLAY = {
    "name": "Company Name",
    "permalink": "Permalink",
    "uuid": "UUID",
    "operating_status": "Status",
    "company_type": "Company Type",
    "ipo_status": "IPO Status",
    "founded_on": "Founded",
    "num_employees": "Employees",
    "short_description": "Description",
    "full_description": "Full Description",
    "linkedin": "LinkedIn",
    "twitter": "Twitter",
    "facebook": "Facebook",
    "website": "Website",
    "contact_email": "Email",
    "phone_number": "Phone",
    "founders": "Founders",
    "last_funding_type": "Last Funding",
    "last_funding_date": "Funding Date",
    "total_funding_usd": "Total Funding ($)",
    "num_funding_rounds": "Funding Rounds",
    "investors": "Investors",
    "hub_tags": "Hub Tags",
    "rank": "Rank",
    "categories": "Categories",
    "city": "City",
    "country": "Country",
    "departments": "Departments",
    "Status": "Status",
}


class SpreadsheetPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_ids = []          # row → application id
        self._all_cols = []         # ordered list of all column keys
        self._hidden_cols = set()   # column keys hidden by user
        self._rows_data = []        # list of (app_id, raw_dict)
        self._editing = False       # guard against recursive cellChanged
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(14)

        # ── Header ────────────────────────────────────────────────────────────
        top = QHBoxLayout(); top.setSpacing(10)
        t = QLabel("Data  ·  Spreadsheet View"); t.setObjectName("pageTitle")
        top.addWidget(t)
        top.addStretch()

        self.searchBox = QLineEdit()
        self.searchBox.setPlaceholderText("Filter rows…")
        self.searchBox.setFixedWidth(220)
        self.searchBox.textChanged.connect(self._filter)
        top.addWidget(self.searchBox)

        self.importBtn = QPushButton("↑  Import Excel / CSV")
        self.importBtn.setObjectName("accentBtn"); self.importBtn.setFixedHeight(32)
        self.importBtn.clicked.connect(self._import)
        top.addWidget(self.importBtn)

        self.colBtn = QPushButton("⊞  Manage Columns")
        self.colBtn.setObjectName("subtleBtn"); self.colBtn.setFixedHeight(32)
        self.colBtn.clicked.connect(self._manage_columns)
        top.addWidget(self.colBtn)

        self.exportBtn = QPushButton("↓  Export CSV")
        self.exportBtn.setObjectName("subtleBtn"); self.exportBtn.setFixedHeight(32)
        self.exportBtn.clicked.connect(self._export_csv)
        top.addWidget(self.exportBtn)

        self.clearBtn = QPushButton("✕  Clear All Data")
        self.clearBtn.setObjectName("dangerBtn"); self.clearBtn.setFixedHeight(32)
        self.clearBtn.clicked.connect(self._clear_all)
        top.addWidget(self.clearBtn)
        root.addLayout(top)

        # ── Import progress bar (hidden until import starts) ───────────────────
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 0)  # indeterminate
        self.progressBar.setFixedHeight(3)
        self.progressBar.setTextVisible(False)
        self.progressBar.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            "QProgressBar::chunk { background: #0078D4; border-radius: 2px; }"
        )
        self.progressBar.setVisible(False)
        root.addWidget(self.progressBar)

        # ── Subtitle ──────────────────────────────────────────────────────────
        self.subtitle = QLabel("Import an Excel file from the Applications tab to see all columns here.")
        self.subtitle.setObjectName("pageSubtitle")
        root.addWidget(self.subtitle)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl_card = QFrame(); tbl_card.setObjectName("card")
        tbl_lay = QVBoxLayout(tbl_card)
        tbl_lay.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setGridStyle(Qt.PenStyle.SolidLine)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: rgba(255,255,255,0.06); }"
            "QTableWidget::item { padding: 4px 8px; }"
            "QTableWidget::item:selected { background: rgba(0,120,212,0.25); }"
        )
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._header_ctx)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.table.cellChanged.connect(self._on_cell_changed)
        tbl_lay.addWidget(self.table)
        root.addWidget(tbl_card, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        self.statusLbl = QLabel("")
        self.statusLbl.setObjectName("pageSubtitle")
        root.addWidget(self.statusLbl)

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self):
        self._load_hidden()
        self._reload()

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
            "SELECT id, raw_data FROM applications WHERE raw_data IS NOT NULL AND raw_data != '' ORDER BY id"
        ).fetchall()
        conn.close()

        self._rows_data = []
        for r in rows:
            try:
                data = json.loads(r[1])
                self._rows_data.append((r[0], data))
            except Exception:
                pass

        # Build column list: union of all keys, preserving insertion order
        seen = []
        seen_set = set()
        for _, data in self._rows_data:
            for k in data.keys():
                if k not in seen_set:
                    seen.append(k)
                    seen_set.add(k)
        self._all_cols = seen

        visible_cols = [c for c in self._all_cols if c not in self._hidden_cols]
        self._render(self._rows_data, visible_cols)

    def _render(self, rows_data, visible_cols):
        self._editing = True
        self.table.blockSignals(True)

        self.table.setRowCount(len(rows_data))
        self.table.setColumnCount(len(visible_cols))
        self.table.setHorizontalHeaderLabels(
            [_DISPLAY.get(c, c.replace("_", " ").title()) for c in visible_cols]
        )

        for r_idx, (app_id, data) in enumerate(rows_data):
            self.table.setRowHeight(r_idx, 36)
            for c_idx, col in enumerate(visible_cols):
                val = data.get(col, "")
                item = QTableWidgetItem(str(val) if val else "")
                item.setData(Qt.ItemDataRole.UserRole, (app_id, col))
                # Style long-text columns
                if col in ("full_description", "investors", "hub_tags", "departments"):
                    item.setForeground(QColor("rgba(255,255,255,0.55)"))
                self.table.setItem(r_idx, c_idx, item)

        # Reasonable default widths
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
            + (f" · {nh} column{'s' if nh != 1 else ''} hidden" if nh else "")
        )
        self.statusLbl.setText(
            f"Click any cell to edit · Right-click column header to hide/show · All changes auto-save"
        )

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

        # Update the raw_data JSON in DB
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
                    (json.dumps(data, ensure_ascii=False), app_id)
                )
                conn.commit()
                # If it's the company name column, also update the company field
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
            "QMenu { background: #2C2C2C; color: #fff; border: 1px solid rgba(255,255,255,0.1); }"
            "QMenu::item:selected { background: #0078D4; }"
        )
        hide_act = menu.addAction(f"Hide  \"{display}\"")
        menu.addSeparator()
        show_all_act = menu.addAction(f"Show All Hidden Columns")

        action = menu.exec(self.table.horizontalHeader().mapToGlobal(pos))
        if action == hide_act:
            self._hidden_cols.add(col_key)
            self._save_hidden()
            self._reload()
        elif action == show_all_act:
            self._hidden_cols.clear()
            self._save_hidden()
            self._reload()

    def _manage_columns(self):
        """Show a dialog listing hidden columns with option to restore them."""
        if not self._hidden_cols:
            QMessageBox.information(self, "Columns", "No columns are hidden.\nRight-click any column header to hide it.")
            return

        hidden_list = "\n".join(
            f"  • {_DISPLAY.get(c, c)}" for c in sorted(self._hidden_cols)
        )
        reply = QMessageBox.question(
            self, "Hidden Columns",
            f"Currently hidden:\n{hidden_list}\n\nRestore all?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._hidden_cols.clear()
            self._save_hidden()
            self._reload()

    # ── Filter ────────────────────────────────────────────────────────────────

    def _filter(self, text):
        text = text.lower()
        for r in range(self.table.rowCount()):
            match = False
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(r, not match if text else False)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "export.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            visible_cols = [c for c in self._all_cols if c not in self._hidden_cols]
            lines = [",".join(f'"{_DISPLAY.get(c,c)}"' for c in visible_cols)]
            for _, data in self._rows_data:
                row_vals = [f'"{str(data.get(c,"")).replace(chr(34), chr(39))}"' for c in visible_cols]
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
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
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
                f"Imported:           {result['imported']}\n"
                f"Duplicates skipped: {result['duplicates_skipped']}\n"
                f"Auto-UUIDs:         {result['new_uuid_generated']}"
                f"{col_info}"
            )
        self._reload()

    # ── Clear ─────────────────────────────────────────────────────────────────

    def _clear_all(self):
        reply = QMessageBox.question(
            self, "Clear All Data",
            "This will permanently delete ALL applications and their replies.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
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
