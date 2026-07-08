from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.db.database import Base

class Project(Base):

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(
        String,
        default="CREATED"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
