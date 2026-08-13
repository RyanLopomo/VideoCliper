from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


BASE_DIR = Path(__file__).resolve().parent

CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def get_credentials():
    credentials = None

    # Reutiliza o token salvo anteriormente
    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES,
        )
        if not credentials.has_scopes(SCOPES):
            TOKEN_FILE.unlink()
            credentials = None

    # Token expirado, mas com refresh token disponível
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    # Primeira autenticação
    if not credentials or not credentials.valid:

        if not CLIENT_SECRET_FILE.exists():
            raise FileNotFoundError(
                f"Credencial não encontrada: {CLIENT_SECRET_FILE}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_FILE),
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=0
        )

        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    return credentials
