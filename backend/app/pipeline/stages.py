from pathlib import Path
import json
import asyncio

from app.models.project import Project
from app.models.video import Video
from app.models.clip import Clip

from app.core.retry import retry
from app.core.clip_validator import validate_clip

from app.pipeline.context import PipelineContext
from app.pipeline.checkpoint import save_stage, touch_progress

from app.services.transcriber import transcribe_audio
from app.services.clip_finder import find_clips
from app.services.video_cutter import generate_clip
from app.services.reel_adapter import adapt_to_reel
from app.services.editing_styles import concrete_style, normalize_style, suggest_style_for_clip_sync, transcript_text_for_clip
from app.services.subtitle_generator import (
    filter_segments_for_clip,
    adjust_segments,
    generate_srt,
    burn_subtitles,
)
from app.services.thumbnail import generate_thumbnail

from app.utils.pipeline_logger import log


def load_video(ctx: PipelineContext):

    ctx.video = (
        ctx.db.query(Video)
        .filter(Video.id == ctx.video_id)
        .first()
    )

    if ctx.video is None:
        raise RuntimeError(
            f"Video {ctx.video_id} não encontrado."
        )

    ctx.project = (
        ctx.db.query(Project)
        .filter(Project.id == ctx.video.project_id)
        .first()
    )

    if ctx.project is None:
        raise RuntimeError(
            "Projeto não encontrado."
        )

    log(
        "PIPELINE",
        f"Vídeo {ctx.video.id} carregado."
    )

    if ctx.video.status != "PAUSED":
        ctx.video.status = "PROCESSING"
        ctx.project.status = "PROCESSING"
        touch_progress(
            ctx.db,
            ctx.video,
            progress=ctx.video.processing_progress,
            message=ctx.video.processing_message or "Preparando processamento.",
        )
        ctx.db.commit()


def prepare_storage(ctx: PipelineContext):

    ctx.project_folder = Path(
        f"/storage/project_{ctx.video.project_id}"
    )

    ctx.clips_folder = (
        ctx.project_folder / "clips"
    )

    ctx.clips_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    ctx.transcript_path = (
        ctx.project_folder / "transcript.json"
    )

    ctx.suggested_clips_path = (
        ctx.project_folder / "suggested_clips.json"
    )

    log(
        "PIPELINE",
        "Storage preparado."
    )


def transcribe_video(ctx: PipelineContext):

    save_stage(
        ctx.db,
        ctx.video,
        "TRANSCRIBING",
        progress=0,
        message="Transcrevendo audio...",
    )

    if ctx.transcript_path.exists():

        with open(
            ctx.transcript_path,
            "r",
            encoding="utf-8",
        ) as f:

            ctx.transcript = json.load(f)

        log(
            "PIPELINE",
            "Transcript carregado."
        )

        touch_progress(
            ctx.db,
            ctx.video,
            progress=100,
            message="Transcricao carregada.",
        )

        return

    def update_transcription_progress(progress: int):
        touch_progress(
            ctx.db,
            ctx.video,
            progress=progress,
            message="Transcrevendo audio...",
        )

    ctx.transcript = retry(
        transcribe_audio,
        ctx.video.file_path,
        str(ctx.transcript_path),
        progress_callback=update_transcription_progress,
        retries=3,
        delay=3,
        stage="TRANSCRIBER",
    )

    with open(
        ctx.transcript_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            ctx.transcript,
            f,
            ensure_ascii=False,
            indent=2,
        )

    log(
        "PIPELINE",
        "Transcript criado."
    )


