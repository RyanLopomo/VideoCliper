import traceback
from datetime import datetime

from rq import get_current_job

from app.db.database import SessionLocal
from app.models.video import Video
from app.pipeline.pipeline import VideoPipeline
from app.utils.pipeline_logger import log


def process_video(video_id: int):
    db = SessionLocal()

    log(
        "WORKER",
        f"Iniciando processamento do video {video_id}",
    )

    try:
        job = get_current_job()
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.current_job_id = job.id if job else f"process-video-{video_id}"
            video.status = "PROCESSING"
            video.last_heartbeat = datetime.utcnow()
            db.commit()

        pipeline = VideoPipeline(
            db=db,
            video_id=video_id,
        )

        pipeline.run()

        log(
            "WORKER",
            f"Video {video_id} concluido.",
        )

    except Exception:
        log(
            "WORKER",
            traceback.format_exc(),
        )

        raise

    finally:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video and video.status in {"COMPLETED", "FAILED", "PAUSED"}:
            video.current_job_id = None
            db.commit()

        db.close()

        log(
            "WORKER",
            "Sessao do banco encerrada.",
        )
