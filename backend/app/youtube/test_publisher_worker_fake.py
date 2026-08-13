from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.models.publication import Publication
from app.workers.publisher_worker import classify_error, mark_retry, process_publication


async def fake_metadata(path):
    return {"title": "t", "description": "d", "tags": []}


class DB:
    def commit(self):
        pass


def publication(status="PENDING", platform_post_id=None):
    pub = Publication(
        id=1,
        status=status,
        attempts=0,
        platform_post_id=platform_post_id,
        updated_at=datetime.utcnow() - timedelta(hours=4),
    )
    pub.clip = SimpleNamespace(
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

    with patch("app.workers.publisher_worker.generate_metadata", fake_metadata), \
        patch("app.workers.publisher_worker.upload_video", return_value="abc"), \
        patch("app.workers.publisher_worker.get_video_status", return_value={"processing_status": "succeeded"}), \
        patch("app.workers.publisher_worker.upload_thumbnail", return_value={}):
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
    with patch("app.workers.publisher_worker.get_video_status", return_value={"processing_status": "succeeded"}), \
        patch("app.workers.publisher_worker.upload_thumbnail", return_value={}), \
        patch("app.workers.publisher_worker.upload_video") as upload:
        process_publication(db, pub)
        print(upload.called)

    print(classify_error(FileNotFoundError("x")))


if __name__ == "__main__":
    main()
