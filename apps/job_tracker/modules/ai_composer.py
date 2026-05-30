"""
AI-powered batch email composer.
Accepts a raw list of email addresses + freeform user instructions,
and generates a personalised subject + body for each contact.
Uses the local LLM when loaded; falls back to the template path otherwise.
"""
import re
from typing import Dict, List

from modules.apple_mail_sender import _profile, generate_personalized_intro, build_email_body


def _company_from_email(email: str) -> str:
    """Derive a display company name from the email domain."""
    if "@" not in email:
        return email.title()
    domain = email.split("@", 1)[1]
    # Drop TLD(s) and common prefixes like "mail.", "careers."
    parts = domain.split(".")
    skip = {"mail", "careers", "jobs", "hr", "info", "noreply", "no-reply", "support"}
    name = next((p for p in parts if p.lower() not in skip), parts[0])
    return name.replace("-", " ").replace("_", " ").title()


def parse_emails(raw: str) -> List[str]:
    """Extract valid email addresses from arbitrary text."""
    found = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", raw)
    seen: set = set()
    result: List[str] = []
    for e in found:
        e = e.lower().strip()
        if e not in seen:
            seen.add(e)
            result.append(e)
    return result


def _llm_generate(company: str, to_email: str, instructions: str) -> Dict[str, str]:
    """Ask the local LLM for a subject + body. Returns {} on failure."""
    from modules.llm_summarizer import _get_llm
    llm = _get_llm()
    if llm is None:
        return {}

    p = _profile()
    prompt = (
        f"[INST] Write a cold outreach email.\n\n"
        f"Sender: {p['name']}, {p['role']}\n"
        f"Skills: {p['pitch']}\n"
        f"LinkedIn: {p['linkedin']}\n\n"
        f"Recipient: {to_email} ({company})\n"
        f"Instructions: {instructions}\n\n"
        f"Reply ONLY in this format:\n"
        f"SUBJECT: <one-line subject>\n"
        f"---\n"
        f"<email body starting with 'Hi {company} team,'>\n"
        f"[/INST]"
    )
    try:
        out = llm(prompt, max_tokens=500, temperature=0.75,
                  stop=["[INST]", "\n\n\n", "Recipient:", "Sender:"])
        text = out["choices"][0]["text"].strip()
        subject = ""
        body = ""
        if "SUBJECT:" in text and "---" in text:
            lines = text.split("\n")
            past_sep = False
            body_lines: List[str] = []
            for line in lines:
                if not subject and line.startswith("SUBJECT:"):
                    subject = line.replace("SUBJECT:", "", 1).strip()
                elif line.strip() == "---":
                    past_sep = True
                elif past_sep:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()
        if subject and body:
            return {"subject": subject, "body": body}
    except Exception:
        pass
    return {}


def generate_email_for_contact(
    to_email: str,
    company: str,
    instructions: str,
) -> Dict[str, str]:
    """
    Generate subject + body for one email address.
    Returns dict with keys: email, company, subject, body.
    """
    p = _profile()

    # Try LLM first
    result = _llm_generate(company, to_email, instructions)
    if result:
        return {**result, "email": to_email, "company": company}

    # Template fallback — weave instructions in as the "notes" hint
    intro = generate_personalized_intro(
        company_name=company,
        short_desc=instructions[:300] if instructions else "",
    )
    body = build_email_body(company, intro)
    subject = f"Joining {company}'s journey — {p['name']}"
    return {"email": to_email, "company": company, "subject": subject, "body": body}


def compose_batch(email_list_raw: str, instructions: str) -> List[Dict[str, str]]:
    """
    Parse a raw block of text for email addresses and generate a draft for each.
    Returns list of {email, company, subject, body} dicts.
    """
    emails = parse_emails(email_list_raw)
    drafts: List[Dict[str, str]] = []
    for email in emails:
        company = _company_from_email(email)
        drafts.append(generate_email_for_contact(email, company, instructions))
    return drafts
