"""
Applications page — manages individual applications with AI bulk import.
"""
import uuid as _uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QTextEdit, QMessageBox,
    QFrame, QFileDialog, QDialogButtonBox, QProgressBar,
    QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor
from database import get_db
from ui.workers import ExcelImportWorker


_STATUS_COLORS = {
    "pending":   ("#9D5D00", "rgba(251,191,36,0.12)"),
    "sent":      ("#107C10", "rgba(16,124,16,0.10)"),
    "replied":   ("#107C10", "rgba(16,124,16,0.12)"),
    "rejected":  ("#C42B1C", "rgba(196,43,28,0.10)"),
    "offer":     ("#6E4FBE", "rgba(110,79,190,0.10)"),
    "interview": ("#0078D4", "rgba(0,120,212,0.10)"),
}


# ── AI extract worker ─────────────────────────────────────────────────────────

class _AIExtractWorker(QThread):
    found    = pyqtSignal(list)   # list of {company, email, name, org_type, context}
    error    = pyqtSignal(str)

    def __init__(self, text: str, intent: str):
        super().__init__()
        self.text   = text
        self.intent = intent
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            from modules.groq_client import chat
            prompt = (
                "Extract contact information from the following text. "
                "For each contact, identify: company/organisation name, email address, "
                "person name, type of organisation (startup/agency/enterprise/recruiter/other), "
                "and any useful context.\n\n"
                "Return ONLY a valid JSON array like:\n"
                '[{"company":"","email":"","name":"","org_type":"","context":""}]\n\n'
                f"User intent: {self.intent}\n\n"
                f"Text to parse:\n{self.text[:3000]}"
            )
            raw = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.1,
            )
            import json, re
            # Extract JSON array from response
            m = re.search(r'\[.*?\]', raw, re.DOTALL)
            if m:
                contacts = json.loads(m.group(0))
            else:
                contacts = json.loads(raw)
            self.found.emit(contacts if isinstance(contacts, list) else [])
        except Exception as e:
            self.error.emit(str(e))


# ── AI Import Dialog ──────────────────────────────────────────────────────────

