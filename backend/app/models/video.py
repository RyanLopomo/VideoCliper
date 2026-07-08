from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from datetime import datetime
from app.db.database import Base

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    source_type = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    
    file_path = Column(String, nullable=False)
    duration = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

