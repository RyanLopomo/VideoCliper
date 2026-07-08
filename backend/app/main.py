from fastapi import FastAPI
from app.api.projects import router as projects_router

from app.db.database import Base, engine

app = FastAPI(
    title="AxisClip API"
)

Base.metadata.create_all(bind=engine)

app.include_router(projects_router)

@app.get("/health") 
def health():

    return {
        "status": "ok"
    }
