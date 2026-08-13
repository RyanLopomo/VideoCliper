from app.models.clip import Clip
from app.utils.pipeline_logger import log
from app.youtube.config import youtube_auto_publish_enabled
from app.youtube.publication_queue import enqueue_publication


def publish_completed_clip(db, clip: Clip):
    if not youtube_auto_publish_enabled():
        return None

    if clip.status != "COMPLETED":
        log("YOUTUBE", f"Clip {clip.id} ainda nao esta COMPLETED.")
        return None

    if not clip.clip_path or not clip.subtitle_path or not clip.thumbnail_path:
        log("YOUTUBE", f"Arquivos incompletos para clip {clip.id}.")
        return None

    publication = enqueue_publication(db, clip)
    log("YOUTUBE", f"Publication {publication.id} PENDING para clip {clip.id}.")
    return publication
