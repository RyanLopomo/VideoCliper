from app.models.video import Video
from app.models.clip import Clip

from app.utils.pipeline_logger import log


def save_stage(db, video: Video, stage: str):

    video.processing_stage = stage

    db.commit()

    log(
        "CHECKPOINT",
        f"Stage -> {stage}"
    )


def save_clip(db, video: Video, clip_number: int):

    video.last_completed_clip = clip_number

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

    if video.project is not None:
        video.project.status = "COMPLETED"

    db.commit()

    log(
        "CHECKPOINT",
        f"Vídeo {video.id} finalizado."
    )


def video_failed(db, video: Video, error: str):

    video.status = "FAILED"

    video.processing_stage = "FAILED"

    video.error_message = error

    if video.project is not None:
        video.project.status = "FAILED"

    db.commit()

    log(
        "CHECKPOINT",
        f"Vídeo {video.id} falhou."
    )
