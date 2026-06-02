"""
quick_mailer.py — Zero-dependency one-call email sender for the NexusOS AI agent.

The AI only needs to know: to_email, company, description.
Everything else (resume path, sender choice, personalised body) is handled here.

Usage by AI:
    call: send_email(to_email="hr@acme.com", company="Acme Corp",
                     description="Berlin fintech startup")
"""
import os
import subprocess

from database import get_setting, subject_to_tracking_key
from modules.apple_mail_sender import (
    _profile,
    send_via_apple_mail,
    generate_personalized_intro,
    build_email_body,
    transform_to_careers,
    generate_subject,
)


# ── internal helpers ───────────────────────────────────────────────────────────

def _company_from_email(email: str) -> str:
    """Infer a display company name from an email domain."""
    if "@" not in email:
        return email.title()
    domain = email.split("@", 1)[1]
    parts  = domain.split(".")
    skip   = {"mail", "careers", "jobs", "hr", "info", "noreply", "support", "team"}
    name   = next((p for p in parts if p.lower() not in skip), parts[0])
    return name.replace("-", " ").replace("_", " ").title()


def _best_sender() -> str:
    """Auto-detect the best available sender on this machine."""
    # Apple Mail — macOS only
    try:
        r = subprocess.run(
            ["osascript", "-e", 'tell application "Mail" to return name'],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return "apple_mail"
    except Exception:
        pass

    # SMTP / OAuth
    try:
        from modules.mail_client import is_configured
        if is_configured().get("smtp"):
            return "smtp"
    except Exception:
        pass

    return "apple_mail"


# ── public function ────────────────────────────────────────────────────────────

def quick_send_email(
    to_email: str,
    company: str = "",
    description: str = "",
    instructions: str = "",
    sender_mode: str = "auto",
    attach_resume: bool = True,
    send_to_careers: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    All-in-one outreach email sender for the NexusOS AI agent.

    Parameters
    ----------
    to_email        Recipient email address (required).
    company         Company or agency name — used for personalisation.
    description     Short description of what the company does.
    instructions    Extra instructions for the email body (optional).
    sender_mode     'auto' | 'apple_mail' | 'smtp' | 'outlook'
    attach_resume   Attach resume from Settings (default True).
    send_to_careers Also send to careers@domain (default True).
    dry_run         Print only, do not send.

    Returns
    -------
    dict with keys: sent (bool), to, subject, resume_attached, error
    """
    to_email = (to_email or "").strip().lower()
    if not to_email or "@" not in to_email:
        return {"sent": False, "to": to_email,
                "error": f"Invalid email address: '{to_email}'"}

    # ── resolve resume ─────────────────────────────────────────────────────────
    p = _profile()
    resume = None
    if attach_resume:
        rpath = p.get("resume") or get_setting("resume_path", "")
        if rpath and os.path.isfile(rpath):
            resume = rpath

    # ── generate email content ─────────────────────────────────────────────────
    company_name = company.strip() or _company_from_email(to_email)
    hint         = " ".join(filter(None, [description, instructions]))

    intro   = generate_personalized_intro(
        company_name=company_name,
        short_desc=hint[:400] if hint else "",
    )
    body    = build_email_body(company_name, intro)
    subject = generate_subject(company_name, "", p["name"], p.get("role", ""))
    tkey    = subject_to_tracking_key(subject)

    # ── build recipient list ───────────────────────────────────────────────────
    to_list = [to_email]
    if send_to_careers:
        care = transform_to_careers(to_email)
        if care != to_email:
            to_list.append(care)

    # ── send ───────────────────────────────────────────────────────────────────
    mode = sender_mode if sender_mode != "auto" else _best_sender()

    try:
        if dry_run:
            print(f"[DRY RUN] To: {to_list}\nSubject: {subject}\n{body[:200]}")
        elif mode == "outlook":
            from modules.outlook_sender import send_via_outlook
            send_via_outlook(to_list, subject, body, resume, tkey)
        elif mode == "smtp":
            from modules.mail_client import send_email as _smtp
            _smtp(to_list, subject, body, attachment_path=resume, tracking_key=tkey)
        else:
            send_via_apple_mail(to_list, subject, body, resume, tkey)

        return {
            "sent":            True,
            "to":              ", ".join(to_list),
            "subject":         subject,
            "resume_attached": bool(resume),
            "error":           None,
        }

    except Exception as exc:
        return {
            "sent":  False,
            "to":    ", ".join(to_list),
            "subject": subject,
            "error": str(exc),
        }
