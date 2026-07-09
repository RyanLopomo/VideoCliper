from pydantic import BaseModel
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str

class ProjectResponse(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True