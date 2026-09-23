from datetime import datetime, timedelta
from pathlib import Path

from app.utils.pipeline_logger import log
from app.youtube.config import cleanup_after_publish, cleanup_delay_hours


CLIP_TERMINAL_STATUSES = {"PUBLISHED", "CANCELLED", "FAILED"}
VIDEO_BLOCKING_STATUSES = {"PENDING", "SCHEDULED", "WAITING_RETRY", "UPLOADING", "PROCESSING"}


def _ready_after_delay(published_at) -> bool:
    delay = cleanup_delay_hours()
    if delay <= 0:
        return True
    if not published_at:
        return False
    return published_at <= datetime.utcnow() - timedelta(hours=delay)


def _safe_unlink(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True


def _clip_cleanup_paths(clip) -> list[Path]:
    paths: set[Path] = set()

    for value in [clip.clip_path, clip.subtitle_path, clip.thumbnail_path]:
        if value:
            paths.add(Path(value))

    if clip.clip_path:
        final_path = Path(clip.clip_path)
        paths.add(final_path.with_name(final_path.name.replace("_final", "")))
        paths.add(final_path.with_name(final_path.name.replace("_final", "_reel")))
        paths.add(final_path.with_name(f"{final_path.stem}_youtube_short.mp4"))

    folder = Path(clip.clip_path).parent if clip.clip_path else None
    if folder and folder.exists():
        for pattern in [
            f"clip_{clip.id}.*",
            f"clip_{clip.id}_*.mp4",
            f"thumb_{clip.id}.*",
        ]:
            paths.update(folder.glob(pattern))

    return sorted(paths)


def _clip_publications_allow_cleanup(clip) -> tuple[bool, str]:
    publications = list(getattr(clip, "publications", []) or [])
    if not publications:
        return False, "NO_PUBLICATION"

    for publication in publications:
        if publication.status not in CLIP_TERMINAL_STATUSES:
            return False, "PUBLICATION_PENDING"
        if publication.status == "PUBLISHED" and not publication.platform_post_id:
            return False, "MISSING_PLATFORM_POST_ID"
        if publication.status == "PUBLISHED" and not _ready_after_delay(publication.published_at):
            return False, "RETENTION_DELAY"

    return True, "OK"


def cleanup_clip_files(clip) -> int:
    if not cleanup_after_publish():
        log("CLEANUP", f"clip_id={clip.id} action=SKIP reason=DISABLED")
        return 0

    allowed, reason = _clip_publications_allow_cleanup(clip)
    if not allowed:
        log("CLEANUP", f"clip_id={clip.id} action=SKIP reason={reason}")
        return 0

    deleted = 0
    for path in _clip_cleanup_paths(clip):
        if _safe_unlink(path):
            deleted += 1

    log("CLEANUP", f"clip={clip.id} status=PUBLISHED deleted_files={deleted}")
    cleanup_video_artifacts_if_complete(clip.video)
    return deleted


def cleanup_video_artifacts_if_complete(video) -> int:
    if not cleanup_after_publish() or not video:
        return 0

    for clip in getattr(video, "clips", []) or []:
        for publication in getattr(clip, "publications", []) or []:
            if publication.status in VIDEO_BLOCKING_STATUSES:
                log("CLEANUP", f"video_id={video.id} action=SKIP reason=PUBLICATION_PENDING")
                return 0

    deleted = 0
    project_folder = Path(video.file_path).parent if video.file_path else None
    candidates: list[Path] = []
    if video.file_path:
        candidates.append(Path(video.file_path))
    if project_folder and project_folder.exists():
        candidates.extend(
            [
                project_folder / "transcript.json",
                project_folder / "suggested_clips.json",
            ]
        )
        for pattern in ["*.wav", "*.mp3", "*.srt", "*.tmp", "*waveform*"]:
            candidates.extend(project_folder.glob(pattern))

    for path in sorted(set(candidates)):
        if _safe_unlink(path):
            deleted += 1

    log("CLEANUP", f"video_id={video.id} action=DELETE deleted_files={deleted}")
    return deleted
