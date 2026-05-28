"""
Built-in email client — pure Python SMTP + IMAP.
No Apple Mail, no Outlook, no AppleScript, no Azure.

Send:  smtplib (SMTP with STARTTLS or SSL)
Read:  imaplib (IMAP4 with SSL)

Credentials come from Settings → SMTP / IMAP fields.
For Microsoft accounts: use an App Password (see Settings → Guide).
For Gmail: use an App Password (Google Account → Security → App passwords).
"""

import email
import imaplib
import os
import smtplib
import time
from email import encoders
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from database import get_setting


def _smtp_cfg() -> dict:
    return {
        "host": get_setting("smtp_host", ""),
        "port": int(get_setting("smtp_port", 587) or 587),
        "user": get_setting("smtp_user", ""),
        "pass": get_setting("smtp_pass", ""),
        "tls":  get_setting("smtp_tls", "true") == "true",
        "name": get_setting("from_name", "") or get_setting("sender_name", ""),
    }


def _imap_cfg() -> dict:
    return {
        "host": get_setting("imap_host", ""),
        "port": int(get_setting("imap_port", 993) or 993),
        "user": get_setting("imap_user", ""),
        "pass": get_setting("imap_pass", ""),
    }


def _decode_str(s) -> str:
    if s is None:
        return ""
    result = ""
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += str(part)
    return result


def _get_body(msg) -> str:
    """Extract plain text body, falling back to stripped HTML."""
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct  = part.get_content_type()
            cd  = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain":
                plain += text
            elif ct == "text/html":
                html += text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            plain = payload.decode(charset, errors="replace")

    if plain.strip():
        return plain.strip()
    # Strip HTML tags as fallback
    import re
    return re.sub(r"<[^>]+>", " ", html).strip()


def _xoauth2_raw(user_email: str, access_token: str) -> str:
    """Raw (unencoded) XOAUTH2 string.
    smtplib.auth() and imaplib.authenticate() both base64-encode internally,
    so we must NOT pre-encode here — doing so causes a 501 double-encode error."""
    return f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"


def _oauth_smtp_creds():
    """
    Returns (smtp_host, smtp_port, user_email, raw_xoauth2) when an OAuth account
    is connected, otherwise None.  Google is checked before Microsoft.
    """
    try:
        from modules.oauth_manager import is_google_connected, get_google_token, google_email
        if is_google_connected():
            user  = google_email()
            token = get_google_token()
            return "smtp.gmail.com", 587, user, _xoauth2_raw(user, token)
    except Exception:
        pass
    try:
        from modules.oauth_manager import is_ms_connected, get_ms_token, ms_email
        if is_ms_connected():
            user  = ms_email()
            token = get_ms_token()
            return "smtp.office365.com", 587, user, _xoauth2_raw(user, token)
    except Exception:
        pass
    return None


def _oauth_imap_creds():
    """
    Returns (imap_host, imap_port, user_email, raw_xoauth2) when an OAuth account
    is connected, otherwise None.
    """
    try:
        from modules.oauth_manager import is_google_connected, get_google_token, google_email
        if is_google_connected():
            user  = google_email()
            token = get_google_token()
            return "imap.gmail.com", 993, user, _xoauth2_raw(user, token)
    except Exception:
        pass
    try:
        from modules.oauth_manager import is_ms_connected, get_ms_token, ms_email
        if is_ms_connected():
            user  = ms_email()
            token = get_ms_token()
            return "outlook.office365.com", 993, user, _xoauth2_raw(user, token)
    except Exception:
        pass
    return None


def is_configured() -> dict:
    """Return {"smtp": bool, "imap": bool} indicating which services are ready."""
    if _oauth_smtp_creds():
        smtp_ok = True
    else:
        s = _smtp_cfg()
        smtp_ok = bool(s["host"] and s["user"] and s["pass"])

    if _oauth_imap_creds():
        imap_ok = True
    else:
        i = _imap_cfg()
        imap_ok = bool(i["host"] and i["user"] and i["pass"])

    return {"smtp": smtp_ok, "imap": imap_ok}


