"""
Background QThread workers.
Rules:
  - Custom signal named 'result' or 'done' (never 'finished') to avoid
    shadowing QThread.finished, which we connect to deleteLater() for
    safe cleanup.
  - Caller must keep a strong reference (self._worker = ...) until done.
"""

from PyQt6.QtCore import QThread, pyqtSignal


def _connect_cleanup(worker):
    """Connect QThread's own finished to deleteLater — safe teardown."""
    worker.finished.connect(worker.deleteLater)


class LLMLoaderWorker(QThread):
    done = pyqtSignal(bool, str)   # success, message

    def __init__(self, model_path, n_ctx=4096, n_gpu_layers=35):
        super().__init__()
        self.model_path    = model_path
        self.n_ctx         = n_ctx
        self.n_gpu_layers  = n_gpu_layers
        _connect_cleanup(self)

    def run(self):
        try:
            from llama_cpp import Llama
            import modules.llm_summarizer as ls
            ls._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
            )
            self.done.emit(True, "Model loaded")
        except Exception as e:
            self.done.emit(False, str(e))


class LLMInferenceWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt, max_tokens=512, temperature=0.7):
        super().__init__()
        self.prompt      = prompt
        self.max_tokens  = max_tokens
        self.temperature = temperature
        _connect_cleanup(self)

    def run(self):
        try:
            import modules.llm_summarizer as ls
            llm = ls._get_llm()
            if llm is None:
                self.error.emit("No model loaded — go to Settings and load the model.")
                return
            output = llm(
                self.prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stop=["[INST]", "[/INST]", "\nUser:", "\nHuman:"],
            )
            self.done.emit(output["choices"][0]["text"].strip())
        except Exception as e:
            self.error.emit(str(e))


class EmailSyncWorker(QThread):
    done = pyqtSignal(int, list)   # new_count, errors

    def __init__(self):
        super().__init__()
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.email_monitor import sync_replies
            r = sync_replies()
            self.done.emit(r.get("new_replies", 0), r.get("errors", []))
        except Exception as e:
            self.done.emit(0, [str(e)])


class BulkSendWorker(QThread):
    progress = pyqtSignal(int, str, str)   # app_id, company, status
    done     = pyqtSignal(dict)

    def __init__(self, app_ids, sleep_seconds=10, dry_run=False,
                 send_to_careers=True, sender_mode="apple_mail",
                 apple_mail_account=""):
        super().__init__()
        self.app_ids            = app_ids
        self.sleep_seconds      = sleep_seconds
        self.dry_run            = dry_run
        self.send_to_careers    = send_to_careers
        self.sender_mode        = sender_mode
        self.apple_mail_account = apple_mail_account
        _connect_cleanup(self)

    def run(self):
        from modules.apple_mail_sender import run_bulk_campaign
        result = run_bulk_campaign(
            application_ids=self.app_ids,
            sleep_seconds=self.sleep_seconds,
            dry_run=self.dry_run,
            send_to_careers=self.send_to_careers,
            sender_mode=self.sender_mode,
            apple_mail_account=self.apple_mail_account,
            progress_callback=lambda aid, co, st: self.progress.emit(aid, co, st),
        )
        self.done.emit(result)


class MailFetchWorker(QThread):
    """Fetch inbox message list via IMAP."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, folder: str = "INBOX", limit: int = 60):
        super().__init__()
        self.folder = folder
        self.limit  = limit
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.mail_client import fetch_messages
            self.done.emit(fetch_messages(self.folder, self.limit))
        except Exception as e:
            self.error.emit(str(e))


class MailBodyWorker(QThread):
    """Fetch a single message body via IMAP."""
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, uid: str, folder: str = "INBOX"):
        super().__init__()
        self.uid    = uid
        self.folder = folder
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.mail_client import fetch_body
            self.done.emit(fetch_body(self.uid, self.folder))
        except Exception as e:
            self.error.emit(str(e))


class MailSendWorker(QThread):
    """Send an email via SMTP."""
    done  = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, to_emails: list, subject: str, body: str,
                 attachment_path: str = None, tracking_key: str = ""):
        super().__init__()
        self.to_emails       = to_emails
        self.subject         = subject
        self.body            = body
        self.attachment_path = attachment_path
        self.tracking_key    = tracking_key
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.mail_client import send_email
            send_email(self.to_emails, self.subject, self.body,
                       self.attachment_path, self.tracking_key)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class MsGraphAuthWorker(QThread):
    """Runs the blocking acquire_token_by_device_flow() call in a background thread."""
    done  = pyqtSignal(str)   # signed-in email on success
    error = pyqtSignal(str)   # error message

    def __init__(self, flow: dict):
        super().__init__()
        self.flow = flow
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.ms_graph import complete_device_flow
            email = complete_device_flow(self.flow)
            self.done.emit(email)
        except Exception as e:
            self.error.emit(str(e))


class OAuthWorker(QThread):
    """
    Browser-based OAuth2 Authorization Code flow.
    Opens the user's browser, spins up a local server on port 8741 to catch the
    redirect, exchanges the code for tokens, and stores them on disk.
    """
    done  = pyqtSignal(str)   # connected email
    error = pyqtSignal(str)

    def __init__(self, provider: str, client_id: str = ""):
        super().__init__()
        self.provider  = provider   # "google" | "microsoft"
        self.client_id = client_id  # only needed for microsoft
        _connect_cleanup(self)

    def run(self):
        try:
            if self.provider == "google":
                from modules.oauth_manager import google_connect
                email = google_connect()    # uses bundled credentials
            else:
                from modules.oauth_manager import ms_connect
                email = ms_connect(self.client_id)
            self.done.emit(email)
        except Exception as e:
            self.error.emit(str(e))


class DraftRegenWorker(QThread):
    """Regenerate an AI reply draft for a specific inbox_index row."""
    done  = pyqtSignal(int, str)    # row_id, draft_text
    error = pyqtSignal(int, str)    # row_id, error_message

    def __init__(self, row_id: int):
        super().__init__()
        self.row_id = row_id
        _connect_cleanup(self)

    def run(self):
        from database import get_db
        conn = get_db()
        row = conn.execute('''
            SELECT i.id, i.body, i.application_id,
                   a.email_subject, a.email_body, a.company, a.position
            FROM inbox_index i
            LEFT JOIN applications a ON i.application_id = a.id
            WHERE i.id = ?
        ''', (self.row_id,)).fetchone()
        conn.close()

        if not row:
            self.error.emit(self.row_id, "Record not found.")
            return

        try:
            from modules.llm_auto_reply import generate_reply_draft, get_fallback_draft
            draft = generate_reply_draft(
                reply_body=row["body"] or "",
                original_subject=row["email_subject"] or "",
                original_body=row["email_body"] or "",
                company_name=row["company"] or "",
                position=row["position"] or "",
            )
            if draft is None:
                # LLM still not loaded — return a polished template
                draft = get_fallback_draft(row["company"] or "the company", row["position"] or "")

            # Persist updated draft
            conn2 = get_db()
            conn2.execute("UPDATE inbox_index SET ai_reply_draft=? WHERE id=?", (draft, self.row_id))
            conn2.commit()
            conn2.close()
            self.done.emit(self.row_id, draft)
        except Exception as e:
            self.error.emit(self.row_id, str(e))


# ResumeWorker and ResumeExportWorker moved to resume_builder/workers.py
from resume_builder.workers import ResumeWorker, ResumeExportWorker  # noqa: F401


class ExcelImportWorker(QThread):
    done = pyqtSignal(dict)

    def __init__(self, filepath, filename):
        super().__init__()
        self.filepath = filepath
        self.filename = filename
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.excel_processor import process_excel
            self.done.emit(process_excel(self.filepath, self.filename))
        except Exception as e:
            self.done.emit({"error": str(e), "imported": 0,
                            "duplicates_skipped": 0, "new_uuid_generated": 0})


class InboxIndexWorker(QThread):
    done = pyqtSignal(dict)   # {"indexed": int, "tkey_matches": int, "errors": list}

    def __init__(self):
        super().__init__()
        _connect_cleanup(self)

    def run(self):
        try:
            from modules.email_monitor import index_all_inbox
            self.done.emit(index_all_inbox())
        except Exception as e:
            self.done.emit({"indexed": 0, "tkey_matches": 0, "errors": [str(e)]})
