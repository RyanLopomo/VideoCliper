from datetime import datetime

from pydantic import BaseModel


class VideoUrlCreate(BaseModel):
    project_id: int
    url: str


class VideoResponse(BaseModel):
    id: int
    project_id: int
    source_type: str
    source_url: str | None
    file_path: str
    duration: float | None
    status: str
    processing_stage: str | None = None
    last_completed_clip: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoListResponse(BaseModel):
    id: int
    project_id: int
    source_type: str
    duration: float | None
    status: str
    processing_stage: str | None = None
    last_completed_clip: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoStatusResponse(BaseModel):
    id: int
    status: str
    processing_stage: str | None
    last_completed_clip: int
    error_message: str | None

    model_config = {"from_attributes": True}
