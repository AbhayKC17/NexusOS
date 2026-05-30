"""
Groq cloud AI client — fast LLM inference for reply drafting and email composition.
Uses the OpenAI-compatible Groq API (https://console.groq.com).
Free tier: 14,400 requests/day on llama3-8b-8192.

Set groq_api_key in Settings → AI to enable.
Falls back to local Mistral 7B when not configured.
"""
import requests

from database import get_setting

_BASE_URL      = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama3-8b-8192"


def _key() -> str:
    return (get_setting("groq_api_key", "") or "").strip()


def is_configured() -> bool:
    return bool(_key())


def chat(
    messages: list,
    max_tokens: int = 500,
    temperature: float = 0.65,
    model: str = _DEFAULT_MODEL,
) -> str:
    """Make a Groq chat completion request. Raises on any error."""
    key = _key()
    if not key:
        raise ValueError(
            "Groq API key not set.\nGo to Settings → AI and paste your key from console.groq.com."
        )
    resp = requests.post(
        _BASE_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model":       model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_reply_draft(
    reply_body: str,
    original_subject: str,
    original_body: str,
    company_name: str,
    position: str = "",
) -> str:
    """Generate a professional reply to a job-application response. Returns draft text."""
    name      = get_setting("sender_name", "") or "the applicant"
    role_hint = f" for the {position} position" if position else ""
    messages  = [
        {
            "role":    "system",
            "content": (
                f"You are writing professional email replies on behalf of {name}, a job applicant. "
                "Be concise (2-3 paragraphs), warm, and action-oriented. "
                "Ready to send as-is — no placeholders, no brackets."
            ),
        },
        {
            "role":    "user",
            "content": (
                f"Company: {company_name}{role_hint}\n\n"
                f"Original email I sent:\n{(original_body or '')[:500]}\n\n"
                f"Their reply:\n{(reply_body or '')[:700]}\n\n"
                "Write a reply that: acknowledges what they said, shows continued enthusiasm, "
                f"proposes a clear next step. Sign off as {name}."
            ),
        },
    ]
    return chat(messages, max_tokens=420)


def compose_cold_email(
    company: str,
    description: str = "",
    instructions: str = "",
) -> dict:
    """Generate a cold outreach email. Returns {'subject': str, 'body': str}."""
    name  = get_setting("sender_name", "") or ""
    role  = get_setting("sender_role",  "") or ""
    pitch = get_setting("sender_pitch", "") or ""

    messages = [
        {
            "role":    "system",
            "content": (
                f"You are writing cold outreach emails for {name}, {role}. "
                f"Key skills: {pitch}. "
                "Reply in EXACTLY this format (two parts, nothing else):\n"
                "SUBJECT: <one-line subject>\n---\n<email body>"
            ),
        },
        {
            "role":    "user",
            "content": (
                f"Write a cold outreach email to {company}."
                + (f"\nAbout them: {description}" if description else "")
                + (f"\nExtra instructions: {instructions}" if instructions else "")
            ),
        },
    ]
    text = chat(messages, max_tokens=500)

    subject, body = "", ""
    if "SUBJECT:" in text and "---" in text:
        past_sep = False
        body_lines: list = []
        for line in text.split("\n"):
            if not subject and line.startswith("SUBJECT:"):
                subject = line.replace("SUBJECT:", "", 1).strip()
            elif line.strip() == "---":
                past_sep = True
            elif past_sep:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()

    return {
        "subject": subject or f"Introduction from {name}",
        "body":    body    or text,
    }
