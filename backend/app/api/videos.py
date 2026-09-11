from pathlib import Path
import json
import shutil
import subprocess
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from app.db.dependencies import get_db
from app.models.project import Project
from app.models.video import Video
from app.schemas.video import VideoListResponse, VideoResponse, VideoStatusResponse, VideoUrlCreate
from app.services.video_jobs import enqueue_video_processing
from app.services.video_publication_plan import set_video_publication_plan

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
        "status": video.status,
        "processing_stage": video.processing_stage,
        "last_completed_clip": video.last_completed_clip,
        "publication_plan_enabled": video.publication_plan_enabled,
        "publication_max_per_day": video.publication_max_per_day,
        "publication_start_date": video.publication_start_date,
        "publication_times": video.publication_times,
        "publication_timezone": video.publication_timezone,
        "publication_plan_applied_at": video.publication_plan_applied_at,
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


async def create_upload_video(
    project_id: int,
    file: UploadFile | None,
    db: Session,
    publication_plan_enabled: bool = False,
    publication_max_per_day: int | None = None,
    publication_start_date: str | None = None,
    publication_times: list[str] | None = None,
    publication_timezone: str | None = None,
) -> dict:
    get_project_or_404(project_id, db)

    if file is None:
        raise HTTPException(status_code=422, detail="A file is required")

    project_folder = Path(f"/storage/project_{project_id}")
    project_folder.mkdir(parents=True, exist_ok=True)

    file_path = project_folder / "original.mp4"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    video = Video(
        project_id=project_id,
        source_type="upload",
        source_url=None,
        file_path=str(file_path),
        duration=get_video_duration(str(file_path)),
        status="PENDING",
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
    db.commit()
    db.refresh(video)
    enqueue_video_processing(video.id)
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
    video.clips.clear()
    video.status = "PENDING"
    video.processing_stage = "PENDING"
    video.last_completed_clip = 0
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
    )


@router.post("/upload/{project_id}", response_model=VideoResponse)
async def upload_video_legacy(
    project_id: int,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    return await create_upload_video(project_id, file, db)


@router.post("/from-url", response_model=VideoResponse)
def import_video_from_url(data: VideoUrlCreate, db: Session = Depends(get_db)):
    get_project_or_404(data.project_id, db)
    source_url = normalize_youtube_url(validate_video_url(data.url))

    project_folder = Path(f"/storage/project_{data.project_id}")
    project_folder.mkdir(parents=True, exist_ok=True)
    output_template = str(project_folder / "original.%(ext)s")

    try:
        with YoutubeDL(
            {
                "outtmpl": output_template,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "noplaylist": True,
                "quiet": True,
            }
        ) as ydl:
            info = ydl.extract_info(source_url, download=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not import video: {exc}")

    downloaded_files = sorted(project_folder.glob("original.*"))
    file_path = project_folder / "original.mp4"
    if not file_path.exists() and downloaded_files:
        file_path = downloaded_files[0]

    duration = info.get("duration")
    video = Video(
        project_id=data.project_id,
        source_type="youtube",
        source_url=source_url,
        file_path=str(file_path),
        duration=round(float(duration), 1) if duration else get_video_duration(str(file_path)),
        status="PENDING",
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

    enqueue_video_processing(video.id)

    return serialize_video(video)


@router.post("/url", response_model=VideoResponse)
def import_video_url_alias(data: VideoUrlCreate, db: Session = Depends(get_db)):
    return import_video_from_url(data, db)
