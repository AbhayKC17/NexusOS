"""
nexus/registry.py — Callable function registry for NexusOS.

Any Python function can be registered under a name.
The AI agent uses this to discover and call capabilities.
"""
from __future__ import annotations
from typing import Callable, Any

_registry: dict[str, dict] = {}


def register(
    name: str,
    fn: Callable,
    description: str = "",
    node_id: str | None = None,
) -> None:
    _registry[name] = {"fn": fn, "description": description, "node_id": node_id}


def get(name: str) -> dict | None:
    return _registry.get(name)


def call(name: str, **kwargs) -> Any:
    entry = _registry.get(name)
    if not entry:
        raise KeyError(f"Function '{name}' not registered in NexusOS.")
    return entry["fn"](**kwargs)


def all_functions() -> list[dict]:
    return [
        {"name": k, "description": v["description"], "node_id": v["node_id"]}
        for k, v in _registry.items()
    ]


def seed_jobtracker() -> None:
    """Register all JobTracker callables into the function registry."""
    try:
        from modules.apple_mail_sender import send_via_apple_mail
        register(
            "send_email", send_via_apple_mail,
            description="Send a personalised email via Apple Mail with optional resume attachment.",
        )
    except Exception:
        pass

    try:
        from modules.resume_builder import build_resume_pdf
        register(
            "build_resume", build_resume_pdf,
            description="Generate a tailored PDF resume from a job description using Groq AI.",
        )
    except Exception:
        pass

    try:
        from campaign import run_campaign_batch
        register(
            "run_campaign", run_campaign_batch,
            description="Bulk-send personalised cold emails to all pending applications.",
        )
    except Exception:
        pass

    try:
        import modules.llm_summarizer as _ls
        _ask = getattr(_ls, "ask", None) or (lambda q: _ls.summarize(q))
        register(
            "ask_ai", _ask,
            description="Ask the local Mistral 7B model a question about job strategy.",
        )
    except Exception:
        pass

    try:
        from modules.email_sync import sync_replies
        register(
            "sync_replies", sync_replies,
            description="Scan inbox for replies and match them to tracked applications.",
        )
    except Exception:
        pass
