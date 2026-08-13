import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.clip_finder import normalize_clips
from app.workers import publisher_worker
from app.workers.heartbeat import last_worker_heartbeat, worker_heartbeat
from app.workers.recovery import recover_stuck_publications
from app.youtube.adapters import TikTokAdapter, YouTubeAdapter, get_adapter
from app.youtube.cleanup import cleanup_clip_files
from app.youtube.validator import normalize_metadata


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self, **kwargs):
        return self

    def all(self):
        return self.items

    def first(self):
        return self.items[0] if self.items else None

    def count(self):
        return len(self.items)


class FakeDB:
    def __init__(self, items):
        self.items = items
        self.commits = 0

    def query(self, model):
        return FakeQuery(self.items)

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        return None


def pub(status="PENDING", platform_post_id=None, attempts=0):
    clip = SimpleNamespace(id=1, status="COMPLETED", clip_path="video.mp4", subtitle_path="clip.srt", thumbnail_path="thumb.jpg")
    return SimpleNamespace(
        id=1, clip=clip, clip_id=1, platform="YOUTUBE", status=status, error_type=None,
        error_details=None, attempts=attempts, next_retry=None, platform_post_id=platform_post_id,
        created_at=datetime.utcnow() - timedelta(hours=2), updated_at=datetime.utcnow() - timedelta(hours=2),
        published_at=None, thumbnail_uploaded_at=None,
    )


def transcript():
    return {"segments": [
        {"start": 0.0, "end": 8.0, "text": "Intro curta."},
        {"start": 8.5, "end": 24.0, "text": "Essa dica importante resolve o problema."},
        {"start": 25.0, "end": 43.0, "text": "O resultado final fica melhor."},
        {"start": 44.0, "end": 64.0, "text": "Conclusao natural da ideia."},
    ]}


class PhaseTests(unittest.TestCase):
    def test_phase_a_pipeline_worker_retry_recovery_cleanup_idempotency(self):
        p = pub()

        async def fake_metadata(path):
            return {"title": "Titulo", "description": "Desc", "tags": []}

        with patch.object(publisher_worker, "retry", side_effect=lambda fn, *a, **k: fn(*a, **k)), \
            patch("app.youtube.adapters.generate_metadata", fake_metadata), \
            patch("app.youtube.adapters.upload_video", side_effect=lambda **kw: "yt_1"), \
            patch("app.youtube.adapters.get_video_status", side_effect=lambda video_id: {"processing_status": "succeeded"}), \
            patch("app.youtube.adapters.upload_thumbnail", side_effect=lambda video_id, path: {"ok": True}), \
            patch.object(publisher_worker, "cleanup_clip_files", side_effect=lambda clip: None):
            publisher_worker.process_publication(FakeDB([p]), p)

        self.assertEqual(p.status, "PUBLISHED")
        self.assertEqual(p.platform_post_id, "yt_1")
        self.assertTrue(p.thumbnail_uploaded_at)

        existing = pub("PROCESSING", "yt_existing")
        with patch.object(publisher_worker, "retry", side_effect=lambda fn, *a, **k: fn(*a, **k)), \
            patch("app.youtube.adapters.upload_video", side_effect=AssertionError()), \
            patch("app.youtube.adapters.get_video_status", side_effect=lambda video_id: {"processing_status": "succeeded"}), \
            patch("app.youtube.adapters.upload_thumbnail", side_effect=lambda video_id, path: {"ok": True}), \
            patch.object(publisher_worker, "cleanup_clip_files", side_effect=lambda clip: None):
            publisher_worker.process_publication(FakeDB([existing]), existing)
        self.assertEqual(existing.status, "PUBLISHED")

        stuck = pub("UPLOADING")
        recover_stuck_publications(FakeDB([stuck]))
        self.assertIn(stuck.status, {"WAITING_RETRY", "FAILED"})

        err = pub()
        publisher_worker.mark_retry(FakeDB([err]), err, "NETWORK_ERROR", "x")
        self.assertEqual(err.status, "WAITING_RETRY")
        self.assertTrue(err.next_retry)

        auth = pub()
        publisher_worker.mark_retry(FakeDB([auth]), auth, "AUTH_REVOKED", "x")
        self.assertEqual(auth.status, "FAILED")

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            final = tmp / "clip_final.mp4"
            srt = tmp / "clip.srt"
            thumb = tmp / "thumb.jpg"
            raw = tmp / "clip.mp4"
            for f in [final, srt, thumb, raw]:
                f.write_text("x")
            cleanup_clip_files(SimpleNamespace(clip_path=str(final), subtitle_path=str(srt), thumbnail_path=str(thumb)))
            self.assertTrue(final.exists())
            self.assertFalse(srt.exists())
            self.assertFalse(thumb.exists())
            self.assertFalse(raw.exists())

    def test_phase_b_quality(self):
        clips = normalize_clips([
            {"start_time": 9.0, "end_time": 42.0, "title": ""},
            {"start_time": 10.0, "end_time": 41.0, "title": "duplicado"},
            {"start_time": 0.0, "end_time": 5.0, "title": "curto"},
        ], transcript())
        self.assertTrue(clips)
        self.assertLessEqual(clips[0]["end_time"] - clips[0]["start_time"], 60)
        self.assertGreaterEqual(clips[0]["end_time"] - clips[0]["start_time"], 15)
        self.assertIn("score", clips[0])
        self.assertEqual(len(clips), 1)
        self.assertTrue(clips[0]["title"])

    def test_phase_c_youtube_metadata_quota_processing_thumbnail(self):
        metadata = normalize_metadata({"title": "x" * 120, "description": "d", "tags": ["a", "a"], "privacyStatus": "public"})
        self.assertEqual(len(metadata["title"]), 100)
        self.assertEqual(metadata["tags"], ["a"])
        self.assertTrue(metadata["category"])
        self.assertEqual(metadata["privacyStatus"], "public")
        self.assertEqual(publisher_worker.classify_error(RuntimeError("quotaExceeded")), "QUOTA_EXCEEDED")
        self.assertEqual(publisher_worker.classify_error(RuntimeError("invalid_grant")), "AUTH_REVOKED")

    def test_phase_d_adapters(self):
        self.assertIsInstance(get_adapter("YOUTUBE"), YouTubeAdapter)
        self.assertIsInstance(get_adapter("TIKTOK"), TikTokAdapter)
        os.environ.pop("TIKTOK_ENABLED", None)
        with self.assertRaises(RuntimeError):
            get_adapter("TIKTOK").upload(SimpleNamespace(id=1), {})
        os.environ["TIKTOK_ENABLED"] = "true"
        try:
            self.assertEqual(get_adapter("TIKTOK").upload(SimpleNamespace(id=2), {}), "tiktok_fake_2")
        finally:
            os.environ.pop("TIKTOK_ENABLED", None)

    def test_phase_e_health_metrics_startup_shutdown(self):
        worker_heartbeat()
        self.assertTrue(last_worker_heartbeat())
        publisher_worker.request_shutdown(None, None)
        self.assertTrue(publisher_worker.SHUTDOWN)
        self.assertIn("postgres-data:/var/lib/postgresql/data", Path("docker-compose.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
