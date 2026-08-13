from pathlib import Path

from app.utils.pipeline_logger import log
from app.youtube.config import cleanup_after_publish


def cleanup_clip_files(clip):
    if not cleanup_after_publish():
        return

    paths = [clip.subtitle_path, clip.thumbnail_path]

    if clip.clip_path:
        final_path = Path(clip.clip_path)
        intermediate = final_path.with_name(final_path.name.replace("_final", ""))
        paths.append(str(intermediate))

    for path in paths:
        if not path:
            continue

        file_path = Path(path)

        if file_path.exists():
            file_path.unlink()
            log("CLEANUP", f"Removido: {file_path}")
