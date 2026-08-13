import asyncio
import time
from pathlib import Path

from googleapiclient.errors import HttpError

from app.youtube.metadata import generate_metadata
from app.youtube.status import get_video_status
from app.youtube.thumbnail import upload_thumbnail
from app.youtube.uploader import upload_video
from app.youtube.validator import normalize_metadata


def validate_files(video_path: str, srt_path: str, thumbnail_path: str):
    for path in [video_path, srt_path, thumbnail_path]:
        if not Path(path).exists():
            raise FileNotFoundError(path)


def retry(func, *args, attempts=3, delay=5, **kwargs):
    last_error = None

    for index in range(attempts):
        try:
            return func(*args, **kwargs)
        except (HttpError, TimeoutError, ConnectionError, RuntimeError) as e:
            last_error = e
            if index < attempts - 1:
                time.sleep(delay * (index + 1))

    raise last_error


def wait_processing(video_id: str, attempts: int = 30, delay: int = 20) -> dict:
    status = {}

    for _ in range(attempts):
        status = retry(get_video_status, video_id)

        if status.get("processing_status") in {"succeeded", "failed", "terminated"}:
            return status

        time.sleep(delay)

    return status


async def publish_clip(
    video_path: str,
    srt_path: str,
    thumbnail_path: str,
    privacy_status: str = "private",
) -> dict:
    validate_files(video_path, srt_path, thumbnail_path)

    metadata = normalize_metadata(await generate_metadata(srt_path))

    video_id = retry(
        upload_video,
        video_path=video_path,
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
        privacy_status=privacy_status,
    )

    processing = wait_processing(video_id)
    thumbnail_response = None

    if processing.get("processing_status") == "succeeded":
        thumbnail_response = retry(upload_thumbnail, video_id, thumbnail_path)

    return {
        "video_id": video_id,
        "metadata": metadata,
        "processing": processing,
        "thumbnail_uploaded": thumbnail_response is not None,
        "thumbnail_response": thumbnail_response,
    }


def publish_clip_sync(*args, **kwargs) -> dict:
    return asyncio.run(publish_clip(*args, **kwargs))
