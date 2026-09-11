from googleapiclient.discovery import build

from app.utils.pipeline_logger import log
from app.youtube.auth import get_credentials


def get_video_status(video_id: str):
    log("YT-UPLOAD", f"etapa=processing_status status=iniciado endpoint=youtube.videos.list videoId={video_id}")

    credentials = get_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
    )

    response = youtube.videos().list(
        part="status,processingDetails",
        id=video_id,
    ).execute()

    if not response.get("items"):
        log("YT-UPLOAD", f"etapa=processing_status status=not_found endpoint=youtube.videos.list videoId={video_id}")
        raise RuntimeError(
            f"Vídeo não encontrado: {video_id}"
        )

    video = response["items"][0]

    status = video.get("status", {})
    processing = video.get(
        "processingDetails",
        {},
    )

    result = {
        "upload_status": status.get(
            "uploadStatus"
        ),
        "privacy_status": status.get(
            "privacyStatus"
        ),
        "publish_at": status.get(
            "publishAt"
        ),
        "published_at": video.get("snippet", {}).get(
            "publishedAt"
        ),
        "processing_status": processing.get(
            "processingStatus"
        ),
        "failure_reason": processing.get(
            "processingFailureReason"
        ),
    }
    log(
        "YT-UPLOAD",
        "etapa=processing_status status=concluido endpoint=youtube.videos.list "
        f"videoId={video_id} processing={result.get('processing_status')} upload={result.get('upload_status')}",
    )
    return result
