from datetime import datetime

from app.models.publication import Publication, PublicationAccount


PLATFORM_YOUTUBE = "YOUTUBE"
ACTIVE_STATUSES = {"PENDING", "UPLOADING", "PROCESSING", "WAITING_RETRY", "PUBLISHED"}


def _default_account_id(db, platform: str):
    account = (
        db.query(PublicationAccount)
        .filter(
            PublicationAccount.platform == platform,
            PublicationAccount.enabled.is_(True),
            PublicationAccount.is_default.is_(True),
        )
        .first()
    )
    return account.id if account else None


def enqueue_publication(
    db,
    clip,
    platform: str = PLATFORM_YOUTUBE,
    publication_account_id: int | None = None,
    status: str = "PENDING",
    scheduled_at=None,
    manual: bool = False,
):
    existing = (
        db.query(Publication)
        .filter(
            Publication.clip_id == clip.id,
            Publication.platform == platform,
        )
        .first()
    )

    if existing:
        if existing.status in {"CANCELLED", "FAILED"} and not existing.platform_post_id:
            existing.status = status
            existing.scheduled_at = scheduled_at
            existing.manual = manual
            existing.error_type = None
            existing.error_details = None
            existing.next_retry = None
            existing.updated_at = datetime.utcnow()
            db.commit()
        return existing

    publication = Publication(
        clip_id=clip.id,
        platform=platform,
        publication_account_id=publication_account_id or _default_account_id(db, platform),
        status=status,
        scheduled_at=scheduled_at,
        manual=manual,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication
