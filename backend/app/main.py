from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.projects import router as projects_router
from app.api.videos import router as videos_router
from app.api.clips import router as clips_router
from app.api.notifications import router as notifications_router
from app.api.publications import router as publications_router
from app.db.migrations import run_migrations

from app.db.database import Base, engine
from app.db.database import SessionLocal
from app.models import publication
from app.models.publication import Publication
from app.models.clip import Clip
from app.models.video import Video
from app.services.notifications import notify
from app.services.video_jobs import enqueue_video_processing
from app.workers.heartbeat import (
    last_recovery_heartbeat,
    last_worker_heartbeat,
)
from app.youtube.config import worker_stale_timeout
import time
from fastapi import Request
from datetime import datetime, timedelta
from sqlalchemy import func, text
from app.queue.redis_connectiuon import redis_conn

app = FastAPI(title="AxisClip API")

app.include_router(clips_router)
app.include_router(notifications_router)
app.include_router(publications_router)
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


@app.on_event("startup")
def recover_incomplete_video_jobs():
    db = SessionLocal()
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=worker_stale_timeout())
    recoverable_stages = {"TRANSCRIBING", "FINDING_CLIPS", "GENERATING_CLIPS"}

    try:
        videos = (
            db.query(Video)
            .filter(
                Video.status.in_(["PROCESSING", "FAILED"]),
                Video.processing_stage.in_(recoverable_stages),
            )
            .all()
        )

        for video in videos:
            error_text = f"{video.error_type or ''}\n{video.error_message or ''}"
            if video.status == "FAILED" and "Timeout" not in error_text and "JobTimeout" not in error_text:
                continue
            if video.last_heartbeat and video.last_heartbeat > stale_before:
                continue

            video.status = "PROCESSING"
            video.error_type = None
            video.error_message = None
            video.processing_message = "Processamento recuperado. Continuando automaticamente."
            video.last_progress_at = now
            video.last_heartbeat = now
            video.last_completed_step = "startup_recovery"
            db.commit()
            enqueue_video_processing(video.id)
            notify(
                db,
                event_key=f"video:{video.id}:startup_recovery:{int(now.timestamp())}",
                type="RECOVERY",
                title="Processamento recuperado",
                message=f"Video {video.id} retomado em {video.processing_stage} ({video.last_completed_clip} clips concluidos).",
                video_id=video.id,
            )
            print(
                "[RECOVERY] "
                f"video_id={video.id} stage={video.processing_stage} "
                f"last_completed_clip={video.last_completed_clip} "
                f"action=RESUME_FROM_CLIP_{(video.last_completed_clip or 0) + 1}"
            )
    finally:
        db.close()


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
    db = SessionLocal()

    try:
        db.execute(text("SELECT 1"))
        redis_status = "ok" if redis_conn.ping() else "error"
        statuses = ["SCHEDULED", "PENDING", "WAITING_RETRY", "UPLOADING", "PROCESSING", "FAILED", "PUBLISHED", "CANCELLED"]
        counts = {status.lower(): 0 for status in statuses}
        for status, total in db.query(Publication.status, func.count(Publication.id)).group_by(Publication.status).all():
            if status in statuses:
                counts[status.lower()] = total

        worker_heartbeat = last_worker_heartbeat()
        recovery_heartbeat = last_recovery_heartbeat()
        worker_status = "UNKNOWN"

        if worker_heartbeat:
            worker_status = (
                "ACTIVE"
                if worker_heartbeat >= datetime.utcnow() - timedelta(seconds=worker_stale_timeout())
                else "STALE"
            )

        published = counts.get("published", 0)
        failed = counts.get("failed", 0)
        avg_seconds = db.query(
            func.avg(func.extract("epoch", Publication.published_at - Publication.created_at))
        ).filter(
            Publication.published_at.isnot(None),
            Publication.created_at.isnot(None),
        ).scalar()
        if avg_seconds is not None:
            avg_seconds = round(float(avg_seconds), 2)
        retries = db.query(func.coalesce(func.sum(Publication.attempts), 0)).scalar() or 0

        return {
            "status": "ok",
            "application": "ok",
            "database": "ok",
            "redis": redis_status,
            "worker": worker_status,
            "heartbeat": {
                "worker": worker_heartbeat.isoformat() if worker_heartbeat else None,
                "recovery": recovery_heartbeat.isoformat() if recovery_heartbeat else None,
            },
            "worker_status": worker_status,
            "last_worker_heartbeat": worker_heartbeat.isoformat() if worker_heartbeat else None,
            "last_recovery_heartbeat": recovery_heartbeat.isoformat() if recovery_heartbeat else None,
            "metrics": {
                "clips_generated": db.query(Clip).count(),
                "publications": db.query(Publication).count(),
                "publications_success": published,
                "failures": failed,
                "retries": int(retries),
                "avg_publication_seconds": avg_seconds,
            },
            **counts,
        }
    finally:
        db.close()
