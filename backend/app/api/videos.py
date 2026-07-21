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
from app.queue.redis_connectiuon import video_queue
from app.schemas.video import VideoListResponse, VideoResponse, VideoStatusResponse, VideoUrlCreate

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


async def create_upload_video(project_id: int, file: UploadFile | None, db: Session) -> dict:
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
    db.commit()
    db.refresh(video)

    video_queue.enqueue("app.workers.jobs.process_video", video.id, job_timeout=7200)

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


@router.post("/upload", response_model=VideoResponse)
async def upload_video(
    project_id: int = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    return await create_upload_video(project_id, file, db)


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
    source_url = normalize_youtube_url(data.url)

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
    db.commit()
    db.refresh(video)

    video_queue.enqueue("app.workers.jobs.process_video", video.id, job_timeout=7200)

    return serialize_video(video)
