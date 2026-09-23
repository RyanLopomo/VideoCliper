from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
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

    target_clip_count = Column(
        Integer,
        nullable=True,
    )

    target_clip_duration = Column(
        Integer,
        nullable=False,
        default=60,
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

    last_completed_step = Column(
        String,
        nullable=True,
    )

    current_job_id = Column(
        String,
        nullable=True,
    )

    processing_progress = Column(
        Integer,
        nullable=True,
    )

    processing_message = Column(
        String,
        nullable=True,
    )

    last_progress_at = Column(
        DateTime,
        nullable=True,
    )

    last_heartbeat = Column(
        DateTime,
        nullable=True,
    )

    error_type = Column(
        String,
        nullable=True,
    )

    error_message = Column(
        Text,
        nullable=True,
    )

    publication_plan_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    publication_max_per_day = Column(
        Integer,
        nullable=True,
    )

    publication_start_date = Column(
        String,
        nullable=True,
    )

    publication_times = Column(
        String,
        nullable=True,
    )

    publication_timezone = Column(
        String,
        nullable=True,
    )

    publication_plan_applied_at = Column(
        DateTime,
        nullable=True,
    )

    editing_style = Column(
        String,
        nullable=False,
        default="AUTO",
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
