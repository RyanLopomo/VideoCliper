from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.utils.pipeline_logger import log
from app.youtube.auth import get_credentials


def upload_thumbnail(video_id: str, thumbnail_path: str) -> dict:
    thumbnail_path = Path(thumbnail_path)
    log("YT-UPLOAD", f"etapa=thumbnail status=iniciado endpoint=youtube.thumbnails.set videoId={video_id}")

    if not thumbnail_path.exists():
        log("YT-UPLOAD", f"etapa=thumbnail status=arquivo_ausente endpoint=youtube.thumbnails.set videoId={video_id}")
        raise FileNotFoundError(f"Thumbnail nao encontrada: {thumbnail_path}")

    youtube = build("youtube", "v3", credentials=get_credentials())
    media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")

    response = youtube.thumbnails().set(
        videoId=video_id,
        media_body=media,
    ).execute()
    log("YT-UPLOAD", f"etapa=thumbnail status=concluido endpoint=youtube.thumbnails.set videoId={video_id}")
    return response
