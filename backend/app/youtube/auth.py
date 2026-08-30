import json
import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import InsecureTransportError, MismatchingStateError


BASE_DIR = Path(__file__).resolve().parent

CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"
STATE_FILE = BASE_DIR / "oauth_state.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def get_credentials():
    credentials = get_saved_credentials()
    if not credentials:
        raise RuntimeError("AUTH_REQUIRED")
    return credentials

def get_saved_credentials():
    if not TOKEN_FILE.exists():
        return None

    try:
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except (ValueError, GoogleAuthError):
        return None

    if not credentials.has_scopes(SCOPES):
        TOKEN_FILE.unlink()
        return None

    if (credentials.expired or not credentials.valid) and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
        except GoogleAuthError:
            return None

    return credentials if credentials.valid else None


def build_oauth_flow(redirect_uri: str) -> Flow:
    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(f"Credencial nao encontrada: {CLIENT_SECRET_FILE}")

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow


def _allow_local_http(redirect_uri: str):
    parsed = urlparse(redirect_uri)
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _save_state(state: str, redirect_uri: str):
    STATE_FILE.write_text(json.dumps({"state": state, "redirect_uri": redirect_uri}), encoding="utf-8")


def _load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def authorization_url(redirect_uri: str) -> str:
    _allow_local_http(redirect_uri)
    flow = build_oauth_flow(redirect_uri)
    state = secrets.token_urlsafe(32)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        state=state,
    )
    _save_state(state, redirect_uri)
    return url


def save_credentials_from_callback(redirect_uri: str, authorization_response: str):
    _allow_local_http(redirect_uri)
    saved_oauth = _load_state()
    state = saved_oauth.get("state") if saved_oauth else None
    saved_redirect_uri = saved_oauth.get("redirect_uri") if saved_oauth else None
    callback_state = parse_qs(urlparse(authorization_response).query).get("state", [None])[0]
    if not state or callback_state != state or not saved_redirect_uri:
        raise MismatchingStateError()
    if redirect_uri != saved_redirect_uri:
        redirect_uri = saved_redirect_uri

    previous_refresh_token = None
    if TOKEN_FILE.exists():
        try:
            previous_refresh_token = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES).refresh_token
        except (ValueError, GoogleAuthError):
            previous_refresh_token = None

    flow = build_oauth_flow(redirect_uri)
    flow.oauth2session.state = state
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials
    if previous_refresh_token and not credentials.refresh_token:
        credentials.refresh_token = previous_refresh_token
    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return credentials


def disconnect_credentials():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
