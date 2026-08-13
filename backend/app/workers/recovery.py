from datetime import datetime, timedelta

from app.db.database import SessionLocal
from app.models.publication import Publication
from app.utils.pipeline_logger import log
from app.youtube.config import (
    publisher_max_attempts,
    publisher_processing_timeout_minutes,
    publisher_upload_timeout_minutes,
    retry_delay_for_attempt,
)
from app.workers.heartbeat import recovery_heartbeat


def recover_stuck_publications(db) -> int:
    now = datetime.utcnow()
    count = 0
    recovery_heartbeat()

    stuck = (
        db.query(Publication)
        .filter(Publication.status.in_(["UPLOADING", "PROCESSING"]))
        .all()
    )

    for publication in stuck:
        timeout = (
            publisher_upload_timeout_minutes()
            if publication.status == "UPLOADING"
            else publisher_processing_timeout_minutes()
        )

        updated_at = publication.updated_at or publication.created_at

        if updated_at and updated_at > now - timedelta(minutes=timeout):
            continue

        publication.attempts += 1
        publication.error_type = "RECOVERY_TIMEOUT"
        publication.error_details = f"Recovered from stuck {publication.status}"
        publication.updated_at = now

        if publication.attempts >= publisher_max_attempts():
            publication.status = "FAILED"
            publication.next_retry = None
        else:
            publication.status = "WAITING_RETRY"
            publication.next_retry = now + retry_delay_for_attempt(publication.attempts)

        count += 1

    invalid_retry = (
        db.query(Publication)
        .filter(
            Publication.status == "WAITING_RETRY",
            Publication.next_retry.is_(None),
        )
        .all()
    )

    for publication in invalid_retry:
        publication.next_retry = now + retry_delay_for_attempt(publication.attempts + 1)
        publication.updated_at = now
        count += 1

    db.commit()
    return count


def main():
    db = SessionLocal()

    try:
        count = recover_stuck_publications(db)
        log("RECOVERY", f"Publicacoes recuperadas: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
