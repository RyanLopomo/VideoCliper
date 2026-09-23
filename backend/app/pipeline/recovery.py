from datetime import datetime
from pathlib import Path

from app.core.clip_validator import ValidationError, validate_clip
from app.models.clip import Clip
from app.pipeline.context import PipelineContext

from app.utils.pipeline_logger import log


def recover_stage(ctx: PipelineContext):
    stage = ctx.video.processing_stage

    if not stage:
        log("RECOVERY", "Primeira execucao.")
        return

    log(
        "RECOVERY",
        f"video_id={ctx.video.id} stage={stage} last_completed_clip={ctx.video.last_completed_clip} action=LOAD_CHECKPOINT",
    )


def transcript_exists(ctx: PipelineContext):
    return ctx.transcript_path.exists()


def clip_video_exists(path: Path):
    return path.exists() and path.stat().st_size > 0


def subtitle_exists(path: Path):
    return path.exists() and path.stat().st_size > 0


def thumbnail_exists(path: Path):
    return path.exists() and path.stat().st_size > 0


def expected_clip_paths(ctx: PipelineContext, clip: Clip) -> tuple[Path, Path, Path]:
    final_mp4 = Path(clip.clip_path) if clip.clip_path else ctx.clips_folder / f"clip_{clip.id}_final.mp4"
    subtitle = Path(clip.subtitle_path) if clip.subtitle_path else ctx.clips_folder / f"clip_{clip.id}.srt"
    thumbnail = Path(clip.thumbnail_path) if clip.thumbnail_path else ctx.clips_folder / f"thumb_{clip.id}.jpg"
    return final_mp4, subtitle, thumbnail


def clip_artifacts_valid(ctx: PipelineContext, clip: Clip) -> bool:
    final_mp4, subtitle, thumbnail = expected_clip_paths(ctx, clip)
    try:
        validate_clip(str(final_mp4), str(subtitle), str(thumbnail))
        return True
    except ValidationError as exc:
        log("RECOVERY", f"video_id={ctx.video.id} clip_id={clip.id} status=INVALID_ARTIFACT reason={exc}")
        return False


def reconcile_clip_checkpoints(ctx: PipelineContext, total_clips: int | None = None) -> int:
    clips = (
        ctx.db.query(Clip)
        .filter(Clip.video_id == ctx.video.id)
        .order_by(Clip.start_time.asc(), Clip.id.asc())
        .all()
    )
    completed = 0

    for index, clip in enumerate(clips, start=1):
        if clip_artifacts_valid(ctx, clip):
            if clip.status != "COMPLETED":
                clip.status = "COMPLETED"
            final_mp4, subtitle, thumbnail = expected_clip_paths(ctx, clip)
            clip.clip_path = str(final_mp4)
            clip.subtitle_path = str(subtitle)
            clip.thumbnail_path = str(thumbnail)
            completed = index
            continue

        if clip.status in {"PROCESSING", "COMPLETED"}:
            clip.status = "PENDING"
        break

    if completed != (ctx.video.last_completed_clip or 0):
        log(
            "RECOVERY",
            f"video_id={ctx.video.id} db_last_completed={ctx.video.last_completed_clip or 0} filesystem_completed={completed} action=RECONCILE_CHECKPOINT",
        )
    ctx.video.last_completed_clip = completed
    if total_clips:
        ctx.video.processing_progress = round((ctx.video.last_completed_clip / max(total_clips, 1)) * 100)
        ctx.video.processing_message = f"{ctx.video.last_completed_clip}/{total_clips} clips gerados."
    ctx.video.last_heartbeat = datetime.utcnow()
    ctx.video.last_progress_at = ctx.video.last_heartbeat
    ctx.video.last_completed_step = f"recovered_clip:{ctx.video.last_completed_clip}"
    ctx.db.commit()

    log(
        "RECOVERY",
        f"video_id={ctx.video.id} resume_from={ctx.video.last_completed_clip + 1}",
    )
    return ctx.video.last_completed_clip


def should_skip_clip(
    ctx: PipelineContext,
    clip_index: int,
):
    return clip_index <= ctx.video.last_completed_clip


def update_last_clip(
    ctx: PipelineContext,
    clip_index: int,
    total_clips: int | None = None,
):
    ctx.video.last_completed_clip = clip_index
    ctx.video.last_heartbeat = datetime.utcnow()
    ctx.video.last_progress_at = ctx.video.last_heartbeat
    ctx.video.last_completed_step = f"clip:{clip_index}"
    if total_clips:
        ctx.video.processing_progress = round((clip_index / max(total_clips, 1)) * 100)
        ctx.video.processing_message = f"{clip_index}/{total_clips} clips gerados."

    ctx.db.commit()

    log(
        "CHECKPOINT",
        f"video={ctx.video.id} stage={ctx.video.processing_stage} completed={clip_index}/{total_clips or '?'} saved=true",
    )


def clear_processing(ctx: PipelineContext):
    ctx.video.processing_stage = "COMPLETED"
    ctx.video.processing_progress = 100
    ctx.video.processing_message = "Processamento concluido."
    ctx.video.last_heartbeat = datetime.utcnow()
    ctx.video.last_progress_at = ctx.video.last_heartbeat
    ctx.video.last_completed_step = "COMPLETED"
    ctx.video.current_job_id = None

    ctx.db.commit()

    log("RECOVERY", "Checkpoint limpo.")
