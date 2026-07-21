from redis import Redis
from rq import Queue

redis_conn = Redis(host="redis", port=6379)
video_queue = Queue("videos", connection=redis_conn, default_timeout=7200)
