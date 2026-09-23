import os

from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.queue.redis_connectiuon import redis_conn, video_queue
from app.utils.pipeline_logger import log


def pipeline_job_timeout() -> int:
    try:
        return max(300, int(os.getenv("PIPELINE_JOB_TIMEOUT", "7200")))
    except ValueError:
        return 7200


def enqueue_video_processing(video_id: int):
    job_id = f"process-video-{video_id}"
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        if job.get_status(refresh=True) in {"queued", "started", "deferred", "scheduled"}:
            log(
                "PIPELINE",
                f"video_id={video_id} job_id={job_id} action=SKIP_DUPLICATE_JOB status={job.get_status(refresh=True)}",
            )
            return job
        job.delete()
    except NoSuchJobError:
        pass

    log(
        "PIPELINE",
        f"video_id={video_id} job_id={job_id} action=ENQUEUE",
    )
    return video_queue.enqueue(
        "app.workers.jobs.process_video",
        video_id,
        job_timeout=pipeline_job_timeout(),
        job_id=job_id,
    )
