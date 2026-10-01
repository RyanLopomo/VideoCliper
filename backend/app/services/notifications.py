from sqlalchemy.exc import IntegrityError

from app.models.notification import Notification
from app.utils.pipeline_logger import log


def _safe_rollback(db):
    rollback = getattr(db, "rollback", None)
    if rollback:
        rollback()


def notify(
    db,
    *,
    event_key: str,
    type: str,
    title: str,
    message: str,
    video_id: int | None = None,
    clip_id: int | None = None,
    publication_id: int | None = None,
    platform: str | None = None,
    url: str | None = None,
):
    try:
        add = getattr(db, "add", None)
        commit = getattr(db, "commit", None)
        if not add or not commit:
            return None
        item = Notification(
            event_key=event_key,
            type=type,
            title=title,
            message=message[:1000],
            video_id=video_id,
            clip_id=clip_id,
            publication_id=publication_id,
            platform=platform,
            url=url,
        )
        db.add(item)
        db.commit()
        return item
    except IntegrityError:
        _safe_rollback(db)
        return None
    except Exception as exc:
        _safe_rollback(db)
        log("NOTIFICATION", f"Falha ao criar notificacao: {exc.__class__.__name__}")
        return None
