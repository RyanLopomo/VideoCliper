import unittest
import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from googleapiclient.errors import HttpError

from app.api.publications import (
    PublicationCreate,
    PublicationScheduleUpdate,
    cancel_publication,
    create_publication,
    sync_publication_with_youtube,
    update_publication_schedule,
)
from app.models.clip import Clip
from app.models.publication import Publication
from app.services.publication_scheduler import build_schedule_plan, normalize_times
from app.services.video_publication_plan import apply_video_publication_plan, configured_times, set_video_publication_plan
from app.workers.publisher_worker import classify_error, format_error_details, schedule_slot_available
from app.youtube.metadata import generate_metadata
from app.youtube.publication_queue import enqueue_publication
from app.youtube.uploader import build_video_insert_body


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)


class DB:
    def __init__(self, clip=None, publication=None):
        self.clip = clip or SimpleNamespace(id=1, title="Clip")
        self.publications = [] if publication is None else [publication]

    def get(self, model, id):
        if model.__name__ == "Clip":
            return self.clip
        return self.publications[0] if self.publications else None

    def query(self, model):
        return Query(self.publications)

    def add(self, item):
        item.id = len(self.publications) + 1
        self.publications.append(item)

    def commit(self):
        pass

    def refresh(self, item):
        pass


class VideoPlanDB:
    def __init__(self, clips):
        self.clips = clips
        self.commits = 0

    def query(self, model):
        if model is Clip:
            return Query(self.clips)
        return Query([])

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        pass


