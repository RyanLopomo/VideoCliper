import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from oauthlib.oauth2 import MismatchingStateError

from app.api.publications import serialize_account
from app.youtube import auth
from app.youtube.publication_urls import publication_url


class OAuthPublicationTest(unittest.TestCase):
    def test_publication_urls(self):
        youtube = SimpleNamespace(platform="YOUTUBE", status="PUBLISHED", platform_post_id="abc123")
        tiktok = SimpleNamespace(platform="TIKTOK", status="PUBLISHED", platform_post_id="abc123")
        failed = SimpleNamespace(platform="YOUTUBE", status="FAILED", platform_post_id="abc123")
        missing_id = SimpleNamespace(platform="YOUTUBE", status="PUBLISHED", platform_post_id=None)

        self.assertEqual(publication_url(youtube), "https://www.youtube.com/watch?v=abc123")
        self.assertIsNone(publication_url(tiktok))
        self.assertIsNone(publication_url(failed))
        self.assertIsNone(publication_url(missing_id))

    def test_account_serialization_does_not_expose_credentials(self):
        account = SimpleNamespace(
            id=1,
            platform="YOUTUBE",
            account_name="Canal",
            platform_account_id="channel-1",
            enabled=True,
            is_default=True,
            credential_path="token.json",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        data = serialize_account(account)

        self.assertNotIn("credential_path", data)
        self.assertNotIn("access_token", data)
        self.assertNotIn("refresh_token", data)
        self.assertEqual(data["platform_account_id"], "channel-1")

    def test_callback_without_saved_state_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(auth, "STATE_FILE", SimpleNamespace(exists=lambda: False)):
                with self.assertRaises(MismatchingStateError):
                    auth.save_credentials_from_callback("http://localhost:8000/youtube/callback", "http://localhost")

    def test_authorization_persists_state_and_redirect_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            flow = SimpleNamespace(
                authorization_url=lambda **kwargs: ("http://accounts.google.test/auth", kwargs["state"])
            )
            with patch.object(auth, "STATE_FILE", state_file), \
                    patch.object(auth, "build_oauth_flow", return_value=flow):
                auth.authorization_url("http://localhost:8000/youtube/callback")

            data = state_file.read_text(encoding="utf-8")
            self.assertIn("state", data)
            self.assertIn("http://localhost:8000/youtube/callback", data)

    def test_callback_uses_saved_redirect_uri_for_token_exchange(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(
                '{"state": "abc", "redirect_uri": "http://localhost:8000/youtube/callback"}',
                encoding="utf-8",
            )
            token_file = Path(tmp) / "token.json"
            flow = SimpleNamespace(
                oauth2session=SimpleNamespace(state=None),
                credentials=SimpleNamespace(refresh_token="new-refresh", to_json=lambda: "{}"),
            )
            seen = {}

            def build_flow(redirect_uri):
                seen["redirect_uri"] = redirect_uri
                flow.fetch_token = lambda authorization_response: seen.update(
                    authorization_response=authorization_response
                )
                return flow

            with patch.object(auth, "STATE_FILE", state_file), \
                    patch.object(auth, "TOKEN_FILE", token_file), \
                    patch.object(auth, "build_oauth_flow", side_effect=build_flow):
                auth.save_credentials_from_callback(
                    "http://127.0.0.1:8000/youtube/callback",
                    "http://127.0.0.1:8000/youtube/callback?code=one&state=abc",
                )

            self.assertEqual(seen["redirect_uri"], "http://localhost:8000/youtube/callback")
            self.assertFalse(state_file.exists())

    def test_callback_preserves_previous_refresh_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(
                '{"state": "abc", "redirect_uri": "http://localhost:8000/youtube/callback"}',
                encoding="utf-8",
            )
            token_file = Path(tmp) / "token.json"
            token_file.write_text("{}", encoding="utf-8")
            credentials = SimpleNamespace(refresh_token=None, to_json=lambda: "{}")
            flow = SimpleNamespace(
                oauth2session=SimpleNamespace(state=None),
                credentials=credentials,
                fetch_token=lambda authorization_response: None,
            )
            old_credentials = SimpleNamespace(refresh_token="old-refresh")

            with patch.object(auth, "STATE_FILE", state_file), \
                    patch.object(auth, "TOKEN_FILE", token_file), \
                    patch.object(auth.Credentials, "from_authorized_user_file", return_value=old_credentials), \
                    patch.object(auth, "build_oauth_flow", return_value=flow):
                auth.save_credentials_from_callback(
                    "http://localhost:8000/youtube/callback",
                    "http://localhost:8000/youtube/callback?code=one&state=abc",
                )

            self.assertEqual(credentials.refresh_token, "old-refresh")

    def test_worker_credentials_require_saved_token(self):
        with patch.object(auth, "TOKEN_FILE", SimpleNamespace(exists=lambda: False)):
            with self.assertRaisesRegex(RuntimeError, "AUTH_REQUIRED"):
                auth.get_credentials()


if __name__ == "__main__":
    unittest.main()
