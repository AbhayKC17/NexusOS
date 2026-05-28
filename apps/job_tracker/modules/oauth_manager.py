"""
OAuth2 Authorization Code flow — exactly how Apple Mail connects to Google and Microsoft.

Flow:
  1. App builds an authorization URL (Google / Microsoft login page)
  2. Opens it in the user's default browser
  3. Runs a tiny local HTTP server on localhost:8741 to catch the redirect
  4. Extracts the authorization code from the callback URL
  5. Exchanges code for access + refresh tokens
  6. Stores tokens in the DB — refreshes silently on next use

No passwords ever stored. Works with company SSO (Microsoft Entra ID / Google Workspace).

App registrations needed (both free):
  Google  : console.cloud.google.com → Create project → Enable Gmail API →
            OAuth consent screen → Credentials → Desktop App → Client ID + Secret
  Microsoft: portal.azure.com → App registrations → (same as Microsoft Graph setup)
"""

import base64
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from database import get_setting, set_setting

# ── Bundled app credentials ───────────────────────────────────────────────────
# Registered once — users never need to enter these.
_GOOGLE_CLIENT_ID     = "REMOVED_SECRET"
_GOOGLE_CLIENT_SECRET = "REMOVED_SECRET"

# ── Redirect server ───────────────────────────────────────────────────────────

REDIRECT_PORT = 8741
REDIRECT_URI  = f"http://localhost:{REDIRECT_PORT}/callback"

_SUCCESS_HTML = (
    "<!DOCTYPE html><html><head><meta charset=utf-8>"
    "<title>JobTracker - Connected</title>"
    "<style>body{font-family:Arial,sans-serif;display:flex;align-items:center;"
    "justify-content:center;height:100vh;margin:0;background:#1a1a2e;color:#fff}"
    ".box{text-align:center;padding:40px;background:#16213e;border-radius:16px;"
    "border:1px solid rgba(255,255,255,.1)}.tick{font-size:60px;margin-bottom:16px}"
    "h2{margin:0 0 8px;font-size:24px;color:#6CCB5F}p{color:rgba(255,255,255,.6)}</style>"
    "</head><body><div class=box><div class=tick>&#10003;</div>"
    "<h2>Connected successfully!</h2><p>You can close this tab and return to JobTracker.</p>"
    "</div></body></html>"
).encode("utf-8")

_ERROR_HTML = (
    "<!DOCTYPE html><html><head><meta charset=utf-8>"
    "<title>JobTracker - Error</title>"
    "<style>body{font-family:Arial,sans-serif;display:flex;align-items:center;"
    "justify-content:center;height:100vh;margin:0;background:#1a1a2e;color:#fff}"
    ".box{text-align:center;padding:40px;background:#16213e;border-radius:16px;"
    "border:1px solid rgba(255,0,0,.3)}.tick{font-size:60px;margin-bottom:16px}"
    "h2{margin:0 0 8px;font-size:24px;color:#FF99A4}p{color:rgba(255,255,255,.6)}</style>"
    "</head><body><div class=box><div class=tick>&#10007;</div>"
    "<h2>Authentication failed</h2><p>Close this tab and try again in JobTracker.</p>"
    "</div></body></html>"
).encode("utf-8")


class _OAuthCallback:
    """Shared state between handler and caller — thread-safe via Event."""
    code:  str | None = None
    error: str | None = None
    state: str | None = None
    event = threading.Event()

    @classmethod
    def reset(cls):
        cls.code  = None
        cls.error = None
        cls.state = None
        cls.event.clear()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.endswith("/callback"):
            self.send_response(404); self.end_headers(); return

        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _OAuthCallback.code  = params["code"][0]
            _OAuthCallback.state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)
        else:
            err = params.get("error_description", params.get("error", ["Unknown error"]))[0]
            _OAuthCallback.error = err
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_ERROR_HTML)

        _OAuthCallback.event.set()

    def log_message(self, *args):
        pass  # suppress console output


def _run_local_server(timeout: int = 120) -> tuple[str | None, str | None]:
    """
    Start local server, wait for OAuth callback.
    Returns (code, error) — one will be None.
    """
    _OAuthCallback.reset()
    srv = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    srv.timeout = 1

    end = time.time() + timeout
    while not _OAuthCallback.event.is_set() and time.time() < end:
        srv.handle_request()

    srv.server_close()

    if not _OAuthCallback.event.is_set():
        return None, "Timed out waiting for browser authentication."
    return _OAuthCallback.code, _OAuthCallback.error


# ── Token storage ─────────────────────────────────────────────────────────────

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _token_path(provider: str) -> str:
    return os.path.join(_DATA_DIR, f"oauth_{provider}.json")


def _save_tokens(provider: str, tokens: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_token_path(provider), "w") as f:
        json.dump(tokens, f)


def _load_tokens(provider: str) -> dict | None:
    p = _token_path(provider)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        return json.load(f)


def _clear_tokens(provider: str) -> None:
    p = _token_path(provider)
    if os.path.isfile(p):
        os.remove(p)


# ── Google OAuth2 ─────────────────────────────────────────────────────────────

_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_SCOPES    = " ".join([
    # Full Gmail access — same as Apple Mail uses.
    # Covers: inbox, sent, drafts, all folders, send, delete, labels.
    "https://mail.google.com/",
    "openid", "email", "profile",
])


