from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("clip_id", "platform", name="uq_publication_clip_platform"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clip_id = Column(Integer, ForeignKey("clips.id"), nullable=False)
    platform = Column(String, nullable=False, default="YOUTUBE")
    status = Column(String, nullable=False, default="PENDING")
    error_type = Column(String, nullable=True)
    error_details = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_retry = Column(DateTime, nullable=True)
    platform_post_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    thumbnail_uploaded_at = Column(DateTime, nullable=True)

    clip = relationship("Clip", back_populates="publications")
