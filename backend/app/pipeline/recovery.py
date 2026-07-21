from pathlib import Path

from app.pipeline.context import PipelineContext

from app.utils.pipeline_logger import log

def recover_stage(ctx: PipelineContext):

    stage = ctx.video.processing_stage

    if not stage:

        log(
            "RECOVERY",
            "Primeira execuÃ§Ã£o."
        )

        return

    log(
        "RECOVERY",
        f"Retomando estÃ¡gio {stage}"
    )

def transcript_exists(ctx: PipelineContext):

    return (
        ctx.transcript_path.exists()
    )

def clip_video_exists(path: Path):

    return (
        path.exists()
        and
        path.stat().st_size > 0
    )

def subtitle_exists(path: Path):

    return (
        path.exists()
        and
        path.stat().st_size > 0
    )

def thumbnail_exists(path: Path):

    return (
        path.exists()
        and
        path.stat().st_size > 0
    )

def should_skip_clip(
    ctx: PipelineContext,
    clip_index: int,
):

    return (
        clip_index
        <=
        ctx.video.last_completed_clip
    )

def update_last_clip(
    ctx: PipelineContext,
    clip_index: int,
):

    ctx.video.last_completed_clip = clip_index

    ctx.db.commit()

    log(
        "RECOVERY",
        f"Checkpoint clip {clip_index}"
    )

def clear_processing(ctx: PipelineContext):

    ctx.video.processing_stage = "COMPLETED"

    ctx.video.last_completed_clip = 0

    ctx.db.commit()

    log(
        "RECOVERY",
        "Checkpoint limpo."
    )
