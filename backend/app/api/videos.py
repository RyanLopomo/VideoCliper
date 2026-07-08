from pathlib import Path
import shutil

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.dependencies import get_db
from app.models.project import Project
from app.models.video import Video
from app.schemas.video import VideoResponse
from app.queue.redis_connectiuon import video_queue
from app.workers.jobs import process_video

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("/{video_id}/status")
def get_video_status(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {
        "id": video.id,
        "status": video.status,
        "error_message": video.error_message,
    }


@router.post("/upload/{project_id}", response_model=VideoResponse)
async def upload_video(
    project_id: int,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if file is None:
        raise HTTPException(status_code=422, detail="A file is required")

    project_folder = Path(f"/storage/project_{project_id}")
    project_folder.mkdir(parents=True, exist_ok=True)
    file_path = project_folder / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    video = Video(project_id=project_id, source_type="upload", file_path=str(file_path))
    db.add(video)
    db.commit()
    db.refresh(video)

    video_queue.enqueue(process_video, video.id)

    return video