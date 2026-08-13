from googleapiclient.discovery import build

from app.youtube.auth import get_credentials


def get_video_status(video_id: str):

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
        raise RuntimeError(
            f"Vídeo não encontrado: {video_id}"
        )

    video = response["items"][0]

    status = video.get("status", {})
    processing = video.get(
        "processingDetails",
        {},
    )

    return {
        "upload_status": status.get(
            "uploadStatus"
        ),
        "privacy_status": status.get(
            "privacyStatus"
        ),
        "processing_status": processing.get(
            "processingStatus"
        ),
        "failure_reason": processing.get(
            "processingFailureReason"
        ),
    }