class PublicationScheduleTest(unittest.TestCase):
    def make_clips(self, total):
        return [SimpleNamespace(id=index + 1, status="COMPLETED", start_time=index) for index in range(total)]

    def test_bulk_plan_30_clips_10_per_day(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(30), 10, "2026-09-07", ["09:00", "13:00", "18:00", "21:00"], now)
        self.assertEqual(plan["estimated_days"], 3)
        self.assertEqual([day["count"] for day in plan["days"]], [10, 10, 10])
        self.assertEqual(len(plan["scheduled"]), 30)

    def test_bulk_plan_17_clips_6_per_day(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(17), 6, "2026-09-07", ["09:00", "13:00", "18:00"], now)
        self.assertEqual(plan["estimated_days"], 3)
        self.assertEqual([day["count"] for day in plan["days"]], [6, 6, 5])

    def test_bulk_plan_12_clips_6_per_day(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(12), 6, "2026-09-07", ["09:00", "13:00"], now)
        self.assertEqual(plan["estimated_days"], 2)
        self.assertEqual([day["count"] for day in plan["days"]], [6, 6])

    def test_bulk_plan_limit_greater_than_clip_count(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(4), 20, "2026-09-07", ["09:00", "18:00"], now)
        self.assertEqual(plan["estimated_days"], 1)
        self.assertEqual(plan["days"][0]["count"], 4)

    def test_bulk_plan_uses_multiple_times(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(5), 5, "2026-09-07", ["09:00", "13:00", "18:00"], now)
        self.assertEqual(plan["days"][0]["times"], ["09:00", "09:01", "13:00", "13:01", "18:00"])
        self.assertEqual(len(set(item["scheduled_at"] for item in plan["scheduled"])), 5)

    def test_today_ignores_past_times(self):
        now = datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(3), 3, "2026-09-06", ["09:00", "13:00", "18:00"], now)
        self.assertEqual(plan["days"][0]["date"], "2026-09-06")
        self.assertEqual(plan["days"][0]["times"], ["18:00", "18:01", "18:02"])

    def test_edit_quantity_recalculates_days(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(12), 4, "2026-09-07", ["09:00", "18:00"], now)
        self.assertEqual([day["count"] for day in plan["days"]], [4, 4, 4])

    def test_edit_hours_recalculates_slots(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(4), 4, "2026-09-07", ["10:00", "20:00"], now)
        self.assertEqual(plan["days"][0]["times"], ["10:00", "10:01", "20:00", "20:01"])

    def test_edit_date_recalculates_first_day(self):
        now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
        plan = build_schedule_plan(self.make_clips(5), 10, "2026-09-09", ["09:00", "18:00"], now)
        self.assertEqual(plan["days"][0]["date"], "2026-09-09")

    def test_duplicate_times_are_rejected(self):
        with self.assertRaises(HTTPException):
            normalize_times(["09:00", "09:00"])

    def test_pre_upload_plan_is_saved_and_applied_after_real_clip_total(self):
        video = SimpleNamespace(id=1)
        set_video_publication_plan(
            video,
            enabled=True,
            max_per_day=6,
            start_date="2026-09-10",
            times=["09:00", "13:00", "18:00"],
            timezone_name="America/Sao_Paulo",
        )
        self.assertTrue(video.publication_plan_enabled)
        self.assertEqual(configured_times(video), ["09:00", "13:00", "18:00"])

        clips = [
            SimpleNamespace(id=index + 1, video_id=1, status="COMPLETED", start_time=index)
            for index in range(17)
        ]
        created = []

        def fake_enqueue(db, clip, **kwargs):
            publication = SimpleNamespace(id=len(created) + 1, clip_id=clip.id, **kwargs)
            created.append(publication)
            return publication

        with patch("app.services.publication_scheduler.enqueue_publication", side_effect=fake_enqueue), patch("app.services.publication_scheduler.notify"):
            result = apply_video_publication_plan(VideoPlanDB(clips), video)

        self.assertEqual(result["estimated_days"], 3)
        self.assertEqual([day["count"] for day in result["days"]], [6, 6, 5])
        self.assertEqual(len(created), 17)
        self.assertTrue(all(publication.status == "SCHEDULED" for publication in created))

    def test_manual_now_creates_pending(self):
        db = DB()
        with patch("app.api.publications.notify"):
            pub = create_publication(PublicationCreate(clip_id=1), db)
        self.assertEqual(pub["status"], "PENDING")
        self.assertTrue(db.publications[0].manual)

    def test_schedule_creates_scheduled(self):
        db = DB()
        when = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with patch("app.api.publications.notify"):
            pub = create_publication(PublicationCreate(clip_id=1, scheduled_at=when), db)
        self.assertEqual(pub["status"], "SCHEDULED")
        self.assertIsNotNone(db.publications[0].scheduled_at)

    def test_past_schedule_rejected(self):
        with self.assertRaises(HTTPException):
            create_publication(PublicationCreate(clip_id=1, scheduled_at="2020-01-01T10:00:00Z"), DB())

    def test_cancel_and_edit_schedule(self):
        publication = Publication(id=1, clip_id=1, platform="YOUTUBE", status="SCHEDULED", scheduled_at=datetime.utcnow() + timedelta(hours=1))
        db = DB(publication=publication)
        new_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        with patch("app.api.publications.ensure_schedule_available"), patch("app.api.publications.ensure_daily_schedule_limit"):
            updated = update_publication_schedule(1, PublicationScheduleUpdate(scheduled_at=new_time), db)
        self.assertEqual(updated["status"], "SCHEDULED")
        cancelled = cancel_publication(1, db)
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_edit_schedule_updates_youtube_when_video_exists(self):
        publication = Publication(
            id=1,
            clip_id=1,
            platform="YOUTUBE",
            status="SCHEDULED",
            scheduled_at=datetime.utcnow() + timedelta(hours=1),
            platform_post_id="yt123",
        )
        db = DB(publication=publication)
        new_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        with patch("app.api.publications.ensure_schedule_available"), \
                patch("app.api.publications.ensure_daily_schedule_limit"), \
                patch("app.api.publications.update_youtube_publish_at") as youtube_update:
            update_publication_schedule(1, PublicationScheduleUpdate(scheduled_at=new_time), db)
        youtube_update.assert_called_once()
        self.assertEqual(publication.status, "SCHEDULED")

    def test_edit_schedule_does_not_create_duplicate_publication(self):
        publication = Publication(id=1, clip_id=1, platform="YOUTUBE", status="SCHEDULED", scheduled_at=datetime.utcnow() + timedelta(hours=1))
        db = DB(publication=publication)
        new_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        with patch("app.api.publications.ensure_schedule_available"), patch("app.api.publications.ensure_daily_schedule_limit"):
            update_publication_schedule(1, PublicationScheduleUpdate(scheduled_at=new_time), db)
        self.assertEqual(len(db.publications), 1)

    def test_cancel_schedule_before_upload_only_marks_cancelled(self):
        publication = Publication(id=1, clip_id=1, platform="YOUTUBE", status="SCHEDULED", scheduled_at=datetime.utcnow() + timedelta(hours=1))
        db = DB(publication=publication)
        with patch("app.api.publications.cancel_youtube_publish_at") as youtube_cancel:
            cancelled = cancel_publication(1, db)
        youtube_cancel.assert_not_called()
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_cancel_schedule_after_upload_updates_youtube(self):
        publication = Publication(
            id=1,
            clip_id=1,
            platform="YOUTUBE",
            status="SCHEDULED",
            scheduled_at=datetime.utcnow() + timedelta(hours=1),
            platform_post_id="yt123",
        )
        db = DB(publication=publication)
        with patch("app.api.publications.cancel_youtube_publish_at") as youtube_cancel:
            cancel_publication(1, db)
        youtube_cancel.assert_called_once_with("yt123")
        self.assertEqual(publication.status, "CANCELLED")

    def test_youtube_error_during_schedule_update_keeps_local_schedule(self):
        publication = Publication(
            id=1,
            clip_id=1,
            platform="YOUTUBE",
            status="SCHEDULED",
            scheduled_at=datetime.utcnow() + timedelta(hours=1),
            platform_post_id="yt123",
        )
        db = DB(publication=publication)
        original = publication.scheduled_at
        new_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        with patch("app.api.publications.ensure_schedule_available"), \
                patch("app.api.publications.ensure_daily_schedule_limit"), \
                patch("app.api.publications.update_youtube_publish_at", side_effect=RuntimeError("Falha YouTube")):
            with self.assertRaises(HTTPException):
                update_publication_schedule(1, PublicationScheduleUpdate(scheduled_at=new_time), db)
        self.assertEqual(publication.scheduled_at, original)

    def test_sync_real_youtube_public_status_marks_published(self):
        publication = Publication(
            id=1,
            clip_id=1,
            platform="YOUTUBE",
            status="SCHEDULED",
            scheduled_at=datetime.utcnow() + timedelta(hours=1),
            platform_post_id="yt123",
        )
        db = DB(publication=publication)
        with patch("app.api.publications.get_youtube_publication_state", return_value={
            "exists": True,
            "upload_status": "processed",
            "privacy_status": "public",
            "publish_at": None,
            "published_at": "2026-09-09T21:00:00Z",
        }):
            sync_publication_with_youtube(db, publication)
        self.assertEqual(publication.status, "PUBLISHED")
        self.assertIsNotNone(publication.published_at)

    def test_slots(self):
        self.assertFalse(schedule_slot_available(datetime(2026, 1, 1, 8, 0)))
        self.assertTrue(schedule_slot_available(datetime(2026, 1, 1, 12, 1)))

    def test_youtube_immediate_body_omits_publish_at_and_empty_tags(self):
        body = build_video_insert_body("Titulo", "Descricao", [], "public", None)
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertNotIn("publishAt", body["status"])
        self.assertNotIn("tags", body["snippet"])

    def test_youtube_future_body_uses_private_and_publish_at(self):
        body = build_video_insert_body(
            "Titulo",
            "Descricao",
            ["tag"],
            "public",
            "2026-09-10T12:00:00Z",
        )
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2026-09-10T12:00:00Z")

    def test_youtube_invalid_publish_at_rejected(self):
        with self.assertRaises(ValueError):
            build_video_insert_body("Titulo", "Descricao", [], "public", "not-a-date")

    def test_youtube_invalid_title_rejected(self):
        with self.assertRaises(ValueError):
            build_video_insert_body("", "Descricao", [], "public", None)

    def test_youtube_http_error_preserves_real_reason(self):
        class Response:
            status = 400
            reason = "Bad Request"

        error = HttpError(
            Response(),
            b'{"error":{"code":400,"message":"Invalid publishAt","errors":[{"domain":"youtube.video","reason":"invalidPublishAt","message":"Invalid publishAt"}]}}',
        )
        self.assertEqual(classify_error(error), "VALIDATION_ERROR")
        self.assertIn("invalidPublishAt", format_error_details(error))

    def test_youtube_http_error_with_api_reason_is_not_network_error(self):
        class Response:
            status = 400
            reason = "Bad Request"

        error = HttpError(
            Response(),
            b'{"error":{"code":400,"message":"API error","errors":[{"domain":"youtube.video","reason":"unexpectedReason","message":"API error"}]}}',
        )
        self.assertEqual(classify_error(error), "YOUTUBE_API_ERROR")
        self.assertIn("unexpectedReason", format_error_details(error))

    def test_ollama_runtime_error_is_metadata_error(self):
        error = RuntimeError("O Ollama retornou uma resposta vazia.")
        setattr(error, "axisclip_stage", "metadata")
        self.assertEqual(classify_error(error), "METADATA_ERROR")

    def test_metadata_fallback_when_ai_returns_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            srt = Path(tmp) / "clip.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nTexto real do clip para fallback.\n", encoding="utf-8")
            with patch("app.youtube.metadata.generate", return_value='{"title": "Titulo quebrado'):
                metadata = asyncio.run(generate_metadata(str(srt)))
        self.assertTrue(metadata["title"])
        self.assertLessEqual(len(metadata["title"]), 100)
        self.assertEqual(metadata["tags"], [])

    def test_metadata_fallback_when_ai_returns_empty_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            srt = Path(tmp) / "clip.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nTexto real do clip para resposta vazia.\n", encoding="utf-8")
            with patch("app.youtube.metadata.generate", side_effect=RuntimeError("O Ollama retornou uma resposta vazia.")):
                metadata = asyncio.run(generate_metadata(str(srt)))
        self.assertIn("Texto", metadata["title"])
        self.assertEqual(metadata["tags"], [])

    def test_reused_failed_publication_clears_old_error(self):
        publication = Publication(
            id=1,
            clip_id=1,
            platform="YOUTUBE",
            status="FAILED",
            error_type="NETWORK_ERROR",
            error_details="old",
            next_retry=datetime.utcnow(),
        )
        db = DB(publication=publication)
        result = enqueue_publication(
            db,
            SimpleNamespace(id=1),
            status="SCHEDULED",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
        )
        self.assertEqual(result.id, 1)
        self.assertEqual(result.status, "SCHEDULED")
        self.assertIsNone(result.error_type)
        self.assertIsNone(result.error_details)
        self.assertIsNone(result.next_retry)


if __name__ == "__main__":
    unittest.main()
