"""
Read reply emails from Microsoft Outlook (Mac) via AppleScript.
Works with Exchange / Office 365 / Entra ID accounts already signed in to Outlook.
No passwords or IMAP credentials needed. Outlook must be open and syncing.

Verified working AppleScript patterns for Outlook on Mac:
  - Inbox folder: mail folder "Inbox"
  - Messages:     messages of inboxFolder
  - Subject:      subject of m
  - Sender:       address of sender of m  (returns email string)
  - Date:         time received of m      (cast to string)
  - Body:         plain text content of m (fallback: content of m)

Note: Outlook on Mac does NOT expose accounts via `accounts` — use mail folders.
"""

import hashlib
import re
import subprocess

from database import get_db, get_setting

TRK_PATTERN = re.compile(r'\[TRK-([a-f0-9\-]{36})\]', re.IGNORECASE)
_SEP = "|||JT|||"


def _run(script: str, timeout: int = 20) -> tuple[int, str, str]:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _permission_error(stderr: str) -> bool:
    return "-1743" in stderr or "Not authorized" in stderr.lower()


def _permission_msg() -> str:
    return (
        "macOS denied AppleScript access to Microsoft Outlook.\n\n"
        "Fix: System Settings → Privacy & Security → Automation\n"
        "→ Enable  Microsoft Outlook  for  Terminal  (or your IDE / Python runner).\n\n"
        "Then restart JobTracker."
    )


def _outlook_running() -> bool:
    """Check if Outlook is running by trying a lightweight AppleScript command."""
    import subprocess as _sp
    try:
        # pgrep is instant — no AppleScript permission needed
        r = _sp.run(["pgrep", "-x", "Microsoft Outlook"],
                    capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def list_accounts() -> list[str]:
    """
    Return email-addressable identities in Outlook.
    Outlook on Mac doesn't expose `accounts` directly, so we derive identity
    from the From address of sent items, or fall back to reporting folder names.
    On company laptops with Exchange, this will show the work email.
    """
    # Try getting identity from Sent Items (reliable for Exchange accounts)
    rc, out, err = _run('''
tell application "Microsoft Outlook"
    set addrs to {}
    try
        set sentFolder to mail folder "Sent Items"
        set recentSent to messages of sentFolder
        repeat with m in recentSent
            try
                set addr to address of sender of m as string
                if addr is not "" and addrs does not contain addr then
                    set end of addrs to addr
                    if (count of addrs) >= 3 then exit repeat
                end if
            end try
        end repeat
    end try
    set AppleScript's text item delimiters to "|||JT|||"
    return addrs as text
end tell''', timeout=15)

    if rc != 0:
        if _permission_error(err):
            return ["__permission_denied__"]
        return []

    accounts = [s.strip() for s in out.split(_SEP) if s.strip()]

    # If no sent items, just return a generic label so the user can still proceed
    if not accounts:
        # Verify Outlook is at least accessible
        rc2, _, err2 = _run(
            'tell application "Microsoft Outlook" to return count of every mail folder', 8
        )
        if rc2 == 0:
            return ["Outlook Inbox (auto-detected)"]
    return accounts


def sync_replies(account_name: str = None) -> dict:
    """
    Scan Microsoft Outlook Inbox for messages with [TRK-...] in the subject.
    account_name is stored in settings but Outlook scans the unified Inbox —
    no per-account filtering needed since TRK UUIDs are globally unique.
    Returns {"new_replies": int, "errors": list}.
    """
    if not _outlook_running():
        return {"new_replies": 0, "errors": [
            "Microsoft Outlook is not running.\nOpen Outlook and try again."
        ]}

    # ── Step 1: scan Inbox for TRK subjects ──────────────────────────────────
    rc, out, err = _run('''
tell application "Microsoft Outlook"
    set output to ""
    set inboxFolder to mail folder "Inbox"
    set allMsgs to messages of inboxFolder
    repeat with m in allMsgs
        try
            set s to subject of m as string
            if s contains "[TRK-" then
                set sndrAddr to ""
                try
                    set sndrAddr to address of sender of m as string
                end try
                set dt to (time received of m) as string
                set output to output & s & "|||JT|||" & sndrAddr & "|||JT|||" & dt & return
            end if
        end try
    end repeat
    return output
end tell''', timeout=90)

    if rc != 0:
        if _permission_error(err):
            return {"new_replies": 0, "errors": [_permission_msg()]}
        return {"new_replies": 0, "errors": [
            f"Outlook scan failed.\n{err or 'Unknown error'}\n"
            "Make sure Outlook is open with your account signed in."
        ]}

    if not out.strip():
        return {"new_replies": 0, "errors": []}

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

        if conn.execute(
            "SELECT id FROM replies WHERE application_id=? AND subject=?",
            (app["id"], subject)
        ).fetchone():
            continue

        # ── Step 2: fetch body ────────────────────────────────────────────────
        body = _fetch_body(subject)

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


def _fetch_body(subject: str) -> str:
    safe_subject = subject.replace('"', '\\"')
    rc, out, _ = _run(f'''
tell application "Microsoft Outlook"
    set inboxFolder to mail folder "Inbox"
    set matches to (messages of inboxFolder whose subject is "{safe_subject}")
    if (count of matches) > 0 then
        set m to item 1 of matches
        try
            return plain text content of m as string
        on error
            try
                return content of m as string
            end try
        end try
    end if
    return ""
end tell''', timeout=30)
    return out if rc == 0 else ""


TKEY_PATTERN = re.compile(r'TKEY:(\d{14})')
_MAX_INDEX_PER_RUN = 60


def index_all_inbox_graph() -> dict:
    """
    Index ALL inbox messages via Microsoft Graph API (reliable, no AppleScript).
    Returns {"indexed": int, "tkey_matches": int, "errors": list}
    """
    from modules.ms_graph import list_inbox_messages, get_message_body

    conn = get_db()
    tkey_map = {
        row["tkey"]: row
        for row in conn.execute(
            "SELECT id, tkey, company, position, email_subject, email_body FROM applications "
            "WHERE tkey IS NOT NULL AND tkey != ''"
        ).fetchall()
    }

    results = {"indexed": 0, "tkey_matches": 0, "errors": []}

    try:
        messages = list_inbox_messages(top=100)
    except Exception as e:
        conn.close()
        return {"indexed": 0, "tkey_matches": 0, "errors": [str(e)]}

    for msg in messages:
        try:
            msg_id    = msg["id"]
            subject   = msg.get("subject", "")
            sender    = msg.get("from", {}).get("emailAddress", {}).get("address", "")
            date_str  = msg.get("receivedDateTime", "")
            msg_uid   = hashlib.md5(f"{sender}|{subject}|{date_str}".encode()).hexdigest()

            if conn.execute("SELECT id FROM inbox_index WHERE message_uid=?", (msg_uid,)).fetchone():
                continue

            body = get_message_body(msg_id)
            tkey_match = TKEY_PATTERN.search(body)
            tkey = tkey_match.group(1) if tkey_match else None
            app  = tkey_map.get(tkey) if tkey else None
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
            results["errors"].append(f"Index error: {e}")

    conn.close()
    return results


def index_all_inbox(account_name: str = None) -> dict:
    """
    Scan ALL Outlook inbox messages, store new ones in inbox_index.
    For messages containing TKEY:XXXXXXXXXXXXXX in body, match to applications
    and generate an AI reply draft.
    Returns {"indexed": int, "tkey_matches": int, "errors": list}
    """
    if not _outlook_running():
        return {"indexed": 0, "tkey_matches": 0, "errors": [
            "Microsoft Outlook is not running. Open Outlook and try again."
        ]}

    # Step 1: quick scan of all headers (no body fetch yet)
    rc, out, err = _run('''
tell application "Microsoft Outlook"
    set output to ""
    set inboxFolder to mail folder "Inbox"
    set allMsgs to messages of inboxFolder
    repeat with m in allMsgs
        try
            set s to subject of m as string
            set sndrAddr to ""
            try
                set sndrAddr to address of sender of m as string
            end try
            set dt to (time received of m) as string
            set output to output & s & "|||JT|||" & sndrAddr & "|||JT|||" & dt & return
        end try
    end repeat
    return output
end tell''', timeout=90)

    if rc != 0:
        if _permission_error(err):
            return {"indexed": 0, "tkey_matches": 0, "errors": [_permission_msg()]}
        return {"indexed": 0, "tkey_matches": 0, "errors": [
            f"Outlook scan failed.\n{err or 'Unknown error'}"
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

    new_msgs = new_msgs[:_MAX_INDEX_PER_RUN]

    for msg_uid, subject, sender, date_str in new_msgs:
        try:
            body = _fetch_body(subject)

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
