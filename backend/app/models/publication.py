from datetime import datetime

from sqlalchemy import (
    Boolean,
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
    publication_account_id = Column(Integer, ForeignKey("publication_accounts.id"), nullable=True)
    platform = Column(String, nullable=False, default="YOUTUBE")
    status = Column(String, nullable=False, default="PENDING")
    error_type = Column(String, nullable=True)
    error_details = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_retry = Column(DateTime, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    manual = Column(Boolean, nullable=False, default=False)
    platform_post_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    thumbnail_uploaded_at = Column(DateTime, nullable=True)

    clip = relationship("Clip", back_populates="publications")
    publication_account = relationship("PublicationAccount", back_populates="publications")


class PublicationAccount(Base):
    __tablename__ = "publication_accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False, default="YOUTUBE")
    account_name = Column(String, nullable=False)
    platform_account_id = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    credential_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    publications = relationship("Publication", back_populates="publication_account")
