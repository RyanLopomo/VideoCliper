from datetime import datetime

from app.models.video import Video
from app.models.clip import Clip

from app.services.notifications import notify
from app.utils.pipeline_logger import log


def touch_progress(
    db,
    video: Video,
    *,
    progress: int | None = None,
    message: str | None = None,
):
    now = datetime.utcnow()
    video.last_heartbeat = now
    video.last_progress_at = now
    if progress is not None:
        video.processing_progress = max(0, min(100, int(progress)))
    if message is not None:
        video.processing_message = message
        video.last_completed_step = message
    db.commit()


def save_stage(
    db,
    video: Video,
    stage: str,
    *,
    progress: int | None = None,
    message: str | None = None,
):

    video.processing_stage = stage
    video.last_heartbeat = datetime.utcnow()
    video.last_progress_at = video.last_heartbeat
    video.processing_progress = progress
    video.processing_message = message
    video.last_completed_step = stage
    if stage not in {"FAILED", "COMPLETED"}:
        video.error_type = None
        video.error_message = None

    db.commit()

    notify(
        db,
        event_key=f"video:{video.id}:stage:{stage}",
        type="STAGE_CHANGED",
        title="Etapa alterada",
        message=f"Video {video.id}: {stage}.",
        video_id=video.id,
    )

    log(
        "CHECKPOINT",
        f"video={video.id} stage={stage} completed={video.last_completed_clip}/{getattr(video, 'target_clip_count', None) or '?'} saved=true"
    )


def save_clip(db, video: Video, clip_number: int):

    video.last_completed_clip = clip_number
    video.last_heartbeat = datetime.utcnow()
    video.last_progress_at = video.last_heartbeat
    video.last_completed_step = f"clip:{clip_number}"

    db.commit()

    log(
        "CHECKPOINT",
        f"Último clip -> {clip_number}"
    )


def clip_completed(db, clip: Clip):

    clip.status = "COMPLETED"

    db.commit()

    log(
        "CHECKPOINT",
        f"Clip {clip.id} concluído."
    )


def clip_failed(db, clip: Clip, error: str):

    clip.status = "FAILED"

    clip.retry_count += 1

    clip.error_message = error

    db.commit()

    log(
        "CHECKPOINT",
        f"Clip {clip.id} falhou."
    )


def video_completed(db, video: Video):

    video.status = "COMPLETED"

    video.processing_stage = "COMPLETED"
    video.processing_progress = 100
    video.processing_message = "Processamento concluido."
    video.last_heartbeat = datetime.utcnow()
    video.last_progress_at = video.last_heartbeat
    video.last_completed_step = "COMPLETED"
    video.current_job_id = None

    if video.project is not None:
        video.project.status = "COMPLETED"

    db.commit()

    log(
        "CHECKPOINT",
        f"Vídeo {video.id} finalizado."
    )


def video_failed(db, video: Video, error: str):

    video.status = "FAILED"

    video.error_type = error.splitlines()[-1][:120] if error else "PROCESSING_ERROR"

    video.error_message = error
    video.processing_message = "Falha no processamento."
    video.last_heartbeat = datetime.utcnow()
    video.last_progress_at = video.last_heartbeat
    video.current_job_id = None

    if video.project is not None:
        video.project.status = "FAILED"

    db.commit()

    log(
        "CHECKPOINT",
        f"Vídeo {video.id} falhou."
    )
