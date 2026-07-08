from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.projects import router as projects_router
from app.api.videos import router as videos_router

from app.db.database import Base, engine

app = FastAPI(title="AxisClip API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(videos_router)
app.include_router(projects_router)


@app.get("/health")
def health():
    return {"status": "ok"}
