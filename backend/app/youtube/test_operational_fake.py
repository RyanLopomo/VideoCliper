from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from app.models.publication import Publication
from app.workers.heartbeat import (
    last_worker_heartbeat,
    worker_heartbeat,
)
from app.workers.publisher_worker import (
    classify_error,
    mark_retry,
    process_publication,
)
from app.youtube.cleanup import cleanup_clip_files


class DB:
    def commit(self):
        pass


async def fake_metadata(path):
    return {"title": "t", "description": "d", "tags": []}


def pub(status="PENDING", post_id=None):
    item = Publication(
        id=1,
        status=status,
        attempts=0,
        platform_post_id=post_id,
        updated_at=datetime.utcnow() - timedelta(hours=1),
    )
    item.clip = SimpleNamespace(
        id=1,
        status="COMPLETED",
        clip_path="video.mp4",
        subtitle_path="clip.srt",
        thumbnail_path="thumb.jpg",
    )
    return item


def main():
    db = DB()

    item = pub()
    with patch("app.workers.publisher_worker.generate_metadata", fake_metadata), \
        patch("app.workers.publisher_worker.upload_video", return_value="vid"), \
        patch("app.workers.publisher_worker.get_video_status", return_value={"processing_status": "succeeded"}), \
        patch("app.workers.publisher_worker.upload_thumbnail", return_value={}), \
        patch("app.workers.publisher_worker.cleanup_clip_files"):
        process_publication(db, item)
    print(item.status)

    item = pub(post_id="vid")
    with patch("app.workers.publisher_worker.get_video_status", return_value={"processing_status": "succeeded"}), \
        patch("app.workers.publisher_worker.upload_thumbnail", return_value={}), \
        patch("app.workers.publisher_worker.upload_video") as upload, \
        patch("app.workers.publisher_worker.cleanup_clip_files"):
        process_publication(db, item)
        print(upload.called)

    item = pub(status="PUBLISHED")
    print(item.status)

    item = pub()
    mark_retry(db, item, "NETWORK_ERROR", "x")
    print(item.status)

    item = pub()
    mark_retry(db, item, "QUOTA_EXCEEDED", "quotaExceeded")
    print(item.error_type)

    item = pub()
    mark_retry(db, item, "AUTH_REVOKED", "invalid_grant")
    print(item.status)

    worker_heartbeat()
    print(last_worker_heartbeat() is not None)
    print(classify_error(FileNotFoundError("x")))

    with patch("app.youtube.cleanup.cleanup_after_publish", return_value=False):
        cleanup_clip_files(pub().clip)
        print("cleanup_off")

    with tempfile.TemporaryDirectory() as tmp:
        srt = Path(tmp) / "clip.srt"
        thumb = Path(tmp) / "thumb.jpg"
        mp4 = Path(tmp) / "clip_final.mp4"
        mid = Path(tmp) / "clip.mp4"

        for path in [srt, thumb, mp4, mid]:
            path.write_text("x", encoding="utf-8")

        clip = SimpleNamespace(
            subtitle_path=str(srt),
            thumbnail_path=str(thumb),
            clip_path=str(mp4),
        )

        with patch("app.youtube.cleanup.cleanup_after_publish", return_value=True):
            cleanup_clip_files(clip)

        print(srt.exists(), thumb.exists(), mp4.exists(), mid.exists())


if __name__ == "__main__":
    main()
