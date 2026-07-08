from datetime import datetime
from pydantic import BaseModel

class VideoResponse(BaseModel):
    id: int
    project_id: int
    source_type: str
    file_path: str
    duration: float | None
    status:str
    created_at: datetime

    class Config:
        from_attributes = True