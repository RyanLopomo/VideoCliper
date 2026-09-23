from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Clip(Base):
    __tablename__ = "clips"

    id = Column(Integer, primary_key=True, index=True)

    video_id = Column(
        Integer,
        ForeignKey("videos.id"),
        nullable=False,
    )

    title = Column(
        String,
        nullable=False,
    )

    start_time = Column(
        Float,
        nullable=False,
    )

    end_time = Column(
        Float,
        nullable=False,
    )

    clip_path = Column(
        String,
        nullable=True,
    )

    subtitle_path = Column(
        String,
        nullable=True,
    )

    thumbnail_path = Column(
        String,
        nullable=True,
    )

    status = Column(
        String,
        nullable=False,
        default="PENDING",
    )

    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message = Column(
        String,
        nullable=True,
    )

    editing_style = Column(
        String,
        nullable=False,
        default="AUTO",
    )

    applied_preset = Column(
        String,
        nullable=True,
    )

    ai_style_recommendation = Column(
        String,
        nullable=True,
    )

    ai_style_confidence = Column(
        Float,
        nullable=True,
    )

    ai_style_reason = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    video = relationship(
        "Video",
        back_populates="clips",
    )

    publications = relationship(
        "Publication",
        back_populates="clip",
        cascade="all, delete-orphan",
    )
