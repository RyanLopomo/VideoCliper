from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.clip import Clip
from app.models.publication import Publication
from app.services.editing_styles import STYLE_PRESETS, normalize_style, concrete_style, suggest_style_sync, transcript_text_for_clip
from app.services.reel_adapter import adapt_to_reel
from app.services.subtitle_generator import burn_subtitles
from app.youtube.publication_urls import publication_url

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
    result = []
    for clip in clips:
        publication = (
            db.query(Publication)
            .filter(
                Publication.clip_id == clip.id,
                Publication.status != "CANCELLED",
            )
            .order_by(Publication.created_at.desc())
            .first()
        )
        result.append(
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
            "publication_url": publication_url(publication) if publication else None,
            "publication_id": publication.id if publication else None,
            "publication_platform": publication.platform if publication else None,
            "publication_status": publication.status if publication else None,
            "publication_scheduled_at": publication.scheduled_at if publication else None,
            "publication_error_type": publication.error_type if publication else None,
            "publication_error_details": publication.error_details if publication else None,
            "editing_style": clip.editing_style,
            "applied_preset": clip.applied_preset,
            "ai_style_recommendation": clip.ai_style_recommendation,
            "ai_style_confidence": clip.ai_style_confidence,
            "ai_style_reason": clip.ai_style_reason,
        }
        )
    return result


@router.get("/styles/presets")
def get_style_presets():
    return {
        "default": "AUTO",
        "styles": [
            {"id": "AUTO", "name": "Auto", "description": "A IA escolhe o melhor estilo para cada clip."},
            {"id": "DRAMATIC", "name": "Dramatico", "description": "Contraste maior, zoom progressivo e captions fortes."},
            {"id": "HAPPY", "name": "Alegre", "description": "Cores vivas, ritmo leve e captions amigaveis."},
            {"id": "ENERGETIC", "name": "Energetico", "description": "Ritmo rapido, zooms mais fortes e visual dinamico."},
            {"id": "CINEMATIC", "name": "Cinematico", "description": "Color grading refinado, zoom lento e transicoes suaves."},
            {"id": "PODCAST", "name": "Podcast", "description": "Foco nos participantes, legibilidade alta e poucos efeitos."},
            {"id": "CLEAN", "name": "Clean", "description": "Poucos efeitos, enquadramento estavel e foco no conteudo."},
        ],
        "presets": STYLE_PRESETS,
    }


def clip_or_404(db: Session, clip_id: int) -> Clip:
    clip = db.query(Clip).filter(Clip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


@router.post("/{clip_id}/style")
def update_clip_style(clip_id: int, payload: dict, db: Session = Depends(get_db)):
    clip = clip_or_404(db, clip_id)
    resolved = concrete_style(payload.get("style"))
    clip.editing_style = normalize_style(payload.get("style"))
    if payload.get("render", True) and clip.clip_path:
        final_path = Path(clip.clip_path)
        clips_folder = final_path.parent
        raw_path = clips_folder / f"clip_{clip.id}.mp4"
        srt_path = Path(clip.subtitle_path or clips_folder / f"clip_{clip.id}.srt")
        reel_path = clips_folder / f"clip_{clip.id}_reel.mp4"
        if raw_path.exists() and srt_path.exists():
            adapt_to_reel(str(raw_path), str(reel_path), style=resolved)
            burn_subtitles(str(reel_path), str(srt_path), str(final_path))
            clip.applied_preset = resolved
    db.commit()
    db.refresh(clip)
    return {"id": clip.id, "editing_style": clip.editing_style, "applied_preset": clip.applied_preset}


@router.post("/{clip_id}/style/suggest")
def suggest_clip_style(clip_id: int, db: Session = Depends(get_db)):
    clip = clip_or_404(db, clip_id)
    transcript_path = Path(f"/storage/project_{clip.video.project_id}/transcript.json")
    transcript = None
    if transcript_path.exists():
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    text = transcript_text_for_clip(transcript, clip.start_time, clip.end_time)
    recommendation = suggest_style_sync(clip.title, text)
    clip.ai_style_recommendation = recommendation["recommended_style"]
    clip.ai_style_confidence = recommendation["confidence"]
    clip.ai_style_reason = recommendation["reason"]
    db.commit()
    return recommendation


@router.get("/{clip_id}/style-preview/{style}")
def preview_clip_style(clip_id: int, style: str, db: Session = Depends(get_db)):
    clip = clip_or_404(db, clip_id)
    if not clip.clip_path:
        raise HTTPException(status_code=404, detail="Clip file not available")
    final_path = Path(clip.clip_path)
    clips_folder = final_path.parent
    raw_path = clips_folder / f"clip_{clip.id}.mp4"
    srt_path = Path(clip.subtitle_path or clips_folder / f"clip_{clip.id}.srt")
    if not raw_path.exists() or not srt_path.exists():
        raise HTTPException(status_code=404, detail="Preview source files not available")
    resolved = concrete_style(style)
    reel_path = clips_folder / f"clip_{clip.id}_preview_{resolved.lower()}_reel.mp4"
    preview_path = clips_folder / f"clip_{clip.id}_preview_{resolved.lower()}.mp4"
    if not preview_path.exists() or preview_path.stat().st_size == 0:
        adapt_to_reel(str(raw_path), str(reel_path), style=resolved)
        burn_subtitles(str(reel_path), str(srt_path), str(preview_path))
    return FileResponse(str(preview_path), media_type="video/mp4", headers={"Accept-Ranges": "bytes"})

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
