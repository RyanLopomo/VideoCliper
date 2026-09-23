import unittest
import sys
import types
from types import SimpleNamespace

sys.modules["app.services.transcriber"] = types.SimpleNamespace(
    transcribe_audio=lambda *args, **kwargs: None,
)

from app.pipeline import stages


class Query:
    def __init__(self, items):
        self.items = items

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.items


class DB:
    def __init__(self, items):
        self.items = items
        self.added = []
        self.commits = 0

    def query(self, model):
        return Query(self.items)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        return None


class PipelineLoopProtectionTest(unittest.TestCase):
    def test_create_clip_record_reuses_existing_time_window(self):
        existing = SimpleNamespace(
            id=7,
            video_id=1,
            start_time=10.0,
            end_time=40.0,
            status="COMPLETED",
            error_message=None,
        )
        ctx = SimpleNamespace(
            db=DB([existing]),
            video=SimpleNamespace(id=1, editing_style="AUTO"),
        )

        clip = stages.create_clip_record(
            ctx,
            {"start_time": 10.02, "end_time": 40.01, "title": "Duplicado"},
        )

        self.assertIs(clip, existing)
        self.assertEqual(ctx.db.added, [])


if __name__ == "__main__":
    unittest.main()
