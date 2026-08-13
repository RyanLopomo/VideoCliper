from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.youtube.auth import get_credentials


def upload_thumbnail(video_id: str, thumbnail_path: str) -> dict:
    thumbnail_path = Path(thumbnail_path)

    if not thumbnail_path.exists():
        raise FileNotFoundError(f"Thumbnail nao encontrada: {thumbnail_path}")

    youtube = build("youtube", "v3", credentials=get_credentials())
    media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")

    return youtube.thumbnails().set(
        videoId=video_id,
        media_body=media,
    ).execute()
