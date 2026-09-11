import json
from datetime import datetime, timezone

from app.models.clip import Clip
from app.models.video import Video
from app.services.publication_scheduler import create_scheduled_publications, normalize_times
from app.utils.pipeline_logger import log
from app.youtube.config import publish_timezone


def set_video_publication_plan(
    video: Video,
    enabled: bool = False,
    max_per_day: int | None = None,
    start_date: str | None = None,
    times: list[str] | None = None,
    timezone_name: str | None = None,
):
    if not enabled:
        video.publication_plan_enabled = False
        return

    if not max_per_day or max_per_day <= 0:
        raise ValueError("Quantidade por dia deve ser maior que zero.")
    if not start_date:
        raise ValueError("Data inicial obrigatoria.")

    normalized_times = normalize_times(times or [])
    video.publication_plan_enabled = True
    video.publication_max_per_day = max_per_day
    video.publication_start_date = start_date
    video.publication_times = json.dumps(normalized_times)
    video.publication_timezone = timezone_name or str(publish_timezone())


def configured_times(video: Video) -> list[str]:
    if not video.publication_times:
        return []
    try:
        parsed = json.loads(video.publication_times)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed]


def apply_video_publication_plan(db, video: Video):
    if not video.publication_plan_enabled:
        return None

    clips = (
        db.query(Clip)
        .filter(Clip.video_id == video.id, Clip.status == "COMPLETED")
        .order_by(Clip.start_time.asc(), Clip.id.asc())
        .all()
    )
    if not clips:
        return None

    result = create_scheduled_publications(
        db,
        clips,
        "YOUTUBE",
        int(video.publication_max_per_day or 1),
        str(video.publication_start_date),
        configured_times(video),
    )
    video.publication_plan_applied_at = datetime.now(timezone.utc)
    db.commit()
    log(
        "YOUTUBE",
        f"Planejamento aplicado video={video.id} clips={result['total_clips']} publications={result['created_publications']}",
    )
    return result
