from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.notification import Notification
from app.services.notifications import notify

router = APIRouter(prefix="/notifications", tags=["notifications"])


def serialize_notification(item: Notification) -> dict:
    return {
        "id": str(item.id),
        "type": item.type,
        "title": item.title,
        "message": item.message,
        "video_id": item.video_id,
        "clip_id": item.clip_id,
        "publication_id": item.publication_id,
        "platform": item.platform,
        "url": item.url,
        "read": item.read,
        "created_at": item.created_at,
    }


@router.get("")
def list_notifications(db: Session = Depends(get_db)):
    items = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()
    return [serialize_notification(item) for item in items]


@router.post("/read-all")
def mark_notifications_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.read.is_(False)).update({"read": True})
    db.commit()
    return {"ok": True}


@router.post("/test")
def test_notification(db: Session = Depends(get_db)):
    item = notify(
        db,
        event_key="test-notification",
        type="PROCESSING_COMPLETED",
        title="Notificacao de teste",
        message="As notificacoes internas estao funcionando.",
    )
    if item is None:
        item = db.query(Notification).filter(Notification.event_key == "test-notification").first()
    return serialize_notification(item)
