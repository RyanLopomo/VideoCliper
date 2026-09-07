import unittest
import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from googleapiclient.errors import HttpError

from app.api.publications import PublicationCreate, PublicationScheduleUpdate, cancel_publication, create_publication, update_publication_schedule
from app.models.publication import Publication
from app.services.publication_scheduler import build_schedule_plan, normalize_times
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
            "2026-09-07T12:00:00Z",
        )
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2026-09-07T12:00:00Z")

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
