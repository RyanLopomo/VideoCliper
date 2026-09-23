from pathlib import Path
import json
import shutil
import subprocess
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from app.db.dependencies import get_db
from app.models.project import Project
from app.models.video import Video
from app.schemas.video import (
    ClipConfigSuggestionRequest,
    ClipConfigSuggestionResponse,
    VideoListResponse,
    VideoMetadataRequest,
    VideoMetadataResponse,
    VideoResponse,
    VideoStatusResponse,
    VideoUrlCreate,
)
from app.services.clip_config import clip_suggestion, normalize_clip_targets, suggest_clip_config_with_ai
from app.services.download_progress import (
    DownloadCancelled,
    cancel_download,
    complete_download,
    fail_download,
    raise_if_cancelled,
    start_download,
    subscribe,
    update_download,
)
from app.services.notifications import notify
from app.services.video_jobs import enqueue_video_processing
from app.services.video_publication_plan import apply_video_publication_plan, set_video_publication_plan
from app.services.editing_styles import normalize_style

router = APIRouter(prefix="/videos", tags=["videos"])


def storage_response_path(file_path: str) -> str:
    return file_path.removeprefix("/")


def serialize_video(video: Video) -> dict:
    return {
        "id": video.id,
        "project_id": video.project_id,
        "source_type": video.source_type,
        "source_url": video.source_url,
        "file_path": storage_response_path(video.file_path),
        "duration": video.duration,
        "target_clip_count": video.target_clip_count,
        "target_clip_duration": video.target_clip_duration,
        "status": video.status,
        "processing_stage": video.processing_stage,
        "last_completed_clip": video.last_completed_clip,
        "last_completed_step": video.last_completed_step,
        "current_job_id": video.current_job_id,
        "processing_progress": video.processing_progress,
        "processing_message": video.processing_message,
        "last_progress_at": video.last_progress_at,
        "last_heartbeat": video.last_heartbeat,
        "error_type": video.error_type,
        "error_message": video.error_message,
        "publication_plan_enabled": video.publication_plan_enabled,
        "publication_max_per_day": video.publication_max_per_day,
        "publication_start_date": video.publication_start_date,
        "publication_times": video.publication_times,
        "publication_timezone": video.publication_timezone,
        "publication_plan_applied_at": video.publication_plan_applied_at,
        "editing_style": video.editing_style,
        "created_at": video.created_at,
    }