# ── SMTP sending ──────────────────────────────────────────────────────────────

def build_html_body(plain_body: str, tracking_key: str = "") -> str:
    """Convert plain text to HTML with optional invisible TKEY span."""
    import html as _html_mod
    escaped = _html_mod.escape(plain_body)
    paragraphs = escaped.split("\n\n")
    html_paras = "".join(
        f"<p style='margin:0 0 14px 0;line-height:1.7'>{p.replace(chr(10), '<br>')}</p>"
        for p in paragraphs
    )
    ghost = (
        f'<span style="font-size:1px;color:#FEFEFE;line-height:0;'
        f'display:inline;user-select:none;opacity:0.01">'
        f'TKEY:{tracking_key}</span>'
    ) if tracking_key else ""
    return (
        "<html><head><meta charset='utf-8'></head>"
        "<body style='font-family:Arial,Helvetica,sans-serif;font-size:14px;"
        "color:#1a1a1a;max-width:600px;padding:20px'>"
        f"{html_paras}{ghost}"
        "</body></html>"
    )


def _build_mime(from_addr, valid_to, subject, body, html_body, attachment_path):
    msg = MIMEMultipart("mixed")
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(valid_to)
    msg["Subject"] = subject
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)
    if attachment_path and os.path.isfile(attachment_path):
        with open(attachment_path, "rb") as fh:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(attachment_path)}"',
        )
        msg.attach(part)
    return msg


def send_email(
    to_emails: list,
    subject: str,
    body: str,
    attachment_path: str = None,
    tracking_key: str = "",
    html_body: str = None,
) -> None:
    """
    Send email via SMTP.
    Uses OAuth2 / XOAUTH2 when a Google or Microsoft account is connected;
    falls back to password SMTP if not.
    """
    if html_body is None:
        html_body = build_html_body(body, tracking_key)

    valid_to = [e for e in to_emails if e and "@" in e]
    if not valid_to:
        raise ValueError("No valid recipient email addresses.")

    sender_name = get_setting("from_name", "") or get_setting("sender_name", "")

    # ── OAuth path ────────────────────────────────────────────────────────────
    oauth = _oauth_smtp_creds()
    if oauth:
        smtp_host, smtp_port, user_email, raw_xoauth2 = oauth
        from_addr = f"{sender_name} <{user_email}>" if sender_name else user_email
        msg = _build_mime(from_addr, valid_to, subject, body, html_body, attachment_path)
        # Use docmd directly — smtplib.auth() would double-base64-encode (→ 501 error)
        import base64 as _b64
        auth_str = _b64.b64encode(raw_xoauth2.encode("ascii")).decode("ascii")
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as srv:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            code, resp = srv.docmd("AUTH", f"XOAUTH2 {auth_str}")
            if code != 235:
                raise smtplib.SMTPAuthenticationError(code, resp)
            srv.sendmail(user_email, valid_to, msg.as_string())
        return

    # ── Password / App-password path ──────────────────────────────────────────
    cfg = _smtp_cfg()
    if not all([cfg["host"], cfg["user"], cfg["pass"]]):
        raise ValueError(
            "SMTP not configured.\n\n"
            "Go to Settings → Email & Microsoft → Connect Google / Microsoft Account,\n"
            "or fill in the SMTP section with host / email / App Password."
        )

    from_addr = f"{cfg['name']} <{cfg['user']}>" if cfg["name"] else cfg["user"]
    msg = _build_mime(from_addr, valid_to, subject, body, html_body, attachment_path)

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as srv:
        if cfg["tls"]:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
        srv.login(cfg["user"], cfg["pass"])
        srv.sendmail(cfg["user"], valid_to, msg.as_string())


# ── IMAP reading ──────────────────────────────────────────────────────────────

