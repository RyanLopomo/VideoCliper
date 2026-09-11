import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.api.projects import delete_project
from app.api.videos import pause_video, restart_video, resume_video, start_video, validate_video_url


class Query:
    def __init__(self, item):
        self.item = item

    def filter(self, *args):
        return self

    def first(self):
        return self.item


class DB:
    def __init__(self, item):
        self.item = item
        self.deleted = None

    def query(self, model):
        return Query(self.item)

    def commit(self):
        pass

    def refresh(self, item):
        pass

    def delete(self, item):
        self.deleted = item


class PipelineControlTest(unittest.TestCase):
    def test_pause_resume_start(self):
        video = SimpleNamespace(id=1, status="PROCESSING")
        db = DB(video)
        self.assertEqual(pause_video(1, db).status, "PAUSED")
        with patch("app.api.videos.enqueue_video_processing") as enqueue:
            self.assertEqual(resume_video(1, db).status, "PROCESSING")
            enqueue.assert_called_once_with(1)
        video.status = "PENDING"
        with patch("app.api.videos.enqueue_video_processing") as enqueue:
            start_video(1, db)
            enqueue.assert_called_once_with(1)

    def test_duplicate_resume_rejected(self):
        with self.assertRaises(HTTPException):
            resume_video(1, DB(SimpleNamespace(id=1, status="PROCESSING")))

    def test_restart_resets_state(self):
        video = SimpleNamespace(
            id=1,
            project_id=1,
            status="FAILED",
            processing_stage="FAILED",
            last_completed_clip=2,
            error_message="x",
            clips=[],
        )
        with patch("app.api.videos.enqueue_video_processing") as enqueue:
            restart_video(1, DB(video))
            enqueue.assert_called_once_with(1)
        self.assertEqual(video.status, "PENDING")
        self.assertEqual(video.processing_stage, "PENDING")
        self.assertEqual(video.last_completed_clip, 0)
        self.assertIsNone(video.error_message)

    def test_url_validation(self):
        self.assertEqual(validate_video_url(" https://example.com/v "), "https://example.com/v")
        with self.assertRaises(HTTPException):
            validate_video_url("file:///tmp/video.mp4")

    def test_delete_project(self):
        project = SimpleNamespace(id=1)
        db = DB(project)
        with patch("app.api.projects.Path.exists", return_value=False):
            self.assertEqual(delete_project(1, db), {"ok": True})
        self.assertIs(db.deleted, project)


if __name__ == "__main__":
    unittest.main()
