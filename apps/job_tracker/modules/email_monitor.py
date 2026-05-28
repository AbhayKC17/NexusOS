import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime
from database import get_db, get_setting
from modules.llm_summarizer import summarize_reply


def sync_replies():
    """
    Route reply sync to the correct backend based on settings:
      sync_mode = 'outlook'    → Microsoft Outlook on Mac (SSO / no password)
      sync_mode = 'apple_mail' → Apple Mail (SSO / no password)
      sync_mode = 'imap'       → IMAP with stored credentials (default)
    """
    mode = get_setting("sync_mode", "imap")
    if mode == "outlook":
        from modules.outlook_reader import sync_replies as _ol_sync
        return _ol_sync()
    if mode == "apple_mail":
        from modules.apple_mail_reader import sync_replies as _am_sync
        return _am_sync()
    return sync_replies_imap()


def index_all_inbox():
    """
    Route inbox indexing (ALL messages, TKEY detection + AI draft) to the correct backend.
    For Outlook mode: tries Microsoft Graph first (reliable), falls back to AppleScript.
    Returns {"indexed": int, "tkey_matches": int, "errors": list}
    """
    mode = get_setting("sync_mode", "imap")

    if mode == "outlook":
        # Prefer Graph API — works without Outlook being open, no AppleScript bugs
        try:
            from modules.ms_graph import is_connected
            if is_connected():
                from modules.outlook_reader import index_all_inbox_graph
                return index_all_inbox_graph()
        except Exception:
            pass
        # Fallback to AppleScript-based reader
        from modules.outlook_reader import index_all_inbox as _ol_idx
        return _ol_idx()

    if mode == "apple_mail":
        from modules.apple_mail_reader import index_all_inbox as _am_idx
        return _am_idx()

    return {"indexed": 0, "tkey_matches": 0, "errors": [
        "Inbox indexing requires Apple Mail or Outlook sync mode.\n"
        "Configure it in Settings → Email & Microsoft."
    ]}

TRK_PATTERN = re.compile(r'\[TRK-([a-f0-9\-]{36})\]', re.IGNORECASE)


def _decode_str(s):
    if s is None:
        return ''
    parts = decode_header(s)
    result = ''
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or 'utf-8', errors='replace')
        else:
            result += part
    return result


def _get_body(msg):
    plain, html = '', ''
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get('Content-Disposition', ''))
            if 'attachment' in cd:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or 'utf-8'
            text = payload.decode(charset, errors='replace')
            if ct == 'text/plain':
                plain += text
            elif ct == 'text/html':
                html += text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            plain = payload.decode(charset, errors='replace')
    return plain.strip() or html.strip()


def sync_replies_imap():
    imap_host = get_setting('imap_host', '')
    imap_port = int(get_setting('imap_port', 993))
    imap_user = get_setting('imap_user', '')
    imap_pass = get_setting('imap_pass', '')

    if not imap_host or not imap_user or not imap_pass:
        return {"error": "IMAP settings not configured", "new_replies": 0}

    new_replies = 0
    errors = []

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(imap_user, imap_pass)
        mail.select('INBOX')

        # search for emails containing TRK- pattern in subject
        _, data = mail.search(None, 'SUBJECT', '"TRK-"')
        message_ids = data[0].split()

        conn = get_db()
        for msg_id in message_ids:
            try:
                _, msg_data = mail.fetch(msg_id, '(RFC822)')
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = _decode_str(msg.get('Subject', ''))
                match = TRK_PATTERN.search(subject)
                if not match:
                    # also check body
                    body_check = _get_body(msg)
                    match = TRK_PATTERN.search(body_check)

                if not match:
                    continue

                tracked_uuid = match.group(1)

                # look up application
                app = conn.execute(
                    "SELECT * FROM applications WHERE uuid = ?", (tracked_uuid,)
                ).fetchone()
                if not app:
                    continue

                # avoid duplicate reply
                date_str = msg.get('Date', '')
                existing = conn.execute('''
                    SELECT id FROM replies
                    WHERE application_id = ? AND subject = ?
                ''', (app['id'], subject)).fetchone()
                if existing:
                    continue

                from_raw = _decode_str(msg.get('From', ''))
                body = _get_body(msg)

                # summarize with local LLM
                try:
                    summary = summarize_reply(body, app['company'], app['position'])
                except Exception:
                    summary = body[:300] + '...' if len(body) > 300 else body

                received_at = datetime.utcnow().isoformat()
                conn.execute('''
                    INSERT INTO replies
                        (application_id, uuid, received_at, from_email, from_name, subject, body, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    app['id'], tracked_uuid, received_at,
                    from_raw, from_raw, subject, body, summary
                ))
                conn.execute('''
                    UPDATE applications SET status = 'replied' WHERE id = ?
                ''', (app['id'],))
                new_replies += 1

            except Exception as e:
                errors.append(str(e))

        conn.commit()
        conn.close()
        mail.logout()

    except Exception as e:
        return {"error": str(e), "new_replies": 0}

    return {"new_replies": new_replies, "errors": errors}