def find_video_clips(ctx: PipelineContext):

    save_stage(
        ctx.db,
        ctx.video,
        "FINDING_CLIPS",
        progress=None,
        message="Analisando transcricao com IA...",
    )

    if ctx.suggested_clips_path and ctx.suggested_clips_path.exists():
        with open(
            ctx.suggested_clips_path,
            "r",
            encoding="utf-8",
        ) as f:
            ctx.suggested_clips = json.load(f)

        log(
            "PIPELINE",
            f"video_id={ctx.video.id} stage=FINDING_CLIPS action=LOAD_CACHED found={len(ctx.suggested_clips)}",
        )
        touch_progress(
            ctx.db,
            ctx.video,
            progress=100,
            message=f"{len(ctx.suggested_clips)} candidatos carregados.",
        )
        return

    ctx.suggested_clips = retry(
        lambda: asyncio.run(
            find_clips(
                str(ctx.transcript_path),
                target_clips=ctx.video.target_clip_count,
                target_duration=ctx.video.target_clip_duration,
            )
        ),
        retries=3,
        delay=5,
        stage="OLLAMA",
    )

    if ctx.suggested_clips_path:
        with open(
            ctx.suggested_clips_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                ctx.suggested_clips,
                f,
                ensure_ascii=False,
                indent=2,
            )

    touch_progress(
        ctx.db,
        ctx.video,
        progress=100,
        message=f"{len(ctx.suggested_clips)} candidatos selecionados.",
    )

    if not ctx.suggested_clips:
        log(
            "PIPELINE",
            f"video_id={ctx.video.id} stage=FINDING_CLIPS result=STOPPED_NO_CANDIDATES",
        )

    log(
        "PIPELINE",
        f"{len(ctx.suggested_clips)} clips encontrados."
    )


def create_clip_record(
    ctx: PipelineContext,
    clip_data: dict,
):

    required = [
        "start_time",
        "end_time",
        "title",
    ]

    for field in required:
        if field not in clip_data:
            raise ValueError(
                f"Campo '{field}' ausente no clip."
            )

    start_time = float(clip_data["start_time"])
    end_time = float(clip_data["end_time"])

    if start_time < 0:
        raise ValueError(
            "start_time não pode ser negativo."
        )

    if end_time <= start_time:
        raise ValueError(
            "end_time precisa ser maior que start_time."
        )

    existing = (
        ctx.db.query(Clip)
        .filter(Clip.video_id == ctx.video.id)
        .order_by(Clip.id)
        .all()
    )
    for clip in existing:
        if (
            abs(float(clip.start_time) - start_time) <= 0.05
            and abs(float(clip.end_time) - end_time) <= 0.05
        ):
            if clip.status != "COMPLETED":
                clip.status = "PENDING"
                clip.error_message = None
                ctx.db.commit()
            log(
                "PIPELINE",
                f"video_id={ctx.video.id} clip_id={clip.id} status=REUSE_DUPLICATE_WINDOW",
            )
            return clip

    clip = Clip(
        video_id=ctx.video.id,
        title=clip_data["title"],
        start_time=start_time,
        end_time=end_time,
        editing_style=normalize_style(getattr(ctx.video, "editing_style", "AUTO")),
        status="PENDING",
    )

    ctx.db.add(clip)
    ctx.db.commit()
    ctx.db.refresh(clip)

    touch_progress(
        ctx.db,
        ctx.video,
        progress=ctx.video.processing_progress,
        message=f"Gerando clip {ctx.video.last_completed_clip + 1}.",
    )

    log(
        "PIPELINE",
        f"Clip {clip.id} criado."
    )

    return clip