class AIImportDialog(QDialog):
    """Paste emails/contact info → AI extracts → add as self-applications."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Bulk Import — Extract Contacts")
        self.setMinimumSize(740, 580)
        self._worker    = None
        self._contacts  = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QLabel("✦  AI Contact Extraction")
        hdr.setStyleSheet(
            "font-size:16px; font-weight:700; color:#1A1A1A; background:transparent;"
        )
        lay.addWidget(hdr)

        desc = QLabel(
            "Paste emails, LinkedIn messages, job board listings, or any text containing "
            "company/contact information. The AI will extract names, emails, and organisations."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:rgba(0,0,0,0.55); font-size:12px; background:transparent;")
        lay.addWidget(desc)

        # Intent row
        intent_row = QHBoxLayout()
        intent_row.addWidget(QLabel("Intent:"))
        self.intentEdit = QLineEdit()
        self.intentEdit.setPlaceholderText(
            "e.g. 'recruitment agencies for PM roles' or 'companies I want to apply to'"
        )
        intent_row.addWidget(self.intentEdit, 1)
        lay.addLayout(intent_row)

        # Text input
        self.textEdit = QTextEdit()
        self.textEdit.setMinimumHeight(160)
        self.textEdit.setPlaceholderText(
            "Paste email content, contact lists, LinkedIn messages, job postings…\n\n"
            "Example:\n"
            "From: Jane Smith <jane@acme.com>\n"
            "Subject: Hiring PM at Acme Corp\n\n"
            "Hi, we're looking for a Product Manager at Acme Corp…"
        )
        lay.addWidget(self.textEdit, 1)

        # Extract button
        btn_row = QHBoxLayout()
        self.extractBtn = QPushButton("✦  Extract Contacts with AI")
        self.extractBtn.setObjectName("accentBtn")
        self.extractBtn.setFixedHeight(36)
        self.extractBtn.clicked.connect(self._extract)
        btn_row.addWidget(self.extractBtn)
        self.statusLbl = QLabel("")
        self.statusLbl.setStyleSheet(
            "font-size:12px; color:rgba(0,0,0,0.5); background:transparent;"
        )
        btn_row.addWidget(self.statusLbl, 1)
        lay.addLayout(btn_row)

        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 0)
        self.progressBar.setFixedHeight(3)
        self.progressBar.setTextVisible(False)
        self.progressBar.setVisible(False)
        lay.addWidget(self.progressBar)

        # ── Review table ──────────────────────────────────────────────────────
        review_lbl = QLabel("EXTRACTED CONTACTS")
        review_lbl.setStyleSheet(
            "font-size:10px; font-weight:700; letter-spacing:1px; "
            "color:rgba(0,0,0,0.38); background:transparent;"
        )
        lay.addWidget(review_lbl)

        self.reviewTable = QTableWidget(0, 5)
        self.reviewTable.setHorizontalHeaderLabels(
            ["Include", "Company", "Email", "Name", "Type"]
        )
        h = self.reviewTable.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.reviewTable.setColumnWidth(0, 56)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.reviewTable.setColumnWidth(3, 130)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.reviewTable.setColumnWidth(4, 110)
        self.reviewTable.verticalHeader().setVisible(False)
        self.reviewTable.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.reviewTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.reviewTable.setStyleSheet(
            "QTableWidget { border: none; background: #FAFAFA; }"
            "QTableWidget::item { padding: 6px 10px; color: #1A1A1A; }"
            "QTableWidget::item:selected { background: rgba(0,103,192,0.10); }"
        )
        self.reviewTable.setFixedHeight(180)
        lay.addWidget(self.reviewTable)

        # ── Bottom buttons ────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.addStretch()
        self.addBtn = QPushButton("＋  Add Selected to Applications")
        self.addBtn.setObjectName("accentBtn")
        self.addBtn.setFixedHeight(36)
        self.addBtn.setEnabled(False)
        self.addBtn.clicked.connect(self._add_selected)
        btns.addWidget(self.addBtn)

        cancel = QPushButton("Close")
        cancel.setObjectName("subtleBtn")
        cancel.setFixedHeight(36)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        lay.addLayout(btns)

    def _extract(self):
        text = self.textEdit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty", "Please paste some text first.")
            return
        if self._worker:
            return

        try:
            from modules.groq_client import is_configured
            if not is_configured():
                QMessageBox.warning(
                    self, "Groq API Required",
                    "AI extraction requires a Groq API key.\nPlease add it in Settings.",
                )
                return
        except Exception:
            pass

        self.extractBtn.setEnabled(False)
        self.progressBar.setVisible(True)
        self.statusLbl.setText("Extracting contacts…")
        self.reviewTable.setRowCount(0)
        self.addBtn.setEnabled(False)

        self._worker = _AIExtractWorker(text, self.intentEdit.text())
        self._worker.found.connect(self._on_found)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.start()

    def _on_found(self, contacts: list):
        self.extractBtn.setEnabled(True)
        self.progressBar.setVisible(False)
        self._contacts = contacts

        if not contacts:
            self.statusLbl.setText("No contacts found. Try rephrasing or adding more context.")
            return

        self.statusLbl.setText(f"Found {len(contacts)} contact(s) — review and edit below")
        self.reviewTable.setRowCount(len(contacts))

        for i, c in enumerate(contacts):
            self.reviewTable.setRowHeight(i, 36)

            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            self.reviewTable.setItem(i, 0, chk)

            for j, val in enumerate([
                c.get("company", ""),
                c.get("email", ""),
                c.get("name", ""),
                c.get("org_type", ""),
            ]):
                item = QTableWidgetItem(val)
                self.reviewTable.setItem(i, j + 1, item)

        self.addBtn.setEnabled(True)

    def _on_error(self, msg: str):
        self.extractBtn.setEnabled(True)
        self.progressBar.setVisible(False)
        self.statusLbl.setText(f"Error: {msg[:80]}")

    def _add_selected(self):
        added = 0
        conn = get_db()
        for i in range(self.reviewTable.rowCount()):
            chk = self.reviewTable.item(i, 0)
            if not chk or chk.checkState() != Qt.CheckState.Checked:
                continue

            def cell(col):
                item = self.reviewTable.item(i, col)
                return item.text().strip() if item else ""

            company = cell(1)
            email   = cell(2)
            name    = cell(3)
            notes   = f"org_type: {cell(4)}"

            if not company:
                continue

            # Check if already exists
            existing = conn.execute(
                "SELECT id FROM applications WHERE company=? AND (contact_email=? OR contact_email IS NULL)",
                (company, email),
            ).fetchone()
            if existing:
                continue

            conn.execute(
                "INSERT INTO applications "
                "(uuid, company, contact_email, contact_name, notes, status, source_file) "
                "VALUES (?, ?, ?, ?, ?, 'pending', 'ai_import')",
                (str(_uuid.uuid4()), company, email or None, name or None, notes),
            )
            added += 1

        conn.commit()
        conn.close()

        if added:
            QMessageBox.information(
                self, "Added",
                f"Added {added} new application(s) to your list.\n"
                "Find them in the Applications tab with status 'pending'.",
            )
            self.accept()
        else:
            QMessageBox.information(
                self, "Nothing New",
                "All selected contacts already exist in your applications.",
            )


# ── Edit dialog ───────────────────────────────────────────────────────────────

class ApplicationDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("Edit Application" if data else "New Application")
        self.setMinimumWidth(520)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 24, 24, 20)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def f(ph):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            return e

        self.company  = f("e.g. Acme Corp")
        self.position = f("Leave blank to use growth-focused outreach")
        self.email    = f("hr@acme.com")
        self.contact  = f("Jane Smith")
        self.status   = QComboBox()
        self.status.addItems(
            ["pending", "sent", "replied", "interview", "rejected", "offer"]
        )
        self.notes = QTextEdit()
        self.notes.setPlaceholderText(
            "Referral info, company description, how you found this…"
        )
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
            if idx >= 0:
                self.status.setCurrentIndex(idx)
            self.notes.setPlainText(self.data.get("notes", "") or "")

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
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


# ── Applications page ─────────────────────────────────────────────────────────

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
        top = QHBoxLayout()
        top.setSpacing(10)
        t = QLabel("Applications")
        t.setObjectName("pageTitle")
        top.addWidget(t)
        top.addStretch()

        self.importBtn = QPushButton("↑  Import Excel / CSV")
        self.importBtn.setObjectName("subtleBtn")
        self.importBtn.setFixedHeight(34)
        self.importBtn.clicked.connect(self._import)
        top.addWidget(self.importBtn)

        self.aiImportBtn = QPushButton("✦  AI Import")
        self.aiImportBtn.setObjectName("subtleBtn")
        self.aiImportBtn.setFixedHeight(34)
        self.aiImportBtn.setToolTip(
            "Paste emails, contact lists, or any text.\n"
            "AI will extract company names and emails."
        )
        self.aiImportBtn.clicked.connect(self._ai_import)
        top.addWidget(self.aiImportBtn)

        self.addBtn = QPushButton("＋  New Application")
        self.addBtn.setObjectName("accentBtn")
        self.addBtn.setFixedHeight(34)
        self.addBtn.clicked.connect(self._add)
        top.addWidget(self.addBtn)
        root.addLayout(top)

        # ── Search / filter bar ───────────────────────────────────────────────
        bar = QFrame()
        bar.setObjectName("card")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 9, 14, 9)
        bar_lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search company, position, email…")
        self.search.textChanged.connect(self.refresh)
        bar_lay.addWidget(self.search, 3)

        self.statusFilter = QComboBox()
        self.statusFilter.addItems(
            ["All Statuses", "pending", "sent", "replied", "interview", "rejected", "offer"]
        )
        self.statusFilter.currentTextChanged.connect(self.refresh)
        bar_lay.addWidget(self.statusFilter, 1)
        root.addWidget(bar)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl_card = QFrame()
        tbl_card.setObjectName("card")
        tbl_lay = QVBoxLayout(tbl_card)
        tbl_lay.setContentsMargins(0, 0, 0, 0)
        tbl_lay.setSpacing(0)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Company", "Position", "Contact Email", "Status", "Date", ""]
        )
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
            f"FROM applications {where} ORDER BY created_at DESC LIMIT 500",
            params,
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
                    fg, bg = _STATUS_COLORS.get(v, ("#1A1A1A", "transparent"))
                    item.setForeground(QColor(fg))
                    item.setBackground(QColor(bg))
                self.table.setItem(i, j, item)

            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(6, 7, 6, 7)
            cl.setSpacing(4)

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
        self.countLabel.setText(
            f"{n} application{'s' if n != 1 else ''}  ·  double-click to edit"
        )

    def _on_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._app_ids):
            self._edit(self._app_ids[row])

    def _ai_import(self):
        dlg = AIImportDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _add(self):
        dlg = ApplicationDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["company"]:
            QMessageBox.warning(self, "Required", "Company name is required.")
            return
        conn = get_db()
        conn.execute(
            "INSERT INTO applications (uuid,company,position,contact_email,contact_name,notes,status) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(_uuid.uuid4()), d["company"], d["position"], d["contact_email"],
             d["contact_name"], d["notes"], d["status"]),
        )
        conn.commit()
        conn.close()
        self.refresh()

    def _edit(self, app_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        conn.close()
        if not row:
            return
        dlg = ApplicationDialog(self, dict(row))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        conn = get_db()
        conn.execute(
            "UPDATE applications SET company=?,position=?,contact_email=?,contact_name=?,notes=?,status=? WHERE id=?",
            (d["company"], d["position"], d["contact_email"], d["contact_name"],
             d["notes"], d["status"], app_id),
        )
        conn.commit()
        conn.close()
        self.refresh()

    def _delete(self, app_id):
        if QMessageBox.question(
            self, "Delete", "Delete this application and all its replies?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        conn = get_db()
        conn.execute("DELETE FROM replies WHERE application_id=?", (app_id,))
        conn.execute("DELETE FROM scheduled_emails WHERE application_id=?", (app_id,))
        conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
        conn.commit()
        conn.close()
        self.refresh()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", "Spreadsheets (*.xlsx *.xls *.csv)"
        )
        if not path:
            return
        import os
        self.importBtn.setEnabled(False)
        self.importBtn.setText("Importing…")
        self._worker = ExcelImportWorker(path, os.path.basename(path))
        self._worker.done.connect(self._import_done)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.start()

    def _import_done(self, result):
        self.importBtn.setEnabled(True)
        self.importBtn.setText("↑  Import Excel / CSV")
        if "error" in result:
            QMessageBox.critical(self, "Import Error", result["error"])
        else:
            QMessageBox.information(
                self, "Import Complete",
                f"Imported:           {result['imported']}\n"
                f"Duplicates skipped: {result['duplicates_skipped']}\n"
                f"Auto-UUIDs:         {result['new_uuid_generated']}",
            )
        self.refresh()
