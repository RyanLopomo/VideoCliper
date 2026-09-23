import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.db.dependencies import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
def create_project(data: ProjectCreate = Body(...), db: Session = Depends(get_db)):
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=422, detail="Project name is required")
    project = Project(name=data.name.strip())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@router.get(
    "", response_model=list[ProjectResponse]
)
def list_projects(
    db: Session = Depends(get_db)
):
    return db.query(Project).all()

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_folder = Path(f"/storage/project_{project_id}").resolve()
    storage_root = Path("/storage").resolve()
    db.delete(project)
    db.commit()

    if project_folder.exists() and storage_root in project_folder.parents:
        shutil.rmtree(project_folder)

    return {"ok": True}

