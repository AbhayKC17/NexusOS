"""
Read reply emails from Apple Mail via AppleScript.
No credentials needed — works with any account Apple Mail already has access to,
including company Exchange SSO accounts. Apple Mail must be open and syncing.

Verified working AppleScript patterns (tested on macOS):
  - Inbox: mailbox "INBOX" of acc  (NOT inbox of acc — that fails with -1728)
  - Sender: sender of m            (returns "Name <email>" string)
  - Date:   date received of m     (AppleScript date, cast to string)
  - Body:   content of m
"""

import hashlib
import os
import re
import subprocess
import tempfile

from database import get_db, get_setting

TRK_PATTERN = re.compile(r'\[TRK-([a-f0-9\-]{36})\]', re.IGNORECASE)
_SEP = "|||JT|||"   # field separator safe in account names and email subjects


def _run(script: str, timeout: int = 20) -> tuple[int, str, str]:
    """Run an AppleScript; return (returncode, stdout, stderr)."""
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _permission_error(stderr: str) -> bool:
    return "-1743" in stderr or "Not authorized" in stderr.lower()


def _permission_msg() -> str:
    return (
        "macOS denied AppleScript access to Mail.\n\n"
        "Fix: System Settings → Privacy & Security → Automation\n"
        "→ Enable  Mail  for  Terminal  (or your IDE / Python runner).\n\n"
        "Then restart JobTracker."
    )


# ── Public API ────────────────────────────────────────────────────────────────

def list_accounts() -> list[str]:
    """Return all account names configured in Apple Mail."""
    rc, out, err = _run('''
tell application "Mail"
    set output to ""
    repeat with acc in accounts
        set output to output & (name of acc as string) & "|||JT|||"
    end repeat
    return output
end tell''', timeout=12)

    if rc != 0:
        if _permission_error(err):
            return ["__permission_denied__"]
        return []
    return [s.strip() for s in out.split(_SEP) if s.strip()]


