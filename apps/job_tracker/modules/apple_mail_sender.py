"""
Apple Mail bulk sender using AppleScript + local LLM for personalised intros.
Emails are sent as HTML with an invisible tracking key embedded.
"""

import html as _html_mod
import os
import subprocess
import tempfile
import time
from typing import Optional, List

import pandas as pd

from database import get_db, get_setting, subject_to_tracking_key as _subject_to_key


def _profile():
    return {
        "name":     get_setting("sender_name",     "Abhay Kumar Choudhary"),
        "role":     get_setting("sender_role",     "Product Manager - Digital Supply Chain"),
        "pitch":    get_setting("sender_pitch",    "digital supply chain product management, Python automation, and process improvement"),
        "linkedin": get_setting("sender_linkedin", "https://www.linkedin.com/in/abhaykumarchoudhary2947/"),
        "resume":   get_setting("resume_path",     ""),
    }


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')



def _body_to_html(plain_body: str, tracking_key: str = "") -> str:
    """Convert plain-text body to HTML email with invisible tracking key."""
    escaped = _html_mod.escape(plain_body)
    # Preserve line breaks and blank-line paragraphs
    paragraphs = escaped.split("\n\n")
    html_paras = "".join(
        f"<p style='margin:0 0 14px 0;line-height:1.7'>{p.replace(chr(10), '<br>')}</p>"
        for p in paragraphs
    )
    # Invisible key: 1px white text — readable by AI, invisible to naked eye
    ghost = ""
    if tracking_key:
        ghost = (
            f'<span style="font-size:1px;color:#FEFEFE;line-height:0;'
            f'display:inline;user-select:none;opacity:0.01">'
            f'TKEY:{tracking_key}</span>'
        )
    return (
        "<html><head><meta charset='utf-8'></head>"
        "<body style='font-family:Arial,Helvetica,sans-serif;font-size:14px;"
        "color:#1a1a1a;max-width:600px;padding:20px'>"
        f"{html_paras}{ghost}"
        "</body></html>"
    )


def get_apple_mail_accounts() -> list:
    """
    Return list of (display_label, email_address) tuples from Apple Mail accounts.
    Runs AppleScript; returns [] on any error (e.g. Mail not installed).
    """
    script = '''
tell application "Mail"
    set output to ""
    repeat with acc in every account
        try
            set firstEmail to item 1 of (get email addresses of acc)
            set output to output & (get name of acc) & "|" & firstEmail & linefeed
        end try
    end repeat
    return output
end tell
'''
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return []
        accounts = []
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                name, email = line.split("|", 1)
                accounts.append((f"{name.strip()}  ({email.strip()})", email.strip()))
            elif "@" in line:
                accounts.append((line, line))
        return accounts
    except Exception:
        return []