def process_clip(
    ctx: PipelineContext,
    clip: Clip,
):

    log(
        "PIPELINE",
        f"Processando clip {clip.id}"
    )
    clip.status = "PROCESSING"
    clip.error_message = None
    ctx.video.last_completed_step = f"clip:{clip.id}:processing"
    ctx.db.commit()

    clip_mp4 = (
        ctx.clips_folder /
        f"clip_{clip.id}.mp4"
    )

    clip_srt = (
        ctx.clips_folder /
        f"clip_{clip.id}.srt"
    )

    final_clip = (
        ctx.clips_folder /
        f"clip_{clip.id}_final.mp4"
    )

    reel_clip = (
        ctx.clips_folder /
        f"clip_{clip.id}_reel.mp4"
    )

    thumbnail = (
        ctx.clips_folder /
        f"thumb_{clip.id}.jpg"
    )

    retry(
        generate_clip,
        input_video=ctx.video.file_path,
        output_video=str(clip_mp4),
        start=clip.start_time,
        end=clip.end_time,
        retries=2,
        stage="FFMPEG",
    )

    segments = filter_segments_for_clip(
        ctx.transcript["segments"],
        clip.start_time,
        clip.end_time,
    )

    adjusted = adjust_segments(
        segments,
        clip.start_time,
        clip.end_time - clip.start_time,
    )

    retry(
        generate_srt,
        adjusted,
        str(clip_srt),
        retries=2,
        stage="SRT",
    )

    selected_style = normalize_style(getattr(clip, "editing_style", None) or getattr(ctx.video, "editing_style", "AUTO"))
    cached_style = normalize_style(getattr(clip, "ai_style_recommendation", None))
    if selected_style == "AUTO" and cached_style != "AUTO":
        selected_style = cached_style

    clip.applied_preset = concrete_style(selected_style)
    ctx.db.commit()

    retry(
        adapt_to_reel,
        input_video=str(clip_mp4),
        output_video=str(reel_clip),
        style=clip.applied_preset,
        retries=2,
        stage="REEL",
    )

    retry(
        burn_subtitles,
        input_video=str(reel_clip),
        input_srt=str(clip_srt),
        output_video=str(final_clip),
        retries=2,
        stage="BURN_SUBTITLE",
    )

    retry(
        generate_thumbnail,
        input_video=str(final_clip),
        output_image=str(thumbnail),
        timestamp=(
            clip.end_time - clip.start_time
        ) / 2,
        retries=2,
        stage="THUMBNAIL",
    )

    validate_clip(
        video_path=str(final_clip),
        subtitle_path=str(clip_srt),
        thumbnail_path=str(thumbnail),
    )

    clip.clip_path = str(final_clip)
    clip.subtitle_path = str(clip_srt)
    clip.thumbnail_path = str(thumbnail)
    clip.status = "COMPLETED"

    ctx.video.last_completed_clip += 1
    total = ctx.video.target_clip_count or ctx.video.last_completed_clip
    ctx.video.processing_progress = round((ctx.video.last_completed_clip / max(total, 1)) * 100)
    ctx.video.processing_progress = min(ctx.video.processing_progress, 100)
    ctx.video.processing_message = f"{ctx.video.last_completed_clip}/{total} clips gerados."

    ctx.db.commit()

    selected_style = normalize_style(getattr(clip, "editing_style", None) or getattr(ctx.video, "editing_style", "AUTO"))
    if selected_style == "AUTO" and not getattr(clip, "ai_style_recommendation", None):
        try:
            recommendation = suggest_style_for_clip_sync(
                clip,
                transcript_text_for_clip(ctx.transcript, clip.start_time, clip.end_time),
            )
            clip.ai_style_recommendation = recommendation["recommended_style"]
            clip.ai_style_confidence = recommendation["confidence"]
            clip.ai_style_reason = recommendation["reason"]
            clip.editing_style = "AUTO"
            ctx.db.commit()
            log(
                "EDITING_STYLE",
                f"clip={clip.id} pipeline_progress={ctx.video.processing_progress}% completed_clips={ctx.video.last_completed_clip}/{total}",
            )
        except Exception as exc:
            log(
                "EDITING_STYLE",
                f"clip={clip.id} status=FALLBACK reason={type(exc).__name__} pipeline_progress={ctx.video.processing_progress}% completed_clips={ctx.video.last_completed_clip}/{total}",
            )

    log(
        "PIPELINE",
        f"Clip {clip.id} concluído."
    )
