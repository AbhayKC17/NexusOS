"""
Generate AI reply drafts for TKEY-matched inbox emails using the local Mistral LLM.
"""

from database import get_setting


def _sender_name() -> str:
    return get_setting("sender_name", "Abhay Kumar Choudhary")


def generate_reply_draft(
    reply_body: str,
    original_subject: str,
    original_body: str,
    company_name: str,
    position: str = "",
) -> str | None:
    """
    Generate a professional reply draft to a job application response.
    Returns None if LLM is not loaded (caller should retry later or show fallback).
    Returns a non-empty string on success.
    """
    from modules.llm_summarizer import _get_llm
    llm = _get_llm()

    if llm is None:
        return None

    name = _sender_name()
    context = f"Company: {company_name}\n"
    if position:
        context += f"Role applied for: {position}\n"

    orig_snip  = (original_body  or "")[:500].strip()
    reply_snip = (reply_body     or "")[:700].strip()

    prompt = (
        f"[INST] You are writing a professional email reply on behalf of {name}, a job applicant.\n\n"
        f"{context}\n"
        f"Original email {name} sent:\n{orig_snip}\n\n"
        f"Reply received from the company:\n{reply_snip}\n\n"
        f"Write a concise, warm, professional reply (2-3 paragraphs):\n"
        f"- Acknowledge what the company said\n"
        f"- Express continued enthusiasm\n"
        f"- Propose a clear next step (call, interview, additional info)\n"
        f"- Sign off as {name}\n"
        f"- No placeholders, ready to send as-is\n\n"
        f"Reply: [/INST]"
    )

    try:
        out = llm(
            prompt,
            max_tokens=420,
            temperature=0.65,
            stop=["[INST]", "[/INST]", "\n\nFrom:", "\n\nOn ", "---"],
        )
        draft = out["choices"][0]["text"].strip()
        return draft if len(draft) >= 60 else None
    except Exception:
        return None


def get_fallback_draft(company_name: str, position: str = "") -> str:
    """Return a polished template when the LLM is unavailable."""
    name = _sender_name()
    role_line = f" for the {position} role" if position else ""
    return (
        f"Thank you so much for getting back to me regarding my application{role_line} at {company_name}.\n\n"
        f"I remain very enthusiastic about the opportunity and would love to move forward. "
        f"Please let me know what works best — I'm happy to schedule a call or provide "
        f"any additional information you may need.\n\n"
        f"Looking forward to hearing from you.\n\n"
        f"Best regards,\n{name}"
    )
