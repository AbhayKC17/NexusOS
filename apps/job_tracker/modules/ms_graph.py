"""
Microsoft Graph API client for JobTracker.
Uses MSAL PublicClientApplication with device code flow.

Works with:
  - Personal Microsoft accounts (outlook.com, hotmail.com)
  - Work/school accounts (company Exchange, Entra ID, Office 365 SSO)
  - Company laptops where email signs in automatically (no password needed)

Free Azure app registration (2 minutes):
  1. portal.azure.com  →  sign in with any Microsoft account (free)
  2. Search "App registrations"  →  New registration
  3. Name: JobTracker  →  Supported accounts: "Accounts in any org + personal"
  4. Redirect URI: Public client/native  →  http://localhost
  5. Register  →  copy Application (client) ID  →  paste in Settings
  6. API permissions  →  Add  →  Microsoft Graph  →  Delegated:
         Mail.Send   Mail.ReadBasic   Mail.Read   User.Read
     (user grants these on first sign-in automatically)
"""

import base64
import os
import re
import requests

from database import get_setting, set_setting

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTHORITY  = "https://login.microsoftonline.com/common"
SCOPES     = [
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Mail.ReadBasic",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]

_DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_CACHE_PATH = os.path.join(_DATA_DIR, "msal_token_cache.json")


def _client_id() -> str:
    cid = get_setting("ms_graph_client_id", "").strip()
    if not cid:
        raise ValueError(
            "Microsoft App Client ID not configured.\n\n"
            "Go to Settings → Email & Microsoft → Microsoft Graph section.\n"
            "See the Guide tab for the free 2-minute Azure setup."
        )
    return cid


def _build_app():
    import msal
    cache = msal.SerializableTokenCache()
    if os.path.isfile(_CACHE_PATH):
        try:
            with open(_CACHE_PATH) as f:
                cache.deserialize(f.read())
        except Exception:
            pass

    app = msal.PublicClientApplication(
        _client_id(),
        authority=AUTHORITY,
        token_cache=cache,
    )
    return app, cache


def _persist_cache(cache) -> None:
    if cache.has_state_changed:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_CACHE_PATH, "w") as f:
            f.write(cache.serialize())


def get_token() -> str:
    """Return a valid access token, refreshing silently if the token is expired."""
    app, cache = _build_app()
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        _persist_cache(cache)
        if result and "access_token" in result:
            return result["access_token"]
    raise ValueError(
        "Not connected to Microsoft.\n\n"
        "Go to Settings → Email & Microsoft → click  'Connect Microsoft Account'."
    )


def is_connected() -> bool:
    try:
        get_token()
        return True
    except Exception:
        return False


def get_signed_in_email() -> str:
    try:
        app, _ = _build_app()
        accounts = app.get_accounts()
        return accounts[0].get("username", "") if accounts else ""
    except Exception:
        return ""


def start_device_flow() -> dict:
    """
    Initiate device code flow.
    Returns dict with: user_code, verification_uri, message, expires_in, interval
    Call complete_device_flow() in a background thread to block until auth completes.
    """
    app, _ = _build_app()
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise ValueError(
            f"Could not start device flow: {flow.get('error_description', str(flow))}\n\n"
            "Check that your Client ID is correct in Settings."
        )
    return flow


def complete_device_flow(flow: dict) -> str:
    """
    Block until the user completes auth in the browser.
    Returns the signed-in email address on success.
    MUST be called from a background thread (QThread worker).
    """
    app, cache = _build_app()
    result = app.acquire_token_by_device_flow(flow)
    _persist_cache(cache)
    if "access_token" in result:
        accounts = app.get_accounts()
        email = accounts[0].get("username", "connected") if accounts else "connected"
        set_setting("ms_graph_email", email)
        return email
    err = result.get("error_description") or result.get("error") or "Authentication failed."
    raise ValueError(err)


def disconnect() -> None:
    """Sign out and wipe cached token."""
    if os.path.isfile(_CACHE_PATH):
        os.remove(_CACHE_PATH)
    set_setting("ms_graph_email", "")


# ── Email sending ─────────────────────────────────────────────────────────────

def send_email(
    to_emails: list,
    subject: str,
    html_body: str,
    attachment_path: str = None,
) -> None:
    """Send an email via POST /me/sendMail."""
    token = get_token()
    recipients = [{"emailAddress": {"address": e}} for e in to_emails if e and "@" in e]
    if not recipients:
        raise ValueError("No valid recipient email addresses.")

    message: dict = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": recipients,
    }

    if attachment_path and os.path.isfile(attachment_path):
        with open(attachment_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode()
        ext = os.path.splitext(attachment_path)[1].lower()
        ct = "application/pdf" if ext == ".pdf" else "application/octet-stream"
        message["attachments"] = [{
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": os.path.basename(attachment_path),
            "contentType": ct,
            "contentBytes": encoded,
        }]

    resp = requests.post(
        f"{GRAPH_BASE}/me/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": message, "saveToSentItems": True},
        timeout=30,
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(
            f"Microsoft Graph send failed (HTTP {resp.status_code}):\n{resp.text[:300]}"
        )


# ── Inbox reading ─────────────────────────────────────────────────────────────

def list_inbox_messages(top: int = 100) -> list:
    """List inbox message headers (id, subject, from, receivedDateTime)."""
    token = get_token()
    resp = requests.get(
        f"{GRAPH_BASE}/me/mailFolders/Inbox/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "$top": top,
            "$select": "id,subject,from,receivedDateTime",
            "$orderby": "receivedDateTime desc",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Graph list inbox failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json().get("value", [])


def get_message_body(message_id: str) -> str:
    """Fetch the plain-text body of a message (HTML tags stripped)."""
    token = get_token()
    resp = requests.get(
        f"{GRAPH_BASE}/me/messages/{message_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"$select": "body"},
        timeout=30,
    )
    if resp.status_code != 200:
        return ""
    content = resp.json().get("body", {}).get("content", "")
    return re.sub(r"<[^>]+>", " ", content).strip()
