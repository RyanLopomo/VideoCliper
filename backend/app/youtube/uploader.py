from pathlib import Path
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.utils.pipeline_logger import log
from app.youtube.auth import get_credentials


YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
VALID_PRIVACY_STATUSES = {"private", "public", "unlisted"}


def _trim_utf8(value: str, max_bytes: int) -> str:
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", errors="ignore")


def _validate_publish_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalidPublishAt: publishAt deve ser ISO 8601 com timezone.") from exc

    if parsed.tzinfo is None:
        raise ValueError("invalidPublishAt: publishAt deve incluir timezone.")
    if parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise ValueError("invalidPublishAt: publishAt nao pode estar no passado.")

    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_video_insert_body(
    title: str,
    description: str,
    tags: list[str] | None,
    privacy_status: str,
    publish_at: str | None,
    category_id: str = "22",
) -> dict:
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("invalidTitle: titulo obrigatorio.")
    clean_title = clean_title[:100]

    clean_description = _trim_utf8(str(description or "").strip(), 5000)
    clean_category = str(category_id or "22").strip()
    if not clean_category.isdigit():
        raise ValueError("invalidCategoryId: categoryId invalido.")

    clean_privacy = str(privacy_status or "private").strip().lower()
    if clean_privacy not in VALID_PRIVACY_STATUSES:
        raise ValueError("invalidVideoMetadata: privacyStatus invalido.")

    body = {
        "snippet": {
            "title": clean_title,
            "description": clean_description,
            "categoryId": clean_category,
        },
        "status": {
            "privacyStatus": "private" if publish_at else clean_privacy,
        },
    }

    clean_tags = []
    seen = set()
    for tag in tags or []:
        clean_tag = str(tag).strip()
        key = clean_tag.casefold()
        if not clean_tag or key in seen:
            continue
        clean_tags.append(clean_tag[:500])
        seen.add(key)
        if len(clean_tags) >= 15:
            break
    if clean_tags:
        body["snippet"]["tags"] = clean_tags

    if publish_at:
        body["status"]["publishAt"] = _validate_publish_at(publish_at)

    return body


def upload_video(
    video_path: str,
    title: str = "AxisClip Test",
    description: str = "Vídeo enviado automaticamente pelo AxisClip.",
    tags: list[str] | None = None,
    privacy_status: str = "public",
    publish_at: str | None = None,
    category_id: str = "22",
):
    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Vídeo não encontrado: {video_path}"
        )

    log("YT-UPLOAD", "etapa=iniciar_upload status=preparando endpoint=youtube.videos.insert")
    credentials = get_credentials()

    youtube = build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        credentials=credentials,
    )

    body = build_video_insert_body(title, description, tags, privacy_status, publish_at, category_id)
    log(
        "YT-UPLOAD",
        "etapa=iniciar_upload status=body_validado "
        f"endpoint=youtube.videos.insert privacyStatus={body['status'].get('privacyStatus')} "
        f"publishAt={'sim' if body['status'].get('publishAt') else 'nao'} "
        f"tags={'sim' if body['snippet'].get('tags') else 'nao'}",
    )

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/*",
        resumable=True,
    )

    def create_request():
        return youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

    request = create_request()

    response = None
    recreated_session = False

    log("YT-UPLOAD", f"etapa=enviar_arquivo status=iniciado endpoint=youtube.videos.insert arquivo={video_path.name}")

    while response is None:

        try:
            status, response = request.next_chunk()
        except HttpError as exc:
            http_status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
            log(
                "YT-UPLOAD",
                f"etapa=enviar_arquivo status=http_error endpoint=youtube.videos.insert "
                f"http_status={http_status} exception=HttpError",
            )
            if http_status == 404 and not recreated_session:
                log("YT-UPLOAD", "etapa=enviar_arquivo status=sessao_expirada endpoint=youtube.videos.insert acao=recriar_sessao")
                media = MediaFileUpload(
                    str(video_path),
                    mimetype="video/*",
                    resumable=True,
                )
                request = create_request()
                recreated_session = True
                continue
            raise
        except (TimeoutError, ConnectionError) as exc:
            log(
                "YT-UPLOAD",
                f"etapa=enviar_arquivo status=network_error endpoint=youtube.videos.insert "
                f"exception={type(exc).__name__} message={str(exc)[:300]}",
            )
            raise

        if status:
            progress = int(
                status.progress() * 100
            )

            log("YT-UPLOAD", f"etapa=enviar_arquivo status=progresso endpoint=youtube.videos.insert progress={progress}")

    video_id = response["id"]

    print(
        f"Upload concluído! "
        f"Video ID: {video_id}"
    )

    return video_id