def sync_replies(account_name: str = None) -> dict:
    """
    Scan Apple Mail inbox for messages with [TRK-...] in the subject.
    Saves new replies to DB. Returns {"new_replies": int, "errors": list}.
    """
    if not account_name:
        account_name = get_setting("apple_mail_account", "")
    if not account_name:
        return {"new_replies": 0, "errors": ["No Apple Mail account configured."]}

    safe_name = account_name.replace('"', '\\"')

    # ── Step 1: scan inbox for TRK subjects ──────────────────────────────────
    # IMPORTANT: variable must NOT be named "inbox" — that's a reserved word in Mail AS
    scan_script = f'''
tell application "Mail"
    set output to ""
    set theAcc to first account whose name is "{safe_name}"
    set theBox to mailbox "INBOX" of theAcc
    set allMsgs to messages of theBox
    repeat with m in allMsgs
        try
            set s to subject of m as string
            if s contains "[TRK-" then
                set sndr to sender of m as string
                set dt to (date received of m) as string
                set output to output & s & "|||JT|||" & sndr & "|||JT|||" & dt & return
            end if
        end try
    end repeat
    return output
end tell'''

    rc, out, err = _run(scan_script, timeout=90)

    if rc != 0:
        if _permission_error(err):
            return {"new_replies": 0, "errors": [_permission_msg()]}
        return {"new_replies": 0, "errors": [
            f"Apple Mail scan failed.\n{err or 'Unknown error'}\n"
            "Make sure Apple Mail is open and the account is syncing."
        ]}

    if not out.strip():
        return {"new_replies": 0, "errors": []}   # inbox has no tracked messages

    results = {"new_replies": 0, "errors": []}
    conn = get_db()
    apps = conn.execute(
        "SELECT id, uuid, company, position FROM applications "
        "WHERE status IN ('sent','replied','interview','offer')"
    ).fetchall()
    uuid_map = {str(a["uuid"]): a for a in apps}

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_SEP)
        if len(parts) < 3:
            continue
        subject, sender, date_str = parts[0], parts[1], parts[2]

        m = TRK_PATTERN.search(subject)
        if not m:
            continue
        app = uuid_map.get(m.group(1))
        if not app:
            continue

        # Dedup
        if conn.execute(
            "SELECT id FROM replies WHERE application_id=? AND subject=?",
            (app["id"], subject)
        ).fetchone():
            continue

        # ── Step 2: fetch body for this message ──────────────────────────────
        body = _fetch_body(safe_name, subject)

        summary = ""
        try:
            from modules.llm_summarizer import summarize_reply
            summary = summarize_reply(body, app["company"], app["position"])
        except Exception:
            summary = body[:300]

        conn.execute('''
            INSERT INTO replies
                (application_id, uuid, received_at, from_email, from_name, subject, body, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (app["id"], m.group(1), date_str, sender, sender, subject, body, summary))
        conn.execute(
            "UPDATE applications SET status='replied' WHERE id=? AND status='sent'",
            (app["id"],)
        )
        conn.commit()
        results["new_replies"] += 1

    conn.close()
    return results


def _fetch_body(safe_account_name: str, subject: str) -> str:
    """Fetch body of the first inbox message with the given subject."""
    safe_subject = subject.replace('"', '\\"')
    rc, out, _ = _run(f'''
tell application "Mail"
    set theAcc to first account whose name is "{safe_account_name}"
    set theBox to mailbox "INBOX" of theAcc
    set matches to (messages of theBox whose subject is "{safe_subject}")
    if (count of matches) > 0 then
        return content of item 1 of matches as string
    end if
    return ""
end tell''', timeout=30)
    return out if rc == 0 else ""


TKEY_PATTERN = re.compile(r'TKEY:(\d{14})')
_MAX_INDEX_PER_RUN = 60


def index_all_inbox(account_name: str = None) -> dict:
    """
    Scan ALL Apple Mail inbox messages, store new ones in inbox_index.
    For messages containing TKEY:XXXXXXXXXXXXXX in body, match to applications
    and generate an AI reply draft.
    Returns {"indexed": int, "tkey_matches": int, "errors": list}
    """
    if not account_name:
        account_name = get_setting("apple_mail_account", "")
    if not account_name:
        return {"indexed": 0, "tkey_matches": 0, "errors": ["No Apple Mail account configured."]}

    safe_name = account_name.replace('"', '\\"')

    # Step 1: quick scan of all headers (no body fetch yet — fast)
    rc, out, err = _run(f'''
tell application "Mail"
    set output to ""
    set theAcc to first account whose name is "{safe_name}"
    set theBox to mailbox "INBOX" of theAcc
    set allMsgs to messages of theBox
    repeat with m in allMsgs
        try
            set s to subject of m as string
            set sndr to sender of m as string
            set dt to (date received of m) as string
            set output to output & s & "|||JT|||" & sndr & "|||JT|||" & dt & return
        end try
    end repeat
    return output
end tell''', timeout=90)

    if rc != 0:
        if _permission_error(err):
            return {"indexed": 0, "tkey_matches": 0, "errors": [_permission_msg()]}
        return {"indexed": 0, "tkey_matches": 0, "errors": [
            f"Apple Mail scan failed.\n{err or 'Unknown error'}"
        ]}

    if not out.strip():
        return {"indexed": 0, "tkey_matches": 0, "errors": []}

    conn = get_db()
    tkey_map = {
        row["tkey"]: row
        for row in conn.execute(
            "SELECT id, tkey, company, position, email_subject, email_body FROM applications "
            "WHERE tkey IS NOT NULL AND tkey != ''"
        ).fetchall()
    }

    results = {"indexed": 0, "tkey_matches": 0, "errors": []}
    new_msgs = []

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_SEP)
        if len(parts) < 3:
            continue
        subject, sender, date_str = parts[0], parts[1], parts[2]
        msg_uid = hashlib.md5(f"{sender}|{subject}|{date_str}".encode()).hexdigest()

        if conn.execute("SELECT id FROM inbox_index WHERE message_uid=?", (msg_uid,)).fetchone():
            continue
        new_msgs.append((msg_uid, subject, sender, date_str))

    # Limit per run to avoid blocking the UI for too long
    new_msgs = new_msgs[:_MAX_INDEX_PER_RUN]

    for msg_uid, subject, sender, date_str in new_msgs:
        try:
            body = _fetch_body(safe_name, subject)

            tkey_match = TKEY_PATTERN.search(body)
            tkey = tkey_match.group(1) if tkey_match else None

            app = tkey_map.get(tkey) if tkey else None
            app_id = app["id"] if app else None

            ai_draft = None
            if tkey and app:
                results["tkey_matches"] += 1
                try:
                    from modules.llm_auto_reply import generate_reply_draft
                    ai_draft = generate_reply_draft(
                        reply_body=body,
                        original_subject=app["email_subject"] or "",
                        original_body=app["email_body"] or "",
                        company_name=app["company"] or "",
                        position=app["position"] or "",
                    )
                    # None means LLM not loaded — user can regenerate from UI
                except Exception as e:
                    results["errors"].append(f"Draft gen failed: {e}")

            conn.execute('''
                INSERT OR IGNORE INTO inbox_index
                    (message_uid, from_email, subject, body, received_at, tkey, application_id, ai_reply_draft)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (msg_uid, sender, subject, body, date_str, tkey, app_id, ai_draft))
            conn.commit()
            results["indexed"] += 1
        except Exception as e:
            results["errors"].append(f"Index error ({subject[:40]}): {e}")

    conn.close()
    return results
