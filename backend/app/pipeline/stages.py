from pathlib import Path
import json
import asyncio

from app.models.project import Project
from app.models.video import Video
from app.models.clip import Clip

from app.core.retry import retry
from app.core.clip_validator import validate_clip

from app.pipeline.context import PipelineContext
from app.pipeline.checkpoint import save_stage

from app.services.transcriber import transcribe_audio
from app.services.clip_finder import find_clips
from app.services.video_cutter import generate_clip
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

    ctx.video.status = "PROCESSING"
    ctx.project.status = "PROCESSING"
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

    log(
        "PIPELINE",
        "Storage preparado."
    )


def transcribe_video(ctx: PipelineContext):

    save_stage(
        ctx.db,
        ctx.video,
        "TRANSCRIBING",
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

        return

    ctx.transcript = retry(
        transcribe_audio,
        ctx.video.file_path,
        str(ctx.transcript_path),
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
    )

    ctx.suggested_clips = retry(
        lambda: asyncio.run(
            find_clips(
                str(ctx.transcript_path)
            )
        ),
        retries=3,
        delay=5,
        stage="OLLAMA",
    )

    if not ctx.suggested_clips:
        raise ValueError(
            "Nenhum clip encontrado."
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

    clip = Clip(
        video_id=ctx.video.id,
        title=clip_data["title"],
        start_time=start_time,
        end_time=end_time,
        status="PROCESSING",
    )

    ctx.db.add(clip)
    ctx.db.commit()
    ctx.db.refresh(clip)

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

    retry(
        burn_subtitles,
        input_video=str(clip_mp4),
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

    ctx.db.commit()

    log(
        "PIPELINE",
        f"Clip {clip.id} concluído."
    )