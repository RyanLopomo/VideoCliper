from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.clip import Clip

router = APIRouter(prefix="/clips", tags=["clips"])

@router.get("/{clip_id}/thumbnail")
def get_thumbnail(
    clip_id: int,
    db: Session = Depends(get_db)
):
    clip = (
        db.query(Clip)
        .filter(Clip.id == clip_id)
        .first()
    )

    if not clip:
        raise HTTPException(
            status_code=404,
            detail="Clip not found"
        )
    if not clip.thumbnail_path:
        raise HTTPException(
            status_code=404,
            detail="Thumb not found"
        )

    clip_path = Path(clip.thumbnail_path)
    if not clip_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Thumb file not found"
        )

    return FileResponse(str(clip_path), media_type="image/jpeg")

@router.get("/{clip_id}/download")
def download_clip(
    clip_id: int,
    db: Session = Depends(get_db)
):
    clip = db.query(Clip).filter(
        Clip.id == clip_id
    ).first()

    if not clip:
        raise HTTPException(
            status_code=404,
            detail="clip not found"
        )

    if not clip.clip_path:
        raise HTTPException(
            status_code=404,
            detail="Clip file not available"
        )

    clip_path = Path(clip.clip_path)
    if not clip_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Clip file not found"
        )

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=f"clip_{clip.id}_final.mp4"
    )

@router.get("/video/{video_id}")
def get_video_clips(
    video_id: int,
    db: Session = Depends(get_db)
):
    clips = (
        db.query(Clip)
        .filter(Clip.video_id == video_id)
        .all()
    )
    return [
        {
            "id": clip.id,
            "video_id": clip.video_id,
            "title": clip.title,
            "start_time": clip.start_time,
            "end_time": clip.end_time,
            "duration": round(clip.end_time - clip.start_time, 1),
            "status": clip.status,
            "thumbnail_url": f"/clips/{clip.id}/thumbnail",
            "stream_url": f"/clips/{clip.id}/stream",
            "download_url": f"/clips/{clip.id}/download",
        }
        for clip in clips
    ]

@router.get("/{clip_id}/stream")
def stream_clip(clip_id: int, db: Session = Depends(get_db)):
    clip = db.query(Clip).filter(Clip.id == clip_id).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if not clip.clip_path:
        raise HTTPException(status_code=404, detail="Clip file not available")

    clip_path = Path(clip.clip_path)
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip file not found")

    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )
