from datetime import datetime

from app.models.publication import Publication


PLATFORM_YOUTUBE = "YOUTUBE"
ACTIVE_STATUSES = {"PENDING", "UPLOADING", "PROCESSING", "WAITING_RETRY", "PUBLISHED"}


def enqueue_publication(db, clip, platform: str = PLATFORM_YOUTUBE):
    existing = (
        db.query(Publication)
        .filter(
            Publication.clip_id == clip.id,
            Publication.platform == platform,
            Publication.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )

    if existing:
        return existing

    publication = Publication(
        clip_id=clip.id,
        platform=platform,
        status="PENDING",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication
