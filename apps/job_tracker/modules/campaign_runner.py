"""
Background campaign runner with atomic per-application claiming.
Multiple runs execute concurrently; SQLite write serialisation prevents
two runs from sending the same email.
"""
import json
import os
import threading
from datetime import datetime

from database import get_db, subject_to_tracking_key as _tkey
from modules.apple_mail_sender import (
    _profile,
    generate_personalized_intro,
    build_email_body,
    transform_to_careers,
    send_via_apple_mail,
)

_active: dict = {}   # run_id -> threading.Event
_lock = threading.Lock()


# ── atomic helpers ─────────────────────────────────────────────────────────────

def _claim(conn, app_id: int, run_id: int) -> bool:
    """
    Atomically mark an application as in_progress for this run.
    SQLite serialises writes, so only one thread can succeed.
    """
    cur = conn.execute(
        "UPDATE applications SET status='in_progress', campaign_run_id=? "
        "WHERE id=? AND status='pending'",
        (run_id, app_id),
    )
    conn.commit()
    return cur.rowcount > 0


def _release(conn, app_id: int) -> None:
    conn.execute(
        "UPDATE applications SET status='pending', campaign_run_id=NULL "
        "WHERE id=? AND status='in_progress'",
        (app_id,),
    )
    conn.commit()


def _set_run(run_id: int, **kw) -> None:
    conn = get_db()
    try:
        sets = ", ".join(f"{k}=?" for k in kw)
        conn.execute(f"UPDATE campaign_runs SET {sets} WHERE id=?",
                     list(kw.values()) + [run_id])
        conn.commit()
    finally:
        conn.close()


# ── startup cleanup ────────────────────────────────────────────────────────────

def cleanup_stale_runs() -> None:
    """
    Called once at app startup.  Resets any runs/applications left hanging
    from a previous crash (status='running' with no live thread).
    """
    conn = get_db()
    try:
        conn.execute(
            "UPDATE campaign_runs SET status='failed' WHERE status='running'"
        )
        conn.execute(
            "UPDATE applications SET status='pending', campaign_run_id=NULL "
            "WHERE status='in_progress'"
        )
        conn.commit()
    finally:
        conn.close()


# ── background thread ──────────────────────────────────────────────────────────

def _run_thread(run_id: int, stop_evt: threading.Event) -> None:
    conn = get_db()
    run = conn.execute("SELECT * FROM campaign_runs WHERE id=?", (run_id,)).fetchone()
    conn.close()
    if not run:
        return

    sender_mode  = run["sender_mode"]
    account      = run["apple_mail_account"] or ""
    sleep_sec    = int(run["sleep_seconds"] or 10)
    dry_run      = bool(run["dry_run"])
    send_careers = bool(run["send_to_careers"])

    _set_run(run_id, status="running", started_at=datetime.utcnow().isoformat())

    p = _profile()
    resume = p["resume"] if p["resume"] and os.path.isfile(p["resume"]) else None

    sent = failed = skipped = 0
    errors: list = []

    while not stop_evt.is_set():
        # Only fetch apps that have a contact email — avoids an infinite loop
        # where no-email apps are claimed, released to pending, and claimed again.
        conn = get_db()
        rows = conn.execute(
            "SELECT id FROM applications "
            "WHERE status='pending' "
            "  AND contact_email IS NOT NULL "
            "  AND trim(contact_email) != '' "
            "ORDER BY id ASC"
        ).fetchall()
        pending_ids = [r["id"] for r in rows]
        conn.close()

        if not pending_ids:
            break

        claimed_id = None
        for app_id in pending_ids:
            conn = get_db()
            ok = _claim(conn, app_id, run_id)
            conn.close()
            if ok:
                claimed_id = app_id
                break

        if claimed_id is None:
            # All pending rows are currently claimed by concurrent runs — wait briefly
            stop_evt.wait(2)
            continue

        conn = get_db()
        app = conn.execute("SELECT * FROM applications WHERE id=?", (claimed_id,)).fetchone()
        conn.close()

        if not app or not app["contact_email"]:
            # App email disappeared between query and claim (edge case) — skip permanently
            conn = get_db()
            conn.execute(
                "UPDATE applications SET status='pending', campaign_run_id=NULL "
                "WHERE id=? AND status='in_progress'", (claimed_id,)
            )
            conn.commit()
            conn.close()
            skipped += 1
            _set_run(run_id, sent=sent, failed=failed, skipped=skipped,
                     errors=json.dumps(errors[-10:]))
            continue

        company   = app["company"] or ""
        raw_email = app["contact_email"]
        to_emails = [raw_email]
        if send_careers:
            care = transform_to_careers(raw_email)
            if care != raw_email:
                to_emails.append(care)

        try:
            position = (app["position"] or "").strip()
            intro    = generate_personalized_intro(company_name=company,
                                                   short_desc=app["notes"] or "")
            subject  = (
                f"Exploring {position} opportunities at {company or 'your company'}"
                if position else
                f"Joining {company or 'your company'}'s journey — {p['name']}"
            )
            body = build_email_body(company, intro, position)
            tkey = _tkey(subject)

            if dry_run:
                print(f"[DRY RUN run#{run_id}] To: {to_emails} | Sender: {account} | {subject}")
            elif sender_mode == "outlook":
                from modules.outlook_sender import send_via_outlook
                send_via_outlook(to_emails, subject, body, resume, tkey)
            elif sender_mode == "smtp":
                from modules.mail_client import send_email as _smtp
                # Pass the specific account email so the correct OAuth token is used.
                # `account` is the Gmail address stored in apple_mail_account field.
                _smtp(
                    to_emails, subject, body,
                    attachment_path=resume,
                    tracking_key=tkey,
                    from_account_email=account or None,
                )
            else:
                send_via_apple_mail(to_emails, subject, body, resume, tkey,
                                    from_account=account)

            now = datetime.utcnow().isoformat()
            conn = get_db()
            conn.execute(
                "UPDATE applications SET status='sent', sent_at=?, "
                "email_subject=?, email_body=?, tkey=?, campaign_run_id=? WHERE id=?",
                (now, subject, body, tkey, run_id, claimed_id),
            )
            conn.commit()
            conn.close()
            sent += 1

        except Exception as exc:
            conn = get_db()
            _release(conn, claimed_id)
            conn.close()
            failed += 1
            errors.append(f"{company}: {str(exc)[:120]}")

        _set_run(run_id, sent=sent, failed=failed, skipped=skipped,
                 errors=json.dumps(errors[-10:]))

        if not dry_run and sleep_sec > 0:
            stop_evt.wait(sleep_sec)

    final = "stopped" if stop_evt.is_set() else "completed"
    _set_run(run_id, status=final, completed_at=datetime.utcnow().isoformat(),
             sent=sent, failed=failed, skipped=skipped,
             errors=json.dumps(errors[-10:]))

    with _lock:
        _active.pop(run_id, None)


# ── public API ─────────────────────────────────────────────────────────────────

def start_run(run_id: int) -> bool:
    with _lock:
        if run_id in _active:
            return False
        evt = threading.Event()
        _active[run_id] = evt
    t = threading.Thread(target=_run_thread, args=(run_id, evt), daemon=True)
    t.start()
    return True


def stop_run(run_id: int) -> bool:
    with _lock:
        evt = _active.get(run_id)
    if evt:
        evt.set()
        return True
    return False


def is_active(run_id: int) -> bool:
    with _lock:
        return run_id in _active
