from datetime import datetime, timedelta

from app.db.database import SessionLocal
from app.models.publication import Publication
from app.services.notifications import notify
from app.services.publication_scheduler import (
    reschedule_publication_cascade,
)
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
    log(
        "RECOVERY",
        "missed_slot_auto_reschedule_desabilitado "
        f"now={now.isoformat()} regra=scheduled_at_vencido_deve_ser_processado_pelo_publisher",
    )

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

        notify(
            db,
            event_key=f"publication:{publication.id}:recovery:{publication.attempts}",
            type="RECOVERY",
            title="Publicacao recuperada",
            message=f"Etapa: {publication.error_details}. Status: {publication.status}.",
            clip_id=publication.clip_id,
            publication_id=publication.id,
            platform=publication.platform,
        )

        count += 1
        if publication.status == "WAITING_RETRY" and not publication.platform_post_id:
            count += reschedule_publication_cascade(db, publication, reason="RECOVERY_TIMEOUT", now=now)

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
        notify(
            db,
            event_key=f"publication:{publication.id}:recovery_next_retry",
            type="RECOVERY",
            title="Nova tentativa reagendada",
            message=f"Nova tentativa em {publication.next_retry.isoformat()}.",
            clip_id=publication.clip_id,
            publication_id=publication.id,
            platform=publication.platform,
        )
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
