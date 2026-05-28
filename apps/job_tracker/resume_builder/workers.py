"""Resume QThread workers — generate content via Groq and export to PDF/DOCX."""

from PyQt6.QtCore import QThread, pyqtSignal


def _connect_cleanup(worker):
    worker.finished.connect(worker.deleteLater)


class ResumeWorker(QThread):
    """Generate tailored resume content via Groq API."""
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, job_description: str):
        super().__init__()
        self.job_description = job_description
        _connect_cleanup(self)

    def run(self):
        try:
            from resume_builder.generator import generate_resume_content, parse_llm_output
            raw  = generate_resume_content(self.job_description)
            data = parse_llm_output(raw)
            self.done.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class ResumeExportWorker(QThread):
    """Apply resume_data to a PDF or DOCX template and export PDF."""
    done  = pyqtSignal(str)   # pdf_path
    error = pyqtSignal(str)

    def __init__(self, resume_data: dict, template_path: str,
                 out_path: str, pdf_dir: str = None):
        super().__init__()
        self.resume_data   = resume_data
        self.template_path = template_path
        self.out_path      = out_path
        self.pdf_dir       = pdf_dir
        _connect_cleanup(self)

    def run(self):
        try:
            if self.template_path.lower().endswith(".pdf"):
                from resume_builder.generator import apply_to_pdf
                pdf_path = apply_to_pdf(self.resume_data, self.template_path, self.out_path)
            else:
                from resume_builder.generator import apply_to_docx, export_pdf
                apply_to_docx(self.resume_data, self.template_path, self.out_path)
                pdf_path = export_pdf(self.out_path, self.pdf_dir)
            self.done.emit(pdf_path)
        except Exception as e:
            self.error.emit(str(e))
