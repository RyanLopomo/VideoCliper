from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.youtube.auth import get_credentials


YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


def upload_video(
    video_path: str,
    title: str = "AxisClip Test",
    description: str = "Vídeo enviado automaticamente pelo AxisClip.",
    tags: list[str] | None = None,
    privacy_status: str = "private",
):
    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Vídeo não encontrado: {video_path}"
        )

    credentials = get_credentials()

    youtube = build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        credentials=credentials,
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
            "tags": tags or [],
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/*",
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None

    print("Iniciando upload...")

    while response is None:

        status, response = request.next_chunk()

        if status:
            progress = int(
                status.progress() * 100
            )

            print(
                f"Upload: {progress}%"
            )

    video_id = response["id"]

    print(
        f"Upload concluído! "
        f"Video ID: {video_id}"
    )

    return video_id
