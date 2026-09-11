from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.db.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("event_key", name="uq_notifications_event_key"),)

    id = Column(Integer, primary_key=True, index=True)
    event_key = Column(String, nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    video_id = Column(Integer, nullable=True)
    clip_id = Column(Integer, nullable=True)
    publication_id = Column(Integer, nullable=True)
    platform = Column(String, nullable=True)
    url = Column(String, nullable=True)
    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
