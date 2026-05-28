import uuid as _uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QTextEdit, QMessageBox,
    QFrame, QFileDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from database import get_db
from ui.style import STATUS_STYLE
from ui.workers import ExcelImportWorker


class ApplicationDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("Edit Application" if data else "New Application")
        self.setMinimumWidth(520)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setSpacing(16); lay.setContentsMargins(24, 24, 24, 20)

        form = QFormLayout(); form.setSpacing(12); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def f(ph):
            e = QLineEdit(); e.setPlaceholderText(ph); return e

        self.company  = f("e.g. Acme Corp")
        self.position = f("Leave blank to use growth-focused outreach")
        self.email    = f("hr@acme.com")
        self.contact  = f("Jane Smith")
        self.status   = QComboBox()
        self.status.addItems(["pending", "sent", "replied", "interview", "rejected", "offer"])
        self.notes    = QTextEdit()
        self.notes.setPlaceholderText("Referral info, company description, how you found this…")
        self.notes.setFixedHeight(90)

        form.addRow("Company *", self.company)
        form.addRow("Position", self.position)
        form.addRow("Contact Email", self.email)
        form.addRow("Contact Name", self.contact)
        form.addRow("Status", self.status)
        form.addRow("Notes", self.notes)
        lay.addLayout(form)

        if self.data:
            self.company.setText(self.data.get("company", "") or "")
            self.position.setText(self.data.get("position", "") or "")
            self.email.setText(self.data.get("contact_email", "") or "")
            self.contact.setText(self.data.get("contact_name", "") or "")
            idx = self.status.findText(self.data.get("status", "pending"))
            if idx >= 0: self.status.setCurrentIndex(idx)
            self.notes.setPlainText(self.data.get("notes", "") or "")

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_data(self):
        return {
            "company":       self.company.text().strip(),
            "position":      self.position.text().strip(),
            "contact_email": self.email.text().strip(),
            "contact_name":  self.contact.text().strip(),
            "status":        self.status.currentText(),
            "notes":         self.notes.toPlainText().strip(),
        }


