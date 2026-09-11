from datetime import datetime, timezone

from googleapiclient.discovery import build

from app.utils.pipeline_logger import log
from app.youtube.auth import get_credentials
from app.youtube.uploader import _validate_publish_at


def _youtube_client():
    return build("youtube", "v3", credentials=get_credentials())


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_youtube_publication_state(video_id: str) -> dict:
    log("YT-UPLOAD", f"etapa=publication_sync status=iniciado endpoint=youtube.videos.list videoId={video_id}")
    response = _youtube_client().videos().list(
        part="status,snippet,processingDetails",
        id=video_id,
    ).execute()
    items = response.get("items") or []
    if not items:
        log("YT-UPLOAD", f"etapa=publication_sync status=not_found endpoint=youtube.videos.list videoId={video_id}")
        return {"exists": False}
    video = items[0]
    status = video.get("status", {})
    processing = video.get("processingDetails", {})
    result = {
        "exists": True,
        "upload_status": status.get("uploadStatus"),
        "privacy_status": status.get("privacyStatus"),
        "publish_at": status.get("publishAt"),
        "published_at": video.get("snippet", {}).get("publishedAt"),
        "processing_status": processing.get("processingStatus"),
    }
    log(
        "YT-UPLOAD",
        "etapa=publication_sync status=concluido endpoint=youtube.videos.list "
        f"videoId={video_id} upload={result['upload_status']} privacy={result['privacy_status']} "
        f"publishAt={'sim' if result['publish_at'] else 'nao'}",
    )
    return result


def update_youtube_publish_at(video_id: str, scheduled_at: datetime) -> dict:
    publish_at = _validate_publish_at(_utc_iso(scheduled_at))
    log("YT-UPLOAD", f"etapa=alterar_agendamento status=iniciado endpoint=youtube.videos.update videoId={video_id}")
    response = _youtube_client().videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at,
            },
        },
    ).execute()
    status = response.get("status", {})
    if status.get("privacyStatus") != "private" or status.get("publishAt") != publish_at:
        raise RuntimeError("YouTube nao confirmou o novo publishAt.")
    log("YT-UPLOAD", f"etapa=alterar_agendamento status=concluido endpoint=youtube.videos.update videoId={video_id}")
    return response


def cancel_youtube_publish_at(video_id: str) -> dict:
    log("YT-UPLOAD", f"etapa=cancelar_agendamento status=iniciado endpoint=youtube.videos.update videoId={video_id}")
    response = _youtube_client().videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "private",
            },
        },
    ).execute()
    status = response.get("status", {})
    if status.get("privacyStatus") != "private" or status.get("publishAt"):
        raise RuntimeError("YouTube nao confirmou o cancelamento do publishAt.")
    log("YT-UPLOAD", f"etapa=cancelar_agendamento status=concluido endpoint=youtube.videos.update videoId={video_id}")
    return response
