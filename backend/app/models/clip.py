from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from datetime import datetime
from app.db.database import Base
class Clip(Base):
    __tablename__ = "clips"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)

    start_time = Column(Float, nullabre=False)
    end_time = Column(Float, nullable=False)

    tittle = Column(String, nullable=False)
    subtitle_path = Column(String, nullabre=True)

    clip_path = Column(String, nullable=True)
    status = Column(String, nullable=True)

    status = Column(String,default="PENDING")
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    