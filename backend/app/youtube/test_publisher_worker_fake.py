from datetime import datetime, timedelta
from unittest.mock import patch

from app.models.clip import Clip
from app.models.publication import Publication
from app.workers.publisher_worker import classify_error, mark_retry, process_publication, redact_secret_text


class DB:
    def commit(self):
        pass


class FakeAdapter:
    def __init__(self):
        self.upload_called = False

    async def metadata(self, clip):
        return {"title": "t", "description": "d", "tags": []}

    def upload(self, clip, metadata):
        self.upload_called = True
        return "abc"

    def processing_status(self, publication):
        return {"processing_status": "succeeded"}

    def thumbnail(self, publication, clip):
        return {}


def publication(status="PENDING", platform_post_id=None):
    pub = Publication(
        id=1,
        platform="YOUTUBE",
        status=status,
        attempts=0,
        platform_post_id=platform_post_id,
        updated_at=datetime.utcnow() - timedelta(hours=4),
    )
    pub.clip = Clip(
        id=1,
        status="COMPLETED",
        clip_path="video.mp4",
        subtitle_path="clip.srt",
        thumbnail_path="thumb.jpg",
    )
    return pub


def main():
    db = DB()
    pub = publication()
    adapter = FakeAdapter()

    with patch("app.workers.publisher_worker.get_adapter", return_value=adapter), \
        patch("app.workers.publisher_worker.cleanup_clip_files"):
        process_publication(db, pub)

    print(pub.status)
    print(pub.platform_post_id)

    pub = publication()
    mark_retry(db, pub, "NETWORK_ERROR", "x")
    print(pub.status)

    pub = publication()
    mark_retry(db, pub, "QUOTA_EXCEEDED", "quotaExceeded")
    print(pub.status, pub.error_type)

    pub = publication()
    mark_retry(db, pub, "AUTH_REVOKED", "invalid_grant")
    print(pub.status)

    pub = publication(platform_post_id="abc")
    adapter = FakeAdapter()
    with patch("app.workers.publisher_worker.get_adapter", return_value=adapter), \
        patch("app.workers.publisher_worker.cleanup_clip_files"):
        process_publication(db, pub)
        print(adapter.upload_called)

    print(classify_error(FileNotFoundError("x")))
    print(classify_error(RuntimeError("AUTH_REQUIRED")))
    print("secret" not in redact_secret_text("access_token: secret refresh_token: secret"))


if __name__ == "__main__":
    main()
