import os
from database import get_setting

_llm = None


def _get_llm():
    global _llm
    return _llm


def reload_llm():
    global _llm
    _llm = None


def summarize_reply(email_body: str, company: str = "", position: str = "") -> str:
    llm = _get_llm()
    if llm is None:
        clean = " ".join(email_body.split())
        return clean[:400] + ("…" if len(clean) > 400 else "")

    ctx = f" from {company}" if company else ""
    if position:
        ctx += f" regarding the {position} role"

    # No <s> prefix — llama_cpp adds BOS automatically
    prompt = f"""[INST] Summarise this job-application reply{ctx} in 2-3 sentences.
Focus on: outcome (rejection/positive/interview/info request), any action items, overall tone.

Email:
{email_body[:1800]}

Summary: [/INST]"""

    try:
        out = llm(prompt, max_tokens=200, temperature=0.3,
                  stop=["[INST]", "\n\nEmail:", "---"])
        return out["choices"][0]["text"].strip()
    except Exception as e:
        return f"[Summary unavailable: {str(e)[:60]}]"


def classify_sentiment(email_body: str) -> str:
    llm = _get_llm()
    if llm is None:
        bl = email_body.lower()
        if any(w in bl for w in ["unfortunately", "regret", "not moving forward", "not a fit"]):
            return "rejected"
        if any(w in bl for w in ["interview", "call", "schedule", "next steps"]):
            return "interview"
        if any(w in bl for w in ["thank you", "received", "reviewing"]):
            return "acknowledged"
        return "unknown"

    prompt = f"""[INST] Classify this email reply into ONE word only: rejected / interview / acknowledged / offer / unknown

Reply: {email_body[:500]}

Classification: [/INST]"""

    try:
        out = llm(prompt, max_tokens=8, temperature=0.1, stop=["\n", " "])
        label = out["choices"][0]["text"].strip().lower()
        return label if label in {"rejected","interview","acknowledged","offer","unknown"} else "unknown"
    except Exception:
        return "unknown"
