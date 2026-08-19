import tempfile
import unittest
from datetime import datetime
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
            state_file = f"{tmp}/state.json"
            with patch.object(auth, "STATE_FILE", SimpleNamespace(exists=lambda: False)):
                with self.assertRaises(MismatchingStateError):
                    auth.save_credentials_from_callback("http://localhost:8000/youtube/callback", "http://localhost")

    def test_worker_credentials_require_saved_token(self):
        with patch.object(auth, "TOKEN_FILE", SimpleNamespace(exists=lambda: False)):
            with self.assertRaisesRegex(RuntimeError, "AUTH_REQUIRED"):
                auth.get_credentials()


if __name__ == "__main__":
    unittest.main()
