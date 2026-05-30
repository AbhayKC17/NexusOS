"""Resume Builder page — paste JD, generate tailored content via Groq AI, export PDF."""

import os
import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QScrollArea, QFrame, QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QTimer

from database import get_setting, set_setting


class ResumePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker        = None
        self._export_worker = None
        self._company_timer = QTimer(self)
        self._company_timer.setSingleShot(True)
        self._company_timer.setInterval(600)   # debounce JD typing
        self._company_timer.timeout.connect(self._auto_extract_company)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QWidget()
        bl   = QHBoxLayout(body)
        bl.setContentsMargins(24, 16, 24, 0)
        bl.setSpacing(16)
        bl.addWidget(self._build_left(),  1)
        bl.addWidget(self._build_right(), 2)
        root.addWidget(body, 1)

        root.addWidget(self._build_bottom())

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("pageHeader")
        hl  = QVBoxLayout(hdr)
        hl.setContentsMargins(28, 22, 28, 16)
        hl.setSpacing(4)
        title = QLabel("Resume Builder")
        title.setObjectName("pageTitle")
        sub   = QLabel("Paste a job description → AI tailors your resume → export PDF")
        sub.setObjectName("pageSubtitle")
        hl.addWidget(title)
        hl.addWidget(sub)
        return hdr

    def _build_left(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay  = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl = QLabel("Job Description")
        lbl.setObjectName("sectionHeader")
        lay.addWidget(lbl)

        self.jdEdit = QTextEdit()
        self.jdEdit.setPlaceholderText(
            "Paste the full job description here…\n\n"
            "Company name is auto-detected from the JD."
        )
        self.jdEdit.textChanged.connect(lambda: self._company_timer.start())
        lay.addWidget(self.jdEdit, 1)

        self.generateBtn = QPushButton("✦  Generate (Groq AI)")
        self.generateBtn.setObjectName("accentBtn")
        self.generateBtn.setFixedHeight(38)
        self.generateBtn.clicked.connect(self._generate)
        lay.addWidget(self.generateBtn)

        self.statusLbl = QLabel("")
        self.statusLbl.setWordWrap(True)
        self.statusLbl.setStyleSheet(
            "color: rgba(0,0,0,0.5); background: transparent; font-size: 12px;"
        )
        lay.addWidget(self.statusLbl)

        return card

    def _build_right(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 8, 16)
        lay.setSpacing(8)

        # Salary
        salaryRow = QHBoxLayout()
        salaryRow.setSpacing(10)
        salaryRow.addWidget(self._field_label("Salary Expectation"))
        self.salaryLbl = QLabel("—")
        self.salaryLbl.setStyleSheet(
            "color: #6CCB5F; background: rgba(108,203,95,0.08); "
            "border: 1px solid rgba(108,203,95,0.3); border-radius: 6px; "
            "padding: 4px 12px; font-size: 13px; font-weight: 600;"
        )
        self.salaryLbl.setWordWrap(True)
        salaryRow.addWidget(self.salaryLbl, 1)
        lay.addLayout(salaryRow)

        # Professional Summary
        lay.addWidget(self._field_label("Professional Summary (30–32 words)"))
        self.summaryEdit = QTextEdit()
        self.summaryEdit.setPlaceholderText("Generated summary will appear here…")
        self.summaryEdit.setFixedHeight(76)
        self.summaryEdit.textChanged.connect(self._update_char_count)
        lay.addWidget(self.summaryEdit)

        self.charCountLbl = QLabel("0 words / target 30–32 words")
        self.charCountLbl.setStyleSheet(
            "color: rgba(0,0,0,0.42); background: transparent; font-size: 11px;"
        )
        lay.addWidget(self.charCountLbl)

        # Work experience bullets — 3 companies (matching PDF template slots)
        for attr, label, height in [
            ("projectsEdit", "Infyair — 4 bullets",  108),
            ("ecolabEdit",   "Ecolab — 4 bullets",   108),
            ("mscEdit",      "MSC — 3 bullets",        90),
        ]:
            lay.addWidget(self._field_label(label))
            edit = QTextEdit()
            edit.setPlaceholderText("Generated bullets will appear here…")
            edit.setFixedHeight(height)
            setattr(self, attr, edit)
            lay.addWidget(edit)

        # Skills
        lay.addWidget(self._field_label("IT & Skills"))
        self.skillsEdit = QTextEdit()
        self.skillsEdit.setPlaceholderText("Generated skills will appear here…")
        self.skillsEdit.setFixedHeight(130)
        lay.addWidget(self.skillsEdit)

        # Raw LLM output — collapsed by default, visible if parsing fails
        self.rawLbl = self._field_label("Raw LLM Output (full generated text)")
        self.rawLbl.setVisible(False)
        lay.addWidget(self.rawLbl)
        self.rawEdit = QTextEdit()
        self.rawEdit.setReadOnly(True)
        self.rawEdit.setFixedHeight(200)
        self.rawEdit.setPlaceholderText("Full LLM output will appear here if content was not parsed…")
        self.rawEdit.setVisible(False)
        lay.addWidget(self.rawEdit)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_bottom(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { border-top: 1px solid rgba(255,255,255,0.06); background: transparent; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 12, 24, 16)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Company name:"))
        self.companyEdit = QLineEdit()
        self.companyEdit.setPlaceholderText("Auto-detected — or type manually")
        self.companyEdit.setFixedWidth(220)
        lay.addWidget(self.companyEdit)

        lay.addStretch()

        self.docxPathBtn = QPushButton("Select Resume PDF…")
        self.docxPathBtn.setObjectName("subtleBtn")
        self.docxPathBtn.clicked.connect(self._pick_resume)
        lay.addWidget(self.docxPathBtn)

        self.exportBtn = QPushButton("Apply to Resume  +  Export PDF")
        self.exportBtn.setObjectName("accentBtn")
        self.exportBtn.setFixedHeight(36)
        self.exportBtn.clicked.connect(self._export)
        lay.addWidget(self.exportBtn)

        return bar

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: rgba(0,0,0,0.55); background: transparent; font-size: 12px;"
        )
        return lbl

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _auto_extract_company(self):
        """Debounced — fires 600 ms after user stops typing in the JD box."""
        jd = self.jdEdit.toPlainText().strip()
        if not jd:
            return
        try:
            from resume_builder.generator import extract_company_from_jd
            name = extract_company_from_jd(jd)
            if name:
                self.companyEdit.setText(name)
        except Exception:
            pass

    def _update_char_count(self):
        text  = self.summaryEdit.toPlainText().strip()
        n     = len(text.split()) if text else 0
        color = (
            "#6CCB5F" if 30 <= n <= 32          # green  — perfect range
            else "#FCE100" if 27 <= n <= 35     # yellow — close
            else "rgba(255,255,255,0.35)"       # dim    — out of range
        )
        self.charCountLbl.setText(f"{n} words / target 30–32 words")
        self.charCountLbl.setStyleSheet(
            f"color: {color}; background: transparent; font-size: 11px;"
        )

    def _generate(self):
        jd = self.jdEdit.toPlainText().strip()
        if not jd:
            QMessageBox.warning(self, "Empty", "Paste a job description first.")
            return

        self.generateBtn.setEnabled(False)
        self.generateBtn.setText("Generating…")
        self.statusLbl.setText("Calling Groq API — usually under 10 seconds…")

        from resume_builder.workers import ResumeWorker
        self._worker = ResumeWorker(jd)
        self._worker.done.connect(self._on_generated)
        self._worker.error.connect(self._on_gen_error)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.start()

    def _on_generated(self, data: dict):
        self.generateBtn.setEnabled(True)
        self.generateBtn.setText("✦  Generate (Groq AI)")

        salary = data.get("salary", "")
        self.salaryLbl.setText(salary if salary else "—")

        self.summaryEdit.setPlainText(data.get("summary", ""))

        def fmt(lst):
            return "\n".join(lst)

        proj   = data["bullets"].get("projects", [])
        ecolab = data["bullets"].get("ecolab", [])
        msc    = data["bullets"].get("msc", [])

        self.projectsEdit.setPlainText(fmt(proj))
        self.ecolabEdit.setPlainText(fmt(ecolab))
        self.mscEdit.setPlainText(fmt(msc))
        self.skillsEdit.setPlainText(data.get("skills", ""))

        raw = data.get("raw", "")
        self.rawEdit.setPlainText(raw)
        any_parsed = bool(data.get("summary") or proj or ecolab or msc)
        self.rawLbl.setVisible(True)
        self.rawEdit.setVisible(True)

        if not any_parsed:
            msg = "Parsing failed — check Raw LLM Output below and paste content manually."
        else:
            msg = f"Generated ({len(proj)}+{len(ecolab)}+{len(msc)} bullets). Review and export."
        self.statusLbl.setText(msg)

        self._auto_extract_company()

    def _on_gen_error(self, err: str):
        self.generateBtn.setEnabled(True)
        self.generateBtn.setText("✦  Generate (Groq AI)")
        self.statusLbl.setText(f"Error: {err[:150]}")
        QMessageBox.critical(self, "Generation Error", err)

    def _pick_resume(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Resume Template", os.path.expanduser("~/Desktop"),
            "Resume Templates (*.pdf *.docx);;PDF files (*.pdf);;Word Documents (*.docx)"
        )
        if path:
            set_setting("resume_path", path)
            self.docxPathBtn.setText(os.path.basename(path))

    def _export(self):
        company = self.companyEdit.text().strip()
        if not company:
            QMessageBox.warning(self, "Company Name",
                                "Enter or confirm the company name for the filename.")
            return

        resume_path = get_setting("resume_path", "")
        if not resume_path or not os.path.isfile(resume_path):
            QMessageBox.warning(
                self, "Resume Template Not Found",
                "Click 'Select Resume PDF…' to choose your Abhay_Resume.pdf file."
            )
            return

        def parse_bullets(text: str) -> list:
            result = []
            for line in text.strip().split("\n"):
                clean = line.strip().lstrip("•–-* ").strip()
                if clean:
                    result.append(clean)
            return result

        resume_data = {
            "summary": self.summaryEdit.toPlainText().strip(),
            "bullets": {
                "projects": parse_bullets(self.projectsEdit.toPlainText()),
                "ecolab":   parse_bullets(self.ecolabEdit.toPlainText()),
                "msc":      parse_bullets(self.mscEdit.toPlainText()),
            },
            "skills": self.skillsEdit.toPlainText().strip(),
        }

        safe    = re.sub(r'[^\w\-]', '_', company.lower()).strip('_')
        desktop = os.path.expanduser("~/Desktop")

        is_pdf = resume_path.lower().endswith(".pdf")
        if is_pdf:
            out_path = os.path.join(desktop, f"abhay_resume_{safe}.pdf")
            status_msg = "Editing PDF directly — preserving exact template…"
        else:
            out_path = os.path.join(desktop, f"abhay_resume_{safe}.docx")
            status_msg = "Applying content to DOCX and converting to PDF…"

        self.exportBtn.setEnabled(False)
        self.exportBtn.setText("Exporting…")
        self.statusLbl.setText(status_msg)

        from resume_builder.workers import ResumeExportWorker
        self._export_worker = ResumeExportWorker(
            resume_data, resume_path, out_path, None if is_pdf else desktop
        )
        self._export_worker.done.connect(self._on_exported)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.finished.connect(lambda: setattr(self, "_export_worker", None))
        self._export_worker.start()

    def _on_exported(self, pdf_path: str):
        self.exportBtn.setEnabled(True)
        self.exportBtn.setText("Apply to Resume  +  Export PDF")
        self.statusLbl.setText(f"Saved: {pdf_path}")
        QMessageBox.information(self, "Exported", f"PDF saved to:\n{pdf_path}")

    def _on_export_error(self, err: str):
        self.exportBtn.setEnabled(True)
        self.exportBtn.setText("Apply to Resume  +  Export PDF")
        self.statusLbl.setText(f"Export error: {err[:150]}")
        QMessageBox.critical(self, "Export Error", err)

    # resume_builder/page.py is 3 levels deep: resume_builder/ → JobTracker/ → Todays Folder/
    _DEFAULT_PDF = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "Abhay_Resume.pdf"
    )

    def refresh(self):
        resume_path = get_setting("resume_path", "")

        # Always prefer the PDF template if it exists.
        if os.path.isfile(self._DEFAULT_PDF):
            if not resume_path or not resume_path.lower().endswith(".pdf") or not os.path.isfile(resume_path):
                resume_path = self._DEFAULT_PDF
                set_setting("resume_path", resume_path)

        if resume_path and os.path.isfile(resume_path):
            self.docxPathBtn.setText(os.path.basename(resume_path))
        else:
            self.docxPathBtn.setText("Select Resume PDF…")
