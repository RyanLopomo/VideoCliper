from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from app.models.publication import Publication
from app.services.publication_scheduler import reschedule_missed_publications
from app.workers.publisher_worker import get_available_publication


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class DB:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    def query(self, model):
        return Query(self.rows)

    def commit(self):
        self.committed = True

    def refresh(self, item):
        pass


class QueryForbiddenDB:
    def query(self, model):
        raise AssertionError("MISSED_SLOT default path must not query publications")


class ScheduledPublicationDueTest(unittest.TestCase):
    def test_due_scheduled_publication_is_claimed_for_upload_now(self):
        scheduled_at = datetime.utcnow() - timedelta(minutes=1)
        publication = Publication(
            id=1,
            clip_id=1,
            platform="YOUTUBE",
            status="SCHEDULED",
            scheduled_at=scheduled_at,
            attempts=0,
        )
        db = DB([publication])

        with patch("app.workers.publisher_worker.manual_upload_counts_toward_daily_limit", return_value=True), \
            patch("app.workers.publisher_worker.notify"):
            claimed = get_available_publication(db)

        self.assertEqual(claimed.id, publication.id)
        self.assertEqual(claimed.status, "UPLOADING")
        self.assertEqual(claimed.scheduled_at, scheduled_at)
        self.assertTrue(db.committed)

    def test_missed_slot_does_not_reschedule_without_explicit_policy(self):
        shifted = reschedule_missed_publications(QueryForbiddenDB(), datetime.utcnow())

        self.assertEqual(shifted, 0)


if __name__ == "__main__":
    unittest.main()
