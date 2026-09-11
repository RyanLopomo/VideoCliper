from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.queue.redis_connectiuon import redis_conn, video_queue


def enqueue_video_processing(video_id: int):
    job_id = f"process-video-{video_id}"
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        if job.get_status(refresh=True) in {"queued", "started", "deferred", "scheduled"}:
            return job
        job.delete()
    except NoSuchJobError:
        pass

    return video_queue.enqueue(
        "app.workers.jobs.process_video",
        video_id,
        job_timeout=7200,
        job_id=job_id,
    )
