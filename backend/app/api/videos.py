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


@router.get("", response_model=list[VideoResponse])
def list_videos(db: Session = Depends(get_db)):
    return db.query(Video).all()


@router.get("/{video_id}/status")
def get_video_status(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        existing = [v.id for v in db.query(Video).limit(20).all()]
        detail = {"error": "Video not found", "available_video_ids": existing}
        raise HTTPException(status_code=404, detail=detail)
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
    print(f"upload called for project_id={project_id}")
    # Log content-length for debugging
    # Note: FastAPI provides request object via dependency injection only in path operation
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        # Help the client by returning some existing project ids
        existing = [p.id for p in db.query(Project).limit(10).all()]
        detail = {"error": "Project not found", "available_project_ids": existing}
        raise HTTPException(status_code=404, detail=detail)

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