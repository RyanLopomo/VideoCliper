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


class Video(Base):
    __tablename__ = "videos"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False,
    )

    source_type = Column(
        String,
        nullable=False,
    )

    source_url = Column(
        String,
        nullable=True,
    )

    file_path = Column(
        String,
        nullable=False,
    )

    duration = Column(
        Float,
        nullable=True,
    )

    status = Column(
        String,
        nullable=False,
        default="PENDING",
    )

    processing_stage = Column(
        String,
        nullable=False,
        default="PENDING",
    )

    last_completed_clip = Column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    project = relationship(
        "Project",
        back_populates="videos",
    )

    clips = relationship(
        "Clip",
        back_populates="video",
        cascade="all, delete-orphan",
    )