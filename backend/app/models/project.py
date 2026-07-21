from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    status = Column(
        String,
        nullable=False,
        default="CREATED",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    videos = relationship(
        "Video",
        back_populates="project",
        cascade="all, delete-orphan",
    )