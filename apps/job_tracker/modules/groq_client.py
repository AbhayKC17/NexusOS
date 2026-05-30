"""
Groq cloud AI client — fast LLM inference for reply drafting and email composition.
Uses the OpenAI-compatible Groq API (https://console.groq.com).
Free tier: 14,400 requests/day.

Set groq_api_key in Settings → AI to enable.
Falls back to local Mistral 7B when not configured.
"""
import requests

from database import get_setting

_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

# Models tried in order — first available one is used.
# llama3-8b-8192 is deprecated; current fast models listed first.
_MODELS = [
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]
_DEFAULT_MODEL = _MODELS[0]


def _key() -> str:
    return (get_setting("groq_api_key", "") or "").strip()


def is_configured() -> bool:
    return bool(_key())


def _groq_error(resp: requests.Response) -> str:
    """Extract the human-readable error from a Groq error response."""
    try:
        body = resp.json()
        return body.get("error", {}).get("message", resp.text[:300])
    except Exception:
        return resp.text[:300]


def chat(
    messages: list,
    max_tokens: int = 500,
    temperature: float = 0.65,
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    Make a Groq chat completion request.
    If the chosen model returns 400/404, automatically tries the fallback list.
    Raises ValueError with the actual Groq error message on failure.
    """
    key = _key()
    if not key:
        raise ValueError(
            "Groq API key not set.\n"
            "Go to Settings → AI and paste your key from console.groq.com."
        )

    # Build a priority list: requested model first, then the rest
    to_try = [model] + [m for m in _MODELS if m != model]

    last_err = "Unknown error"
    for m in to_try:
        resp = requests.post(
            _BASE_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       m,
                "messages":    messages,
                "max_tokens":  max_tokens,
                "temperature": temperature,
            },
            timeout=30,
        )
        if resp.ok:
            return resp.json()["choices"][0]["message"]["content"].strip()

        last_err = _groq_error(resp)

        # Only retry on model-related errors (400/404); propagate auth/rate errors immediately
        if resp.status_code in (401, 429):
            break
        if resp.status_code not in (400, 404):
            break

    raise ValueError(f"Groq API error: {last_err}")


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


def _repair_json_array(text: str) -> list:
    """
    Extract a JSON array from text, repairing truncation in three passes:

    1. Parse the full response as-is (happy path).
    2. Backward scan — close the array after each '}' until one parses.
    3. Regex extraction — directly pull email/company/subject/body values
       even when the body string is truncated mid-character.
    """
    import json as _json
    import re

    start = text.find("[")
    if start == -1:
        raise ValueError("No JSON array found in Groq response.")

    chunk = text[start:]

    # ── Pass 1: complete array ────────────────────────────────────────────────
    end = chunk.rfind("]") + 1
    if end > 0:
        try:
            return _json.loads(chunk[:end])
        except _json.JSONDecodeError:
            pass

    # ── Pass 2: backward scan — works when at least one object is complete ────
    for i in range(len(chunk) - 1, -1, -1):
        if chunk[i] != "}":
            continue
        candidate = chunk[: i + 1] + "]"
        try:
            result = _json.loads(candidate)
            if isinstance(result, list) and result:
                return result
        except _json.JSONDecodeError:
            continue

    # ── Pass 3: regex — works even when body is cut mid-string ───────────────
    # Matches each object by key name, tolerating a truncated "body" value.
    pattern = re.compile(
        r'"email"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"'
        r'.*?"company"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"'
        r'.*?"subject"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"'
        r'.*?"body"\s*:\s*"((?:[^"\\]|\\.)*)',
        re.DOTALL,
    )
    objects = []
    for m in pattern.finditer(chunk):
        body = m.group(4).rstrip("\\").rstrip(" ,")
        # Mark clearly if the body was cut short
        if body and body[-1] not in ".!?\"":
            body += "…"
        objects.append({
            "email":   m.group(1),
            "company": m.group(2),
            "subject": m.group(3),
            "body":    body,
        })
    if objects:
        return objects

    raise ValueError(
        "Could not parse JSON from Groq response.\n\n"
        "Tip: try fewer addresses at once or shorten the company descriptions.\n\n"
        "Raw (first 400 chars):\n" + text[:400]
    )


def extract_contacts(user_message: str) -> list[dict]:
    """
    Lightweight pass: extract every email address and its company context
    from a free-form message.  No drafting — just identification.

    Returns: [{"email": ..., "company": ..., "context": ...}]
    """
    system = (
        "Extract all email addresses from the user's message.\n"
        "For each email return: the company name and any context about that "
        "company (description, specialisation, location, role focus).\n\n"
        "Return ONLY a valid JSON array, nothing else:\n"
        '[{"email":"...","company":"...","context":"..."}]'
    )
    raw = chat(
        [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=800,
        temperature=0.2,
    )
    # Reuse the robust repair (passes 1 & 2 are structure-agnostic)
    start = raw.find("[")
    if start == -1:
        return []
    chunk = raw[start:]
    import json as _j
    end = chunk.rfind("]") + 1
    if end > 0:
        try:
            return _j.loads(chunk[:end])
        except Exception:
            pass
    for i in range(len(chunk) - 1, -1, -1):
        if chunk[i] != "}": continue
        try:
            r = _j.loads(chunk[:i + 1] + "]")
            if isinstance(r, list) and r:
                return r
        except Exception:
            pass
    return []


def draft_single_email(
    email: str,
    company: str,
    context: str,
    user_intent: str,
) -> dict:
    """
    Draft one personalised email for a single company.

    Priority:
      1. Local Mistral 7B — no rate limits, no cost, works offline.
      2. Groq cloud — only if local model is not loaded; retries on rate-limit.
      3. Template fallback — always succeeds.
    """
    import time as _time
    import re as _re

    name     = get_setting("sender_name",     "") or ""
    role     = get_setting("sender_role",     "") or ""
    pitch    = get_setting("sender_pitch",    "") or ""
    linkedin = get_setting("sender_linkedin", "") or ""

    # Shared greeting / sign-off — injected into every path so LLM can't flip roles
    greeting  = f"Hi {company} team,"
    signoff   = f"Best regards,\n{name}"

    # ── 1. Local Mistral 7B (no rate limits) ──────────────────────────────────
    try:
        from modules.llm_summarizer import _get_llm
        llm = _get_llm()
        if llm is not None:
            prompt = (
                f"[INST] Write a cold job-application email.\n\n"
                f"SENDER (who is writing): {name}, {role}\n"
                f"SENDER skills: {pitch}\n"
                f"SENDER LinkedIn: {linkedin}\n\n"
                f"RECIPIENT (who receives it): hiring team at {company} <{email}>\n"
                f"Company context: {(context or 'none')[:200]}\n"
                f"Purpose from sender: {user_intent[:150]}\n\n"
                f"Rules:\n"
                f"- The email is FROM {name} TO {company}.\n"
                f"- Opening line is EXACTLY: {greeting}\n"
                f"- Closing is EXACTLY: {signoff}\n"
                f"- 3 short paragraphs, max 90 words between greeting and sign-off.\n"
                f"- NO placeholders like [Your Name] or [Company Name]. Use real values.\n\n"
                f"SUBJECT: <subject under 10 words>\n---\n"
                f"{greeting}\n\n[/INST]"
            )
            out  = llm(prompt, max_tokens=360, temperature=0.65,
                       stop=["[INST]", "\nSUBJECT:", "RECIPIENT:"])
            text = out["choices"][0]["text"].strip()

            # The model output continues after the seeded greeting
            subject = ""
            body    = f"{greeting}\n\n{text}"

            # Extract subject if the model echoed it back (sometimes it does)
            for line in text.split("\n"):
                if line.upper().startswith("SUBJECT:"):
                    subject = line.split(":", 1)[1].strip()
                    break

            # Clean up sign-off — model may have added it or not
            if f"Best regards" not in body:
                body = body.rstrip() + f"\n\n{signoff}"

            if not subject:
                subject = f"Exploring opportunities at {company} — {name}"

            # Sanity check: body must mention the company name, not just the sender's
            if company.split()[0].lower() in body.lower():
                return {"email": email, "company": company,
                        "subject": subject, "body": body}
    except Exception:
        pass

    # ── 2. Groq cloud (rate-limit retry, clearer role prompt) ─────────────────
    if is_configured():
        import json as _j
        system = (
            f"You are writing a cold job-application email on behalf of {name} ({role}).\n"
            f"Skills: {pitch}. LinkedIn: {linkedin}.\n\n"
            f"The email is FROM {name} TO the hiring team at the recipient company.\n"
            f"NEVER address the email to {name}.\n"
            f"Start body with: {greeting}\n"
            f"End body with: {signoff}\n"
            f"Subject: under 10 words. Body: 3 paragraphs, 90 words max. No placeholders.\n"
            f'Return ONLY valid JSON: {{"subject":"...","body":"..."}}'
        )
        user_msg = (
            f"Company: {company}\nEmail: {email}\n"
            f"Context: {(context or 'none')[:200]}\n"
            f"Sender's intent: {user_intent[:150]}"
        )
        for attempt in range(3):
            try:
                raw = chat(
                    [{"role": "system", "content": system},
                     {"role": "user",   "content": user_msg}],
                    max_tokens=350,
                    temperature=0.65,
                )
                s = raw.find("{"); e = raw.rfind("}") + 1
                if s != -1 and e > 0:
                    d = _j.loads(raw[s:e])
                    body = d.get("body", "")
                    # Fix missing greeting / sign-off
                    if greeting not in body:
                        body = f"{greeting}\n\n{body}"
                    if "Best regards" not in body:
                        body = body.rstrip() + f"\n\n{signoff}"
                    return {"email": email, "company": company,
                            "subject": d.get("subject", f"Exploring opportunities — {name}"),
                            "body":    body}
                break
            except ValueError as err:
                msg = str(err)
                if "Rate limit" in msg and attempt < 2:
                    m = _re.search(r"try again in (\d+\.?\d*)s", msg)
                    _time.sleep(float(m.group(1)) + 1 if m else 7)
                else:
                    break

    # ── 3. Template fallback (always correct) ─────────────────────────────────
    from modules.apple_mail_sender import build_email_body
    intro = (
        f"I came across {company} and your work aligns strongly with my "
        f"background in {pitch or 'product and operations'}."
    )
    return {
        "email":   email,
        "company": company,
        "subject": f"Exploring opportunities at {company} — {name}",
        "body":    build_email_body(company, intro),
    }


def parse_and_draft_batch(user_message: str) -> list[dict]:
    """
    Parse a natural-language message that contains email addresses, company
    context, and a sending intent.  Draft a personalised outreach email for
    every address found.

    Returns: [{"email": ..., "company": ..., "subject": ..., "body": ...}]
    """
    name     = get_setting("sender_name",     "") or "the sender"
    role     = get_setting("sender_role",     "") or ""
    pitch    = get_setting("sender_pitch",    "") or ""
    linkedin = get_setting("sender_linkedin", "") or ""

    system = (
        f"You draft cold outreach emails on behalf of {name}, {role}.\n"
        f"Key skills: {pitch}.\n"
        f"LinkedIn: {linkedin}.\n\n"
        "The user's message contains one or more email addresses with company "
        "context and a stated intent (what kind of email to send).\n\n"
        "Rules:\n"
        "1. Extract EVERY email address in the message.\n"
        "2. Identify the company name from context or the email domain.\n"
        "3. Draft a warm, professional email aligned to the stated intent.\n"
        "4. Subject: concise, under 10 words.\n"
        "5. Body: MAXIMUM 120 words — 3 short paragraphs. No placeholders.\n"
        "6. IMPORTANT: output ONLY a valid, complete JSON array. Nothing else.\n\n"
        "Format:\n"
        "[{\"email\":\"...\",\"company\":\"...\",\"subject\":\"...\",\"body\":\"...\"}]"
    )

    raw = chat(
        [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=3000,
        temperature=0.65,
    )

    return _repair_json_array(raw)


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
