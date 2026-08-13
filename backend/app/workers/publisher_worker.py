import asyncio
import signal
import time
from datetime import datetime, timedelta
import traceback

from googleapiclient.errors import HttpError

from app.db.database import SessionLocal
from app.models.clip import Clip
from app.models.project import Project
from app.models.publication import Publication
from app.models.video import Video
from app.utils.pipeline_logger import log
from app.youtube.config import (
    publisher_poll_interval,
    publisher_max_attempts,
    recovery_interval,
    retry_delay_for_attempt,
    worker_run_once,
    youtube_processing_poll_interval,
)
from app.workers.heartbeat import worker_heartbeat
from app.workers.recovery import recover_stuck_publications
from app.youtube.cleanup import cleanup_clip_files
from app.youtube.publisher import retry
from app.youtube.adapters import get_adapter


TRANSIENT = {"NETWORK_ERROR", "TIMEOUT", "SERVER_ERROR", "QUOTA_EXCEEDED"}
SHUTDOWN = False


def request_shutdown(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True
    log("PUBLISHER", "Worker encerrando.")


def classify_error(error: Exception) -> str:
    text = str(error)

    if isinstance(error, FileNotFoundError) or isinstance(error, ValueError):
        return "VALIDATION_ERROR"
    if "quotaExceeded" in text:
        return "QUOTA_EXCEEDED"
    if "invalid_grant" in text or "unauthorized" in text.lower():
        return "AUTH_REVOKED"
    if isinstance(error, TimeoutError):
        return "TIMEOUT"
    if isinstance(error, HttpError) and getattr(error, "resp", None):
        status = int(error.resp.status)
        if status in {401, 403}:
            return "AUTH_REVOKED" if "insufficient" not in text.lower() else "VALIDATION_ERROR"
        if status >= 500:
            return "SERVER_ERROR"

    return "NETWORK_ERROR"


def next_quota_retry() -> datetime:
    now = datetime.utcnow()
    return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)


def mark_retry(db, publication: Publication, error_type: str, details: str):
    publication.attempts += 1
    publication.error_type = error_type
    publication.error_details = details[:4000]
    publication.updated_at = datetime.utcnow()

    if publication.attempts >= publisher_max_attempts() or error_type not in TRANSIENT:
        publication.status = "FAILED"
        publication.next_retry = None
    else:
        publication.status = "WAITING_RETRY"
        publication.next_retry = (
            next_quota_retry()
            if error_type == "QUOTA_EXCEEDED"
            else datetime.utcnow() + retry_delay_for_attempt(publication.attempts)
        )

    db.commit()


def get_available_publication(db):
    now = datetime.utcnow()

    publication = (
        db.query(Publication)
        .filter(
            (Publication.status == "PENDING")
            | (
                (Publication.status == "WAITING_RETRY")
                & (Publication.next_retry <= now)
            )
        )
        .order_by(Publication.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if publication:
        publication.status = "UPLOADING"
        publication.updated_at = now
        db.commit()
        db.refresh(publication)

    return publication


def process_publication(db, publication: Publication):
    clip = publication.clip
    adapter = get_adapter(publication.platform)

    if not clip or clip.status != "COMPLETED":
        raise ValueError("Clip invalido para publicacao.")

    if not publication.platform_post_id:
        log("PUBLISHER", f"Upload iniciado publication={publication.id}")
        metadata = retry(lambda: asyncio.run(adapter.metadata(clip)))
        video_id = retry(adapter.upload, clip, metadata)

        publication.platform_post_id = video_id
        publication.status = "PROCESSING"
        publication.updated_at = datetime.utcnow()
        db.commit()
        log("PUBLISHER", f"videoId recebido publication={publication.id} videoId={video_id}")
    else:
        video_id = publication.platform_post_id
        publication.status = "PROCESSING"
        publication.updated_at = datetime.utcnow()
        db.commit()

    log("PUBLISHER", f"Processing iniciado publication={publication.id}")

    while True:
        status = retry(adapter.processing_status, publication)

        if status.get("processing_status") != "processing":
            break

        time.sleep(youtube_processing_poll_interval())

    if status.get("processing_status") == "succeeded":
        log("PUBLISHER", f"Processing concluido publication={publication.id}")
        if publication.platform == "YOUTUBE" and not publication.thumbnail_uploaded_at:
            retry(adapter.thumbnail, publication, clip)
            publication.thumbnail_uploaded_at = datetime.utcnow()
            log("PUBLISHER", f"Thumbnail enviada publication={publication.id}")
        publication.status = "PUBLISHED"
        publication.published_at = datetime.utcnow()
        publication.updated_at = datetime.utcnow()
        db.commit()
        cleanup_clip_files(clip)

        url = f"https://www.youtube.com/watch?v={video_id}"
        log("YOUTUBE", f"Clip {clip.id} publicado. videoId={video_id} status=PUBLISHED url={url}")
        return

    if status.get("processing_status") in {"failed", "terminated"}:
        raise RuntimeError(f"Processing falhou: {status}")

    publication.status = "WAITING_RETRY"
    publication.next_retry = datetime.utcnow() + retry_delay_for_attempt(publication.attempts + 1)
    publication.updated_at = datetime.utcnow()
    db.commit()


def run_once() -> bool:
    db = SessionLocal()

    try:
        worker_heartbeat()
        publication = get_available_publication(db)

        if not publication:
            return False

        log("PUBLISHER", f"Publication encontrada {publication.id}")
        log("PUBLISHER", f"Publication iniciada {publication.id}")

        try:
            process_publication(db, publication)
        except Exception as e:
            mark_retry(db, publication, classify_error(e), traceback.format_exc())
            log("PUBLISHER", f"Retry agendado publication={publication.id} status={publication.status}")

        return True

    finally:
        db.close()


def main():
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    log("PUBLISHER", "Worker iniciado")
    last_recovery = 0

    if worker_run_once():
        run_once()
        log("PUBLISHER", "Worker encerrado")
        return

    while not SHUTDOWN:
        worker_heartbeat()
        found = run_once()
        now = time.time()

        if now - last_recovery >= recovery_interval():
            db = SessionLocal()
            try:
                count = recover_stuck_publications(db)
                log("RECOVERY", f"Recovery executado count={count}")
            finally:
                db.close()
            last_recovery = now

        if not found:
            log("PUBLISHER", "Worker aguardando tarefas")
            time.sleep(publisher_poll_interval())

    log("PUBLISHER", "Worker encerrado")


if __name__ == "__main__":
    main()