class ApplicationsPage(QWidget):
    compose_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_ids = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # ── Title row ─────────────────────────────────────────────────────────
        top = QHBoxLayout(); top.setSpacing(10)
        t = QLabel("Applications"); t.setObjectName("pageTitle")
        top.addWidget(t); top.addStretch()

        self.importBtn = QPushButton("↑  Import Excel / CSV")
        self.importBtn.setObjectName("subtleBtn")
        self.importBtn.setFixedHeight(34)
        self.importBtn.clicked.connect(self._import)
        top.addWidget(self.importBtn)

        self.addBtn = QPushButton("＋  New Application")
        self.addBtn.setObjectName("accentBtn")
        self.addBtn.setFixedHeight(34)
        self.addBtn.clicked.connect(self._add)
        top.addWidget(self.addBtn)
        root.addLayout(top)

        # ── Search / filter bar ───────────────────────────────────────────────
        bar = QFrame(); bar.setObjectName("card")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 9, 14, 9); bar_lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search company, position, email…")
        self.search.textChanged.connect(self.refresh)
        bar_lay.addWidget(self.search, 3)

        self.statusFilter = QComboBox()
        self.statusFilter.addItems(["All Statuses", "pending", "sent", "replied", "interview", "rejected", "offer"])
        self.statusFilter.currentTextChanged.connect(self.refresh)
        bar_lay.addWidget(self.statusFilter, 1)
        root.addWidget(bar)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl_card = QFrame(); tbl_card.setObjectName("card")
        tbl_lay = QVBoxLayout(tbl_card)
        tbl_lay.setContentsMargins(0, 0, 0, 0); tbl_lay.setSpacing(0)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Company", "Position", "Contact Email", "Status", "Date", ""])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 84)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 84)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 120)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._on_double_click)
        tbl_lay.addWidget(self.table)
        root.addWidget(tbl_card, 1)

        self.countLabel = QLabel("")
        self.countLabel.setObjectName("pageSubtitle")
        root.addWidget(self.countLabel)

    def refresh(self):
        q  = self.search.text().strip()
        sf = self.statusFilter.currentText()

        conn = get_db()
        where, params = "WHERE 1=1", []
        if q:
            where += " AND (company LIKE ? OR position LIKE ? OR contact_email LIKE ?)"
            params += [f"%{q}%"] * 3
        if sf and sf != "All Statuses":
            where += " AND status=?"
            params.append(sf)

        rows = conn.execute(
            f"SELECT id,company,position,contact_email,status,created_at "
            f"FROM applications {where} ORDER BY created_at DESC LIMIT 500", params
        ).fetchall()
        conn.close()

        self._app_ids = []
        self.table.setRowCount(len(rows))
        for i, (app_id, co, pos, em, st, created) in enumerate(rows):
            self._app_ids.append(app_id)
            self.table.setRowHeight(i, 44)

            values = [co or "—", pos or "—", em or "—", st or "pending", (created or "")[:10]]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if j == 3:
                    fg, _ = STATUS_STYLE.get(v, ("#FFFFFF", ""))
                    item.setForeground(QColor(fg))
                self.table.setItem(i, j, item)

            # Action buttons — transparent container so table row shines through
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(6, 7, 6, 7); cl.setSpacing(4)

            for icon, tip, fn in [
                ("✉", "Compose email", lambda _, a=app_id: self.compose_requested.emit(a)),
                ("✎", "Edit entry",    lambda _, a=app_id: self._edit(a)),
                ("✕", "Delete",        lambda _, a=app_id: self._delete(a)),
            ]:
                b = QPushButton(icon)
                b.setFixedSize(30, 30)
                b.setToolTip(tip)
                b.setObjectName("dangerBtn" if icon == "✕" else "subtleBtn")
                b.clicked.connect(fn)
                cl.addWidget(b)

            self.table.setCellWidget(i, 5, cell)

        n = len(rows)
        self.countLabel.setText(f"{n} application{'s' if n != 1 else ''}  ·  double-click any row to edit")

    def _on_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._app_ids):
            self._edit(self._app_ids[row])

    def _add(self):
        dlg = ApplicationDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        d = dlg.get_data()
        if not d["company"]:
            QMessageBox.warning(self, "Required", "Company name is required."); return
        conn = get_db()
        conn.execute(
            "INSERT INTO applications (uuid,company,position,contact_email,contact_name,notes,status) VALUES (?,?,?,?,?,?,?)",
            (str(_uuid.uuid4()), d["company"], d["position"], d["contact_email"],
             d["contact_name"], d["notes"], d["status"])
        ); conn.commit(); conn.close()
        self.refresh()

    def _edit(self, app_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        conn.close()
        if not row: return
        dlg = ApplicationDialog(self, dict(row))
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        d = dlg.get_data()
        conn = get_db()
        conn.execute(
            "UPDATE applications SET company=?,position=?,contact_email=?,contact_name=?,notes=?,status=? WHERE id=?",
            (d["company"], d["position"], d["contact_email"], d["contact_name"],
             d["notes"], d["status"], app_id)
        ); conn.commit(); conn.close()
        self.refresh()

    def _delete(self, app_id):
        if QMessageBox.question(
            self, "Delete", "Delete this application and all its replies?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        conn = get_db()
        conn.execute("DELETE FROM replies WHERE application_id=?", (app_id,))
        conn.execute("DELETE FROM scheduled_emails WHERE application_id=?", (app_id,))
        conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
        conn.commit(); conn.close(); self.refresh()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Spreadsheets (*.xlsx *.xls *.csv)")
        if not path: return
        import os
        self.importBtn.setEnabled(False); self.importBtn.setText("Importing…")
        self._worker = ExcelImportWorker(path, os.path.basename(path))
        self._worker.done.connect(self._import_done)
        self._worker.start()

    def _import_done(self, result):
        self.importBtn.setEnabled(True); self.importBtn.setText("↑  Import Excel / CSV")
        if "error" in result:
            QMessageBox.critical(self, "Import Error", result["error"])
        else:
            QMessageBox.information(self, "Import Complete",
                f"Imported:          {result['imported']}\n"
                f"Duplicates skipped: {result['duplicates_skipped']}\n"
                f"Auto-UUIDs:        {result['new_uuid_generated']}")
        self.refresh()