def send_via_apple_mail(
    to_emails: List[str],
    subject: str,
    body: str,
    resume_path: Optional[str] = None,
    tracking_key: str = "",
    from_account: str = "",
) -> None:
    # Convert plain body → HTML with invisible tracking key
    html_body = _body_to_html(body, tracking_key)

    # Write HTML body to temp file — avoids AppleScript string limits
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
        tmp.write(html_body)
        tmp_path = tmp.name

    # Build recipients block
    recipients_block = "\n".join(
        f'        make new to recipient at end of to recipients with properties {{address:"{_esc(e)}"}}'
        for e in to_emails
        if e and "@" in e
    )

    # Build attachment block — correct AppleScript syntax
    attachment_block = ""
    if resume_path and os.path.isfile(resume_path):
        attachment_block = f'''
        set theAttachment to (POSIX file "{_esc(resume_path)}") as alias
        make new attachment with properties {{file name:theAttachment}} at after last paragraph of content'''
    elif resume_path:
        print(f"[Apple Mail] Resume not found at: {resume_path}")

    # Build the outgoing message properties dict — include sender only when specified
    msg_props = f'{{subject:"{_esc(subject)}", visible:true'
    if from_account:
        msg_props += f', sender:"{_esc(from_account)}"'
    msg_props += '}'

    # Use html content property so the invisible key is preserved
    script = f'''
set bodyFile to POSIX file "{_esc(tmp_path)}"
set theHtml to ""
try
    set theHtml to (read bodyFile as «class utf8»)
end try

tell application "Mail"
    set newMessage to make new outgoing message with properties {msg_props}
    tell newMessage
        set html content to theHtml
{recipients_block}
{attachment_block}
        delay 2
        send
    end tell
end tell
'''

    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=60)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def transform_to_careers(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return email
    _, domain = email.split("@", 1)
    return f"careers@{domain}" if domain else email


def generate_personalized_intro(
    company_name: str,
    short_desc: str = "",
    long_desc: str = "",
    categories: str = "",
    website: str = "",
    city: str = "",
    country: str = "",
) -> str:
    from modules.llm_summarizer import _get_llm

    p = _profile()
    llm = _get_llm()

    if llm is None:
        return (
            f"I admire what {company_name or 'your company'} is building and believe "
            f"my experience in {p['pitch']} could add real value to your team."
        )

    info = f"Company: {company_name}\n"
    if short_desc:   info += f"About: {short_desc}\n"
    if long_desc:    info += f"Details: {long_desc[:300]}\n"
    if categories:   info += f"Sector: {categories}\n"
    if city or country: info += f"Location: {city}, {country}\n"

    # No leading <s> — llama_cpp adds BOS token automatically
    prompt = f"""[INST] Write exactly 1-2 sentences (max 30 words) as an opening line for a cold job-application email.

Candidate: {p['name']}, {p['role']}, strengths: {p['pitch']}

{info}
Requirements:
- Show genuine interest in THIS company specifically
- Connect the candidate's background to their work
- Do NOT start with Hi/Hello
- No quotes, no sign-off, no bullet points
- One option only

Opening line: [/INST]"""

    try:
        out = llm(prompt, max_tokens=80, temperature=0.7,
                  stop=["[INST]", "\n\n", "Candidate:", "Company:"])
        return out["choices"][0]["text"].strip().strip('"')
    except Exception:
        return (
            f"I admire what {company_name or 'your company'} is building and believe "
            f"my experience in {p['pitch']} could be a strong match."
        )


def build_email_body(company_name: str, intro: str, position: str = "") -> str:
    p = _profile()
    name_disp = company_name or "your company"
    if position:
        middle = (
            f"I am currently exploring {position} opportunities, and I believe my "
            f"experience in {p['pitch']} would make me a strong addition to your team at {name_disp}."
        )
    else:
        middle = (
            f"I am deeply excited about what {name_disp} is building and would love to be "
            f"a part of your growth journey. My background in {p['pitch']} has prepared me "
            f"to contribute meaningfully from day one — whether in product, operations, or strategy."
        )
    return f"""Hi {name_disp} team,

{intro}

{middle}

You can find more about me here:
- LinkedIn: {p['linkedin']}
- Resume: attached

If this resonates, I would love a quick call or email exchange to explore if there is a mutual fit.

Best regards,
{p['name']}"""


def run_bulk_campaign(
    application_ids: List[int],
    sleep_seconds: int = 10,
    dry_run: bool = False,
    send_to_careers: bool = True,
    sender_mode: str = "apple_mail",   # "apple_mail" | "outlook" | "smtp"
    apple_mail_account: str = "",
    progress_callback=None,
) -> dict:
    p = _profile()
    resume_path = p["resume"] if p["resume"] and os.path.isfile(p["resume"]) else None

    if resume_path is None and p["resume"]:
        print(f"[Campaign] Resume path set but file not found: {p['resume']}")

    results = {"sent": 0, "failed": 0, "skipped": 0, "errors": []}
    conn = get_db()

    for app_id in application_ids:
        app = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not app:
            results["skipped"] += 1
            continue

        if not app["contact_email"]:
            results["skipped"] += 1
            results["errors"].append(f"{app['company']}: no email address")
            continue

        company   = app["company"] or ""
        raw_email = app["contact_email"]

        to_emails = [raw_email]
        if send_to_careers:
            careers = transform_to_careers(raw_email)
            if careers != raw_email:
                to_emails.append(careers)

        try:
            position = (app["position"] or "").strip()
            intro    = generate_personalized_intro(company_name=company, short_desc=app["notes"] or "")
            if position:
                subject = f"Exploring {position} opportunities at {company or 'your company'}"
            else:
                subject = f"Joining {company or 'your company'}'s journey — {p['name']}"
            body    = build_email_body(company, intro, position)

            tracking_key = _subject_to_key(subject)

            if dry_run:
                print(f"[DRY RUN] To: {to_emails} | Subject: {subject} | Sender: {sender_mode}")
                print(f"[DRY RUN] Tracking key: {tracking_key}")
                print(body[:300])
            elif sender_mode == "outlook":
                from modules.outlook_sender import send_via_outlook
                send_via_outlook(to_emails, subject, body, resume_path, tracking_key)
            elif sender_mode == "smtp":
                from modules.mail_client import send_email as _smtp_send
                _smtp_send(to_emails, subject, body,
                           attachment_path=resume_path, tracking_key=tracking_key)
            else:
                send_via_apple_mail(to_emails, subject, body, resume_path, tracking_key,
                                    from_account=apple_mail_account)

            from datetime import datetime
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE applications SET status='sent', sent_at=?, email_subject=?, email_body=?, tkey=? WHERE id=?",
                (now, subject, body, tracking_key, app_id)
            )
            conn.commit()
            results["sent"] += 1

            if progress_callback:
                progress_callback(app_id, company, "sent")

        except Exception as e:
            results["failed"] += 1
            err = f"{company}: {str(e)[:120]}"
            results["errors"].append(err)
            if progress_callback:
                progress_callback(app_id, company, f"failed: {e}")

        if not dry_run and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    conn.close()
    return results
