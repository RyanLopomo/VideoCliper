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


def enqueue_publication(db, clip, platform: str = PLATFORM_YOUTUBE, publication_account_id: int | None = None):
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
        publication_account_id=publication_account_id or _default_account_id(db, platform),
        status="PENDING",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication
