from datetime import datetime

from pydantic import BaseModel


class VideoMetadataRequest(BaseModel):
    url: str


class VideoMetadataResponse(BaseModel):
    duration: float | None


class ClipConfigSuggestionRequest(BaseModel):
    duration: float


class ClipConfigSuggestionResponse(BaseModel):
    recommended_count: int
    recommended_duration_seconds: int
    reason: str
    confidence: float


class VideoUrlCreate(BaseModel):
    project_id: int
    url: str
    target_clip_count: int | None = None
    target_clip_duration: int | None = None
    publication_plan_enabled: bool = False
    publication_max_per_day: int | None = None
    publication_start_date: str | None = None
    publication_times: list[str] | None = None
    publication_timezone: str | None = None
    editing_style: str = "AUTO"


class VideoResponse(BaseModel):
    id: int
    project_id: int
    source_type: str
    source_url: str | None
    file_path: str
    duration: float | None
    target_clip_count: int | None = None
    target_clip_duration: int = 60
    status: str
    processing_stage: str | None = None
    last_completed_clip: int = 0
    last_completed_step: str | None = None
    current_job_id: str | None = None
    processing_progress: int | None = None
    processing_message: str | None = None
    last_progress_at: datetime | None = None
    last_heartbeat: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    publication_plan_enabled: bool = False
    publication_max_per_day: int | None = None
    publication_start_date: str | None = None
    publication_times: str | None = None
    publication_timezone: str | None = None
    publication_plan_applied_at: datetime | None = None
    editing_style: str = "AUTO"
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoListResponse(BaseModel):
    id: int
    project_id: int
    source_type: str
    duration: float | None
    target_clip_count: int | None = None
    target_clip_duration: int = 60
    status: str
    processing_stage: str | None = None
    last_completed_clip: int = 0
    last_completed_step: str | None = None
    current_job_id: str | None = None
    processing_progress: int | None = None
    processing_message: str | None = None
    last_progress_at: datetime | None = None
    last_heartbeat: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    publication_plan_enabled: bool = False
    publication_max_per_day: int | None = None
    publication_start_date: str | None = None
    publication_times: str | None = None
    publication_timezone: str | None = None
    publication_plan_applied_at: datetime | None = None
    editing_style: str = "AUTO"
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoStatusResponse(BaseModel):
    id: int
    status: str
    processing_stage: str | None
    last_completed_clip: int
    last_completed_step: str | None = None
    current_job_id: str | None = None
    processing_progress: int | None = None
    processing_message: str | None = None
    last_progress_at: datetime | None = None
    last_heartbeat: datetime | None = None
    error_type: str | None = None
    error_message: str | None

    model_config = {"from_attributes": True}