def _imap_connect():
    # ── OAuth path ────────────────────────────────────────────────────────────
    oauth = _oauth_imap_creds()
    if oauth:
        imap_host, imap_port, user_email, raw_xoauth2 = oauth
        raw_bytes = raw_xoauth2.encode("ascii")
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        # imaplib.authenticate() base64-encodes whatever the callback returns,
        # so pass raw bytes here — NOT pre-encoded.
        mail.authenticate("XOAUTH2", lambda challenge: raw_bytes)
        return mail

    # ── Password / App-password path ──────────────────────────────────────────
    cfg = _imap_cfg()
    if not all([cfg["host"], cfg["user"], cfg["pass"]]):
        raise ValueError(
            "IMAP not configured.\n\n"
            "Go to Settings → Email & Microsoft → Connect Google / Microsoft Account,\n"
            "or fill in the IMAP section with host / email / App Password."
        )
    mail = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    mail.login(cfg["user"], cfg["pass"])
    return mail


def list_folders() -> list:
    """Return list of IMAP folder names."""
    mail = _imap_connect()
    _, folders = mail.list()
    mail.logout()
    result = []
    for f in folders:
        parts = f.decode().split('"/"')
        name = parts[-1].strip().strip('"')
        result.append(name)
    return result


def fetch_messages(folder: str = "INBOX", limit: int = 60) -> list:
    """
    Fetch message headers from the given folder.
    Returns list of dicts: uid, subject, from_addr, date, unread, has_attachment.
    """
    mail = _imap_connect()
    mail.select(f'"{folder}"' if " " in folder else folder)

    _, data = mail.search(None, "ALL")
    uids = data[0].split()
    recent = uids[-limit:][::-1]  # most recent first

    messages = []
    for uid in recent:
        try:
            _, msg_data = mail.fetch(uid, "(RFC822.HEADER FLAGS)")
            raw   = msg_data[0][1]
            flags = msg_data[0][0]
            msg   = email.message_from_bytes(raw)

            flags_str = flags.decode() if isinstance(flags, bytes) else str(flags)
            unread    = "\\Seen" not in flags_str

            messages.append({
                "uid":     uid.decode(),
                "subject": _decode_str(msg.get("Subject", "(no subject)")),
                "from":    _decode_str(msg.get("From", "")),
                "date":    msg.get("Date", ""),
                "unread":  unread,
            })
        except Exception:
            pass

    mail.logout()
    return messages


def fetch_body(uid: str, folder: str = "INBOX", mark_read: bool = True) -> dict:
    """
    Fetch full message body by UID.
    Returns dict: subject, from_addr, to, date, body, raw_headers.
    """
    mail = _imap_connect()
    mail.select(f'"{folder}"' if " " in folder else folder)
    _, msg_data = mail.fetch(uid.encode(), "(RFC822)")
    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    if mark_read:
        mail.store(uid.encode(), "+FLAGS", "\\Seen")
    mail.logout()

    return {
        "uid":      uid,
        "subject":  _decode_str(msg.get("Subject", "")),
        "from":     _decode_str(msg.get("From", "")),
        "to":       _decode_str(msg.get("To", "")),
        "date":     msg.get("Date", ""),
        "body":     _get_body(msg),
        "reply_to": _decode_str(msg.get("Reply-To", "")) or _decode_str(msg.get("From", "")),
    }


def delete_message(uid: str, folder: str = "INBOX") -> None:
    mail = _imap_connect()
    mail.select(f'"{folder}"' if " " in folder else folder)
    mail.store(uid.encode(), "+FLAGS", "\\Deleted")
    mail.expunge()
    mail.logout()


def mark_unread(uid: str, folder: str = "INBOX") -> None:
    mail = _imap_connect()
    mail.select(f'"{folder}"' if " " in folder else folder)
    mail.store(uid.encode(), "-FLAGS", "\\Seen")
    mail.logout()
