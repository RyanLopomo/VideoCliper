import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.youtube.publication_queue import enqueue_publication
from app.youtube.shorts import is_short_format, youtube_upload_path_for_clip
from app.youtube.validator import normalize_metadata


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class DB:
    def __init__(self):
        self.rows = []

    def query(self, model):
        return Query(self.rows)

    def add(self, item):
        item.id = len(self.rows) + 1
        self.rows.append(item)

    def commit(self):
        pass

    def refresh(self, item):
        pass


class ShortsFlowTest(unittest.TestCase):
    def test_public_privacy_default(self):
        self.assertEqual(normalize_metadata({"title": "Titulo"})["privacyStatus"], "public")

    def test_vertical_or_square_is_short_format(self):
        self.assertTrue(is_short_format(1080, 1920))
        self.assertTrue(is_short_format(1080, 1080))
        self.assertFalse(is_short_format(1920, 1080))

    def test_long_clip_is_not_uploaded_as_short(self):
        clip = SimpleNamespace(id=1, clip_path="clip.mp4", start_time=0, end_time=181)
        with patch("app.youtube.shorts.probe_video", return_value=(1080, 1920, 181)):
            with self.assertRaises(ValueError):
                youtube_upload_path_for_clip(clip)

    def test_horizontal_clip_gets_publication_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "clip_final.mp4"
            source.write_bytes(b"x")
            clip = SimpleNamespace(id=1, clip_path=str(source), start_time=0, end_time=60)
            with patch("app.youtube.shorts.probe_video", return_value=(1920, 1080, 60)), \
                    patch("app.youtube.shorts.subprocess.run") as run:
                run.return_value = None
                output = Path(youtube_upload_path_for_clip(clip))
            self.assertEqual(output.name, "clip_final_youtube_short.mp4")

    def test_enqueue_publication_never_duplicates_clip_platform(self):
        db = DB()
        clip = SimpleNamespace(id=1)
        first = enqueue_publication(db, clip)
        first.status = "FAILED"
        second = enqueue_publication(db, clip)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(db.rows), 1)


if __name__ == "__main__":
    unittest.main()
