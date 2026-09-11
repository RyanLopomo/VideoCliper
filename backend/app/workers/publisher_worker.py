import asyncio
import inspect
import json
import re
import signal
import time
from datetime import datetime, timedelta, timezone
import traceback
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError
from sqlalchemy import or_

from app.db.database import SessionLocal
from app.db.migrations import run_migrations
from app.models.clip import Clip
from app.models.project import Project
from app.models.publication import Publication
from app.models.video import Video
from app.utils.pipeline_logger import log
from app.services.notifications import notify
from app.youtube.config import (
    publisher_poll_interval,
    publisher_max_attempts,
    max_uploads_per_day,
    manual_upload_counts_toward_daily_limit,
    publish_schedule,
    publish_timezone,
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


TRANSIENT = {"NETWORK_ERROR", "TIMEOUT", "SERVER_ERROR", "QUOTA_EXCEEDED", "METADATA_ERROR", "HTTP_ERROR"}
SHUTDOWN = False
YOUTUBE_VALIDATION_REASONS = {
    "invalidTitle",
    "invalidDescription",
    "invalidTags",
    "invalidPublishAt",
    "invalidCategoryId",
    "invalidVideoMetadata",
    "mediaBodyRequired",
}


def request_shutdown(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True
    log("PUBLISHER", "Worker encerrando.")


def classify_error(error: Exception) -> str:
    text = str(error)
    youtube_error = youtube_error_details(error)
    reason = youtube_error.get("reason")
    http_status = int(youtube_error.get("http_status") or 0)

    if "AUTH_REQUIRED" in text:
        return "AUTH_REVOKED"
    if reason in YOUTUBE_VALIDATION_REASONS:
        return "VALIDATION_ERROR"
    if reason in {"quotaExceeded", "uploadLimitExceeded"}:
        return "QUOTA_EXCEEDED"
    if "ollama" in text.lower() or "metadata" in str(getattr(error, "axisclip_stage", "")).lower():
        return "METADATA_ERROR"
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
        if status in {401, 403} and reason in {"authError", "forbidden", "forbiddenEmbedSetting"}:
            return "AUTH_REVOKED" if "insufficient" not in text.lower() else "VALIDATION_ERROR"
        if status >= 500:
            return "SERVER_ERROR"
        if reason:
            return "YOUTUBE_API_ERROR"
        return "HTTP_ERROR"
    if http_status:
        return "YOUTUBE_API_ERROR" if reason else "HTTP_ERROR"

    return "NETWORK_ERROR"


def youtube_error_details(error: Exception) -> dict:
    if not isinstance(error, HttpError):
        return {}
    details = {"http_status": getattr(getattr(error, "resp", None), "status", None)}
    content = getattr(error, "content", None)
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="ignore")
    if not content:
        return details
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        details["message"] = str(content)[:1000]
        return details

    api_error = payload.get("error") or {}
    errors = api_error.get("errors") or []
    first = errors[0] if errors else {}
    details.update(
        {
            "reason": first.get("reason"),
            "message": first.get("message") or api_error.get("message"),
            "domain": first.get("domain"),
        }
    )
    return {key: value for key, value in details.items() if value is not None}


def format_error_details(error: Exception) -> str:
    youtube_error = youtube_error_details(error)
    stage = getattr(error, "axisclip_stage", None)
    if youtube_error:
        return json.dumps({"stage": stage, "youtube_error": youtube_error}, ensure_ascii=False)
    return json.dumps(
        {
            "stage": stage,
            "exception_type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
        ensure_ascii=False,
    )


def raise_with_stage(stage: str, error: Exception):
    setattr(error, "axisclip_stage", stage)
    log(
        "YT-UPLOAD",
        f"etapa={stage} status=exception exception={type(error).__name__} message={redact_secret_text(str(error))[:300]}",
    )
    raise error


def run_stage(stage: str, func, *args, **kwargs):
    log("YT-UPLOAD", f"etapa={stage} status=iniciado")
    try:
        result = func(*args, **kwargs)
        log("YT-UPLOAD", f"etapa={stage} status=concluido")
        return result
    except Exception as exc:
        raise_with_stage(stage, exc)


def redact_secret_text(text: str) -> str:
    patterns = [
        r"(access_token['\"=: ]+)[^'\"\s,}]+",
        r"(refresh_token['\"=: ]+)[^'\"\s,}]+",
        r"(client_secret['\"=: ]+)[^'\"\s,}]+",
        r"(Authorization:\s*Bearer\s+)[^\s]+",
    ]
    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


def adapter_upload(adapter, clip, metadata, publication):
    if len(inspect.signature(adapter.upload).parameters) <= 2:
        return adapter.upload(clip, metadata)
    return adapter.upload(clip, metadata, publication)


def next_quota_retry() -> datetime:
    now = datetime.utcnow()
    return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)


def local_day_bounds(now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    local_start = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc).replace(tzinfo=None), local_end.astimezone(timezone.utc).replace(tzinfo=None)


def upload_limit_reached(db, now: datetime, ignore_manual: bool = False) -> bool:
    limit = max_uploads_per_day()
    if limit <= 0:
        return True
    slots = publish_schedule()
    if slots:
        local = now.replace(tzinfo=timezone.utc).astimezone(publish_timezone())
        reached = sum(
            1
            for slot in slots
            if local.time() >= local.replace(
                hour=int(slot.split(":", 1)[0]),
                minute=int(slot.split(":", 1)[1]),
                second=0,
                microsecond=0,
            ).time()
        )
        limit = min(limit, reached)
    if limit <= 0:
        return True
    start, end = local_day_bounds(now.replace(tzinfo=timezone.utc), publish_timezone())
    query = db.query(Publication).filter(
        Publication.status.in_(["UPLOADING", "PROCESSING", "PUBLISHED", "SCHEDULED"]),
        or_(
            (Publication.updated_at >= start) & (Publication.updated_at < end),
            (Publication.scheduled_at >= start) & (Publication.scheduled_at < end),
        ),
    )
    if ignore_manual:
        query = query.filter(Publication.manual.is_(False))
    return query.count() >= limit


def schedule_slot_available(now: datetime) -> bool:
    slots = publish_schedule()
    if not slots:
        return True
    local = now.replace(tzinfo=timezone.utc).astimezone(publish_timezone())
    reached = 0
    for slot in slots:
        hour, minute = [int(part) for part in slot.split(":", 1)]
        if local.time() >= local.replace(hour=hour, minute=minute, second=0, microsecond=0).time():
            reached += 1
    return reached > 0


def mark_retry(db, publication: Publication, error_type: str, details: str):
    publication.attempts += 1
    publication.error_type = error_type
    publication.error_details = redact_secret_text(details)[:4000]
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
    log(
        "YT-UPLOAD",
        "etapa=retry status=registrado "
        f"publication={publication.id} error_type={error_type} tentativa={publication.attempts} "
        f"proximo_retry={publication.next_retry.isoformat() if publication.next_retry else '-'}",
    )
    notify(
        db,
        event_key=f"publication:{publication.id}:{publication.status.lower()}:{publication.attempts}",
        type="ERROR" if publication.status == "FAILED" else "RETRY",
        title="Falha na publicacao" if publication.status == "FAILED" else "Falha temporaria",
        message=(
            f"Etapa: {publication.status}. Motivo: {error_type}."
            + (f" Nova tentativa em {publication.next_retry.isoformat()}." if publication.next_retry else "")
        ),
        clip_id=publication.clip_id,
        publication_id=publication.id,
        platform=publication.platform,
    )


def get_available_publication(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    manual_bypass = not manual_upload_counts_toward_daily_limit()

    publication = None
    if manual_bypass:
        publication = (
            db.query(Publication)
            .filter(Publication.status == "PENDING", Publication.manual.is_(True))
            .order_by(Publication.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )

    if not publication:
        publication = (
            db.query(Publication)
            .filter(Publication.status == "SCHEDULED", Publication.scheduled_at <= now)
            .order_by(Publication.scheduled_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )

    if not publication and upload_limit_reached(db, now, ignore_manual=manual_bypass):
        return None

    if not publication and schedule_slot_available(now):
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
        notify(
            db,
            event_key=f"publication:{publication.id}:upload_started",
            type="UPLOAD_STARTED",
            title=f"Upload para o {publication.platform} iniciado",
            message=f"Clip {publication.clip_id} iniciou upload.",
            clip_id=publication.clip_id,
            publication_id=publication.id,
            platform=publication.platform,
        )

    return publication


def process_publication(db, publication: Publication):
    clip = publication.clip
    adapter = get_adapter(publication.platform)

    if not clip or clip.status != "COMPLETED":
        raise ValueError("Clip invalido para publicacao.")

    if not publication.platform_post_id:
        log("PUBLISHER", f"Upload iniciado publication={publication.id}")
        metadata = retry(lambda: run_stage("metadata", lambda: asyncio.run(adapter.metadata(clip))))
        video_id = retry(lambda: run_stage("enviar_arquivo", adapter_upload, adapter, clip, metadata, publication))

        publication.platform_post_id = video_id
        publication.status = "PROCESSING"
        publication.updated_at = datetime.utcnow()
        db.commit()
        notify(
            db,
            event_key=f"publication:{publication.id}:upload_completed",
            type="UPLOAD_COMPLETED",
            title=f"Video enviado para o {publication.platform}",
            message=f"Video ID recebido: {video_id}",
            clip_id=publication.clip_id,
            publication_id=publication.id,
            platform=publication.platform,
        )
        log("PUBLISHER", f"videoId recebido publication={publication.id} videoId={video_id}")
    else:
        video_id = publication.platform_post_id
        publication.status = "PROCESSING"
        publication.updated_at = datetime.utcnow()
        db.commit()

    log("PUBLISHER", f"Processing iniciado publication={publication.id}")

    while True:
        status = retry(lambda: run_stage("processing_status", adapter.processing_status, publication))

        if status.get("processing_status") != "processing":
            break

        time.sleep(youtube_processing_poll_interval())

    if status.get("processing_status") == "succeeded":
        log("PUBLISHER", f"Processing concluido publication={publication.id}")
        notify(
            db,
            event_key=f"publication:{publication.id}:platform_processing_completed",
            type="PROCESSING_COMPLETED",
            title=f"Processamento do {publication.platform} concluido",
            message=f"Clip {clip.id} terminou o processamento na plataforma.",
            clip_id=clip.id,
            publication_id=publication.id,
            platform=publication.platform,
        )
        if publication.platform == "YOUTUBE" and not publication.thumbnail_uploaded_at:
            retry(lambda: run_stage("thumbnail", adapter.thumbnail, publication, clip))
            publication.thumbnail_uploaded_at = datetime.utcnow()
            log("PUBLISHER", f"Thumbnail enviada publication={publication.id}")
        publication.status = "PUBLISHED"
        publication.error_type = None
        publication.error_details = None
        publication.next_retry = None
        publication.published_at = datetime.utcnow()
        publication.updated_at = datetime.utcnow()
        db.commit()
        cleanup_clip_files(clip)

        url = f"https://www.youtube.com/watch?v={video_id}"
        notify(
            db,
            event_key=f"publication:{publication.id}:published",
            type="PUBLISHED",
            title=f"Clip publicado no {publication.platform}",
            message=f"Clip {clip.id} publicado com sucesso.",
            clip_id=clip.id,
            publication_id=publication.id,
            platform=publication.platform,
            url=url,
        )
        log("YOUTUBE", f"Clip {clip.id} publicado. videoId={video_id} status=PUBLISHED url={url}")
        return

    if status.get("processing_status") in {"failed", "terminated"}:
        raise RuntimeError(f"Processing falhou: {status}")

    publication.status = "WAITING_RETRY"
    publication.next_retry = datetime.utcnow() + retry_delay_for_attempt(publication.attempts + 1)
    publication.updated_at = datetime.utcnow()
    db.commit()
    notify(
        db,
        event_key=f"publication:{publication.id}:retry_processing",
        type="RETRY",
        title="Nova tentativa agendada",
        message=f"Etapa: Processing {publication.platform}. Nova tentativa em {publication.next_retry.isoformat()}.",
        clip_id=publication.clip_id,
        publication_id=publication.id,
        platform=publication.platform,
    )


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
            mark_retry(db, publication, classify_error(e), format_error_details(e))
            log("PUBLISHER", f"Retry agendado publication={publication.id} status={publication.status}")

        return True

    finally:
        db.close()


def main():
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    log("PUBLISHER", "Worker iniciado")
    try:
        run_migrations()
    except Exception as e:
        log("PUBLISHER", f"Migration check falhou: {e}")
    last_recovery = 0

    if worker_run_once():
        run_once()
        log("PUBLISHER", "Worker encerrado")
        return

    while not SHUTDOWN:
        worker_heartbeat()
        try:
            found = run_once()
        except Exception as e:
            found = False
            log("PUBLISHER", f"Erro fora da publication: {classify_error(e)} {e}")
        now = time.time()

        if now - last_recovery >= recovery_interval():
            db = SessionLocal()
            try:
                count = recover_stuck_publications(db)
                log("RECOVERY", f"Recovery executado count={count}")
            except Exception as e:
                log("RECOVERY", f"Recovery falhou: {e}")
            finally:
                db.close()
            last_recovery = now

        if not found:
            log("PUBLISHER", "Worker aguardando tarefas")
            time.sleep(publisher_poll_interval())

    log("PUBLISHER", "Worker encerrado")


if __name__ == "__main__":
    main()
