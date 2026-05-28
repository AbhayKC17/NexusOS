"""
Send emails via Microsoft — uses Graph API (primary) with Apple Mail as fallback.

Graph API (primary):
  - Works with any Microsoft account including company SSO / Entra ID
  - No Outlook needs to be open
  - Requires one-time device code auth in Settings → Microsoft Graph
  - Reliable — no AppleScript quirks

Apple Mail (fallback, only if Graph not connected):
  - Requires Apple Mail to be open
  - Sends via AppleScript
"""

import html as _html_mod
import os
import subprocess
import tempfile
from typing import List, Optional


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _build_html_body(body: str, tracking_key: str = "") -> str:
    escaped    = _html_mod.escape(body)
    paragraphs = escaped.split("\n\n")
    html_paras = "".join(
        f"<p style='margin:0 0 14px 0;line-height:1.7'>{p.replace(chr(10), '<br>')}</p>"
        for p in paragraphs
    )
    ghost = (
        f'<span style="font-size:1px;color:#FEFEFE;line-height:0;'
        f'display:inline;user-select:none;opacity:0.01">'
        f'TKEY:{tracking_key}</span>'
    ) if tracking_key else ""

    return (
        "<html><head><meta charset='utf-8'></head>"
        "<body style='font-family:Arial,Helvetica,sans-serif;font-size:14px;"
        "color:#1a1a1a;max-width:600px;padding:20px'>"
        f"{html_paras}{ghost}"
        "</body></html>"
    )


def send_via_outlook(
    to_emails: List[str],
    subject: str,
    body: str,
    resume_path: Optional[str] = None,
    tracking_key: str = "",
) -> None:
    """
    Send via Microsoft Graph API if connected, otherwise fall back to Apple Mail.
    Raises RuntimeError with a clear message if neither works.
    """
    html_body = _build_html_body(body, tracking_key)

    # ── Primary: Microsoft Graph API ──────────────────────────────────────────
    try:
        from modules.ms_graph import is_connected, send_email as graph_send
        if is_connected():
            graph_send(to_emails, subject, html_body, resume_path)
            return
    except ImportError:
        pass
    except Exception as e:
        # Graph is connected but the send failed — re-raise with context
        raise RuntimeError(f"Microsoft Graph send failed: {e}") from e

    # ── Fallback: Apple Mail AppleScript ──────────────────────────────────────
    try:
        from modules.apple_mail_sender import send_via_apple_mail
        send_via_apple_mail(to_emails, subject, body, resume_path, tracking_key)
        return
    except Exception as e:
        pass

    # ── Neither worked ────────────────────────────────────────────────────────
    raise RuntimeError(
        "Could not send via Microsoft Outlook.\n\n"
        "Option A (recommended): Connect your Microsoft account via\n"
        "  Settings → Email & Microsoft → Microsoft Graph → Connect Microsoft Account\n\n"
        "Option B: Add your Outlook account to Apple Mail, then try again.\n"
        "  System Settings → Internet Accounts → Microsoft Exchange"
    )
