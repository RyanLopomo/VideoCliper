from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.video import Video


@dataclass
class PipelineContext:

    db: Session

    video_id: int

    video: Optional[Video] = None

    project: Optional[Project] = None

    transcript: Optional[dict] = None

    suggested_clips: list = field(default_factory=list)

    project_folder: Optional[Path] = None

    clips_folder: Optional[Path] = None

    transcript_path: Optional[Path] = None

    suggested_clips_path: Optional[Path] = None

    current_clip: int = 0