def google_auth_url(client_id: str, state: str) -> str:
    params = {
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         _GOOGLE_SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return _GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


def google_exchange_code(client_id: str, client_secret: str, code: str) -> dict:
    resp = requests.post(_GOOGLE_TOKEN_URL, data={
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()


def google_refresh(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(_GOOGLE_TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_google_token() -> str:
    """Return a valid Google access token, refreshing if expired."""
    t = _load_tokens("google")
    if not t:
        raise ValueError(
            "Google account not connected.\n\nGo to Settings → Connect Google Account."
        )
    expires_at = t.get("expires_at", 0)
    if time.time() < expires_at - 60:
        return t["access_token"]

    cid    = get_setting("google_client_id", "") or _GOOGLE_CLIENT_ID
    secret = get_setting("google_client_secret", "") or _GOOGLE_CLIENT_SECRET
    new_token = google_refresh(cid, secret, t["refresh_token"])
    t["access_token"] = new_token
    t["expires_at"]   = time.time() + 3500
    _save_tokens("google", t)
    return new_token


def is_google_connected() -> bool:
    try:
        get_google_token()
        return True
    except Exception:
        return False


def google_email() -> str:
    t = _load_tokens("google")
    return t.get("email", "") if t else ""


def google_connect() -> str:
    """
    Full Google OAuth2 browser flow using bundled app credentials.
    Opens browser → waits for callback → exchanges code → stores tokens.
    Returns the connected email address.
    BLOCKING — run in a QThread worker.
    """
    client_id     = get_setting("google_client_id", "")     or _GOOGLE_CLIENT_ID
    client_secret = get_setting("google_client_secret", "") or _GOOGLE_CLIENT_SECRET

    state = secrets.token_urlsafe(16)
    url   = google_auth_url(client_id, state)
    webbrowser.open(url)

    code, err = _run_local_server(timeout=120)
    if err:
        raise ValueError(f"Google authentication failed: {err}")
    if not code:
        raise ValueError("No authorization code received from Google.")

    tokens = google_exchange_code(client_id, client_secret, code)
    if "error" in tokens:
        raise ValueError(f"Token exchange failed: {tokens['error_description']}")

    # Decode id_token to get email
    email = ""
    id_token = tokens.get("id_token", "")
    if id_token:
        try:
            payload = id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            info  = json.loads(base64.b64decode(payload))
            email = info.get("email", "")
        except Exception:
            pass

    tokens["email"]      = email
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
    _save_tokens("google", tokens)
    return email


def google_disconnect():
    _clear_tokens("google")


# ── Microsoft OAuth2 (Authorization Code — browser-based) ────────────────────

_MS_AUTH_URL  = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_MS_SCOPES    = " ".join([
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Mail.ReadBasic",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read",
    "offline_access", "openid", "email",
])


def ms_auth_url(client_id: str, state: str) -> str:
    params = {
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         _MS_SCOPES,
        "state":         state,
        "prompt":        "select_account",
    }
    return _MS_AUTH_URL + "?" + urllib.parse.urlencode(params)


def ms_exchange_code(client_id: str, code: str) -> dict:
    resp = requests.post(_MS_TOKEN_URL, data={
        "client_id":    client_id,
        "code":         code,
        "redirect_uri": REDIRECT_URI,
        "grant_type":   "authorization_code",
        # Public client — no client_secret needed for desktop apps
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()


def ms_refresh(client_id: str, refresh_token: str) -> dict:
    resp = requests.post(_MS_TOKEN_URL, data={
        "client_id":     client_id,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
        "scope":         _MS_SCOPES,
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()


def get_ms_token() -> str:
    """Return a valid Microsoft access token, refreshing if expired."""
    t = _load_tokens("microsoft")
    if not t:
        raise ValueError(
            "Microsoft account not connected.\n\nGo to Settings → Connect Microsoft Account."
        )
    if time.time() < t.get("expires_at", 0) - 60:
        return t["access_token"]

    cid     = get_setting("ms_graph_client_id", "")
    new_t   = ms_refresh(cid, t["refresh_token"])
    if "error" in new_t:
        _clear_tokens("microsoft")
        raise ValueError(f"Token refresh failed: {new_t.get('error_description', new_t)}")
    new_t["email"]      = t.get("email", "")
    new_t["expires_at"] = time.time() + new_t.get("expires_in", 3600)
    _save_tokens("microsoft", new_t)
    return new_t["access_token"]


def is_ms_connected() -> bool:
    try:
        get_ms_token()
        return True
    except Exception:
        return False


def ms_email() -> str:
    t = _load_tokens("microsoft")
    return t.get("email", "") if t else ""


def ms_connect(client_id: str) -> str:
    """
    Full Microsoft OAuth2 browser flow (auth code, not device code).
    Opens the Microsoft login page → user signs in → tokens stored.
    Returns the connected email.
    BLOCKING — run in a QThread worker.
    """
    state = secrets.token_urlsafe(16)
    url   = ms_auth_url(client_id, state)
    webbrowser.open(url)

    code, err = _run_local_server(timeout=120)
    if err:
        raise ValueError(f"Microsoft authentication failed: {err}")
    if not code:
        raise ValueError("No authorization code received from Microsoft.")

    tokens = ms_exchange_code(client_id, code)
    if "error" in tokens:
        raise ValueError(f"Token exchange failed: {tokens.get('error_description', tokens)}")

    # Get email from id_token or Graph API
    email = ""
    id_token = tokens.get("id_token", "")
    if id_token:
        try:
            payload = id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            info  = json.loads(base64.b64decode(payload))
            email = info.get("email") or info.get("preferred_username", "")
        except Exception:
            pass

    tokens["email"]      = email
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
    _save_tokens("microsoft", tokens)
    return email


def ms_disconnect():
    _clear_tokens("microsoft")


# ── XOAUTH2 helper (for IMAP/SMTP) ───────────────────────────────────────────

def xoauth2_string(user_email: str, access_token: str) -> str:
    """Build the base64-encoded XOAUTH2 string for IMAP/SMTP auth."""
    raw = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode()).decode()
