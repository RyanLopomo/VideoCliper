from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.projects import router as projects_router
from app.api.videos import router as videos_router
from app.api.clips import router as clips_router
from app.db.migrations import run_migrations

from app.db.database import Base, engine
import time
from fastapi import Request

app = FastAPI(title="AxisClip API")

app.include_router(clips_router)
app.include_router(projects_router)
app.include_router(videos_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
run_migrations()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    try:
        content_length = request.headers.get("content-length")
    except Exception:
        content_length = None
    print(f"--> {request.method} {request.url.path} content-length={content_length}")
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    print(f"<-- {request.method} {request.url.path} status={response.status_code} time={duration:.1f}ms")
    return response

@app.get("/health")
def health():
    return {"status": "ok"}