def get_video_duration(file_path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                file_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        return round(float(data["format"]["duration"]), 1)
    except Exception:
        return None


def get_project_or_404(project_id: int, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        existing = [p.id for p in db.query(Project).limit(10).all()]
        raise HTTPException(
            status_code=404,
            detail={"error": "Project not found", "available_project_ids": existing},
        )
    return project


def normalize_youtube_url(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    video_id = params.get("v", [None])[0]

    if not video_id:
        return url

    query = urlencode({"v": video_id})
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


def validate_video_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="URL invalida.")
    return value


def get_url_metadata(url: str) -> dict:
    source_url = normalize_youtube_url(validate_video_url(url))
    try:
        with YoutubeDL({"quiet": True, "noplaylist": True, "skip_download": True}) as ydl:
            return ydl.extract_info(source_url, download=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Nao foi possivel detectar metadados: {exc}")


async def create_upload_video(
    project_id: int,
    file: UploadFile | None,
    db: Session,
    publication_plan_enabled: bool = False,
    publication_max_per_day: int | None = None,
    publication_start_date: str | None = None,
    publication_times: list[str] | None = None,
    publication_timezone: str | None = None,
    editing_style: str = "AUTO",
    target_clip_count: int | None = None,
    target_clip_duration: int | None = None,
) -> dict:
    get_project_or_404(project_id, db)

    if file is None:
        raise HTTPException(status_code=422, detail="A file is required")

    project_folder = Path(f"/storage/project_{project_id}")
    project_folder.mkdir(parents=True, exist_ok=True)

    file_path = project_folder / "original.mp4"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    duration = get_video_duration(str(file_path))
    try:
        clip_count, clip_duration = normalize_clip_targets(duration, target_clip_count, target_clip_duration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    video = Video(
        project_id=project_id,
        source_type="upload",
        source_url=None,
        file_path=str(file_path),
        duration=duration,
        target_clip_count=clip_count,
        target_clip_duration=clip_duration,
        status="PENDING",
        processing_stage="PENDING",
        processing_progress=0,
        processing_message="Upload concluido. Aguardando processamento.",
        last_progress_at=datetime.utcnow(),
        last_heartbeat=datetime.utcnow(),
        editing_style=normalize_style(editing_style),
    )
    db.add(video)
    try:
        set_video_publication_plan(
            video,
            enabled=publication_plan_enabled,
            max_per_day=publication_max_per_day,
            start_date=publication_start_date,
            times=publication_times,
            timezone_name=publication_timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    db.refresh(video)

    enqueue_video_processing(video.id)

    return serialize_video(video)


@router.get("", response_model=list[VideoListResponse])
def list_videos(db: Session = Depends(get_db)):
    return db.query(Video).order_by(Video.id).all()


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
def get_video_status(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        existing = [v.id for v in db.query(Video).limit(20).all()]
        raise HTTPException(
            status_code=404,
            detail={"error": "Video not found", "available_video_ids": existing},
        )
    return video


@router.post("/{video_id}/pause", response_model=VideoStatusResponse)
def pause_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Video already completed")
    if video.status == "PAUSED":
        return video
    if video.status not in {"PENDING", "PROCESSING"}:
        raise HTTPException(status_code=409, detail="Video cannot be paused")
    video.status = "PAUSED"
    video.processing_message = "Processo pausado."
    video.last_progress_at = datetime.utcnow()
    video.last_heartbeat = video.last_progress_at
    db.commit()
    db.refresh(video)
    return video


@router.post("/{video_id}/start", response_model=VideoStatusResponse)
def start_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "PENDING":
        raise HTTPException(status_code=409, detail="Video is not pending")
    enqueue_video_processing(video.id)
    return video


@router.post("/{video_id}/resume", response_model=VideoStatusResponse)
def resume_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "PAUSED":
        raise HTTPException(status_code=409, detail="Video is not paused")
    video.status = "PROCESSING"
    video.processing_message = "Processamento retomado."
    video.last_progress_at = datetime.utcnow()
    video.last_heartbeat = video.last_progress_at
    db.commit()
    db.refresh(video)
    enqueue_video_processing(video.id)
    return video


@router.post("/{video_id}/publication-plan/retry", response_model=VideoStatusResponse)
def retry_video_publication_plan(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.publication_plan_enabled:
        raise HTTPException(status_code=409, detail="Video has no publication plan")
    if not any(clip.status == "COMPLETED" for clip in video.clips):
        raise HTTPException(status_code=409, detail="Video has no completed clips")

    try:
        apply_video_publication_plan(db, video)
        video.status = "COMPLETED"
        video.processing_stage = "COMPLETED"
        video.processing_progress = 100
        video.processing_message = "Processamento concluido. Publicacoes agendadas."
        if video.error_type == "PUBLICATION_PLAN_ERROR":
            video.error_type = None
            video.error_message = None
        db.commit()
    except Exception as exc:
        video.status = "COMPLETED"
        video.processing_stage = "COMPLETED"
        video.processing_progress = 100
        video.processing_message = "Processamento concluido. Falha no agendamento das publicacoes."
        video.error_type = "PUBLICATION_PLAN_ERROR"
        video.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail="Falha ao reagendar publicacoes.") from exc

    db.refresh(video)
    return video


@router.post("/{video_id}/restart", response_model=VideoStatusResponse)
def restart_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    project_folder = Path(f"/storage/project_{video.project_id}")
    clips_folder = project_folder / "clips"
    if clips_folder.exists():
        shutil.rmtree(clips_folder)
    transcript = project_folder / "transcript.json"
    if transcript.exists():
        transcript.unlink()
    suggested_clips = project_folder / "suggested_clips.json"
    if suggested_clips.exists():
        suggested_clips.unlink()
    video.clips.clear()
    video.status = "PENDING"
    video.processing_stage = "PENDING"
    video.last_completed_clip = 0
    video.processing_progress = 0
    video.processing_message = "Aguardando processamento."
    video.last_progress_at = datetime.utcnow()
    video.last_heartbeat = video.last_progress_at
    video.last_completed_step = None
    video.current_job_id = None
    video.error_type = None
    video.error_message = None
    db.commit()
    db.refresh(video)
    enqueue_video_processing(video.id)
    return video


@router.post("/upload", response_model=VideoResponse)
async def upload_video(
    project_id: int = Form(...),
    file: UploadFile | None = File(default=None),
    publication_plan_enabled: bool = Form(False),
    publication_max_per_day: int | None = Form(default=None),
    publication_start_date: str | None = Form(default=None),
    publication_times: str | None = Form(default=None),
    publication_timezone: str | None = Form(default=None),
    editing_style: str = Form("AUTO"),
    target_clip_count: int | None = Form(default=None),
    target_clip_duration: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        times = json.loads(publication_times) if publication_times else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Horarios invalidos.") from exc
    return await create_upload_video(
        project_id,
        file,
        db,
        publication_plan_enabled,
        publication_max_per_day,
        publication_start_date,
        times,
        publication_timezone,
        editing_style,
        target_clip_count,
        target_clip_duration,
    )


@router.post("/upload/{project_id}", response_model=VideoResponse)
async def upload_video_legacy(
    project_id: int,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    return await create_upload_video(project_id, file, db)


@router.post("/url-metadata", response_model=VideoMetadataResponse)
def read_url_metadata(data: VideoMetadataRequest):
    info = get_url_metadata(data.url)
    duration = info.get("duration")
    return {"duration": round(float(duration), 1) if duration else None}


@router.post("/clip-config/suggest", response_model=ClipConfigSuggestionResponse)
async def suggest_clip_config(data: ClipConfigSuggestionRequest):
    try:
        return await suggest_clip_config_with_ai(data.duration)
    except Exception:
        return clip_suggestion(data.duration)


@router.get("/downloads/events")
async def download_events():
    return StreamingResponse(subscribe(), media_type="text/event-stream")


@router.post("/downloads/{download_id}/cancel")
def cancel_active_download(download_id: str):
    if not cancel_download(download_id):
        raise HTTPException(status_code=404, detail="Download nao encontrado.")
    return {"ok": True, "download_id": download_id, "status": "cancelled"}


@router.post("/from-url", response_model=VideoResponse)
def import_video_from_url(data: VideoUrlCreate, db: Session = Depends(get_db)):
    get_project_or_404(data.project_id, db)
    source_url = normalize_youtube_url(validate_video_url(data.url))

    project_folder = Path(f"/storage/project_{data.project_id}")
    project_folder.mkdir(parents=True, exist_ok=True)
    output_template = str(project_folder / "original.%(ext)s")
    download_id = start_download(filename=source_url)
    notify(
        db,
        event_key=f"download:{download_id}:started",
        type="DOWNLOAD_STARTED",
        title="Download iniciado",
        message="O download do video foi iniciado.",
    )

    def progress_hook(payload: dict):
        raise_if_cancelled(download_id)
        if payload.get("status") == "downloading":
            update_download(download_id, payload)

    try:
        with YoutubeDL(
            {
                "outtmpl": output_template,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "noplaylist": True,
                "quiet": True,
                "progress_hooks": [progress_hook],
            }
        ) as ydl:
            info = ydl.extract_info(source_url, download=True)
    except DownloadCancelled as exc:
        notify(
            db,
            event_key=f"download:{download_id}:cancelled",
            type="DOWNLOAD_CANCELLED",
            title="Download cancelado",
            message="Download cancelado.",
        )
        raise HTTPException(status_code=409, detail="Download cancelado.") from exc
    except Exception as exc:
        fail_download(download_id, str(exc))
        notify(
            db,
            event_key=f"download:{download_id}:error",
            type="DOWNLOAD_ERROR",
            title="Falha no download",
            message=str(exc),
        )
        raise HTTPException(status_code=400, detail=f"Could not import video: {exc}")

    downloaded_files = sorted(project_folder.glob("original.*"))
    file_path = project_folder / "original.mp4"
    if not file_path.exists() and downloaded_files:
        file_path = downloaded_files[0]

    duration = info.get("duration")
    duration = round(float(duration), 1) if duration else get_video_duration(str(file_path))
    try:
        clip_count, clip_duration = normalize_clip_targets(
            duration,
            data.target_clip_count,
            data.target_clip_duration,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    video = Video(
        project_id=data.project_id,
        source_type="youtube",
        source_url=source_url,
        file_path=str(file_path),
        duration=duration,
        target_clip_count=clip_count,
        target_clip_duration=clip_duration,
        status="PENDING",
        processing_stage="PENDING",
        processing_progress=0,
        processing_message="Download concluido. Aguardando processamento.",
        last_progress_at=datetime.utcnow(),
        last_heartbeat=datetime.utcnow(),
        editing_style=normalize_style(data.editing_style),
    )
    db.add(video)
    try:
        set_video_publication_plan(
            video,
            enabled=data.publication_plan_enabled,
            max_per_day=data.publication_max_per_day,
            start_date=data.publication_start_date,
            times=data.publication_times,
            timezone_name=data.publication_timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    db.refresh(video)

    complete_download(download_id, video.id)
    notify(
        db,
        event_key=f"download:{download_id}:completed",
        type="DOWNLOAD_COMPLETED",
        title="Download concluido",
        message=f"Video {video.id} foi baixado com sucesso.",
        video_id=video.id,
    )

    enqueue_video_processing(video.id)

    return serialize_video(video)


@router.post("/url", response_model=VideoResponse)
def import_video_url_alias(data: VideoUrlCreate, db: Session = Depends(get_db)):
    return import_video_from_url(data, db)
