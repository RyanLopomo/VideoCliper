import os
from datetime import timedelta


def youtube_auto_publish_enabled() -> bool:
    return os.getenv("YOUTUBE_AUTO_PUBLISH", "false").lower() == "true"


def youtube_privacy_status() -> str:
    value = os.getenv("YOUTUBE_PRIVACY_STATUS", "public").lower()

    if value not in {"private", "unlisted", "public"}:
        return "private"

    return value


def publisher_max_attempts() -> int:
    return int(os.getenv("PUBLISHER_MAX_ATTEMPTS", "5"))


def publisher_retry_delays() -> list[int]:
    raw = os.getenv("PUBLISHER_RETRY_DELAYS", "5,15,30,60")
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def publisher_upload_timeout_minutes() -> int:
    return int(os.getenv("PUBLISHER_UPLOAD_TIMEOUT", "60"))


def publisher_processing_timeout_minutes() -> int:
    return int(os.getenv("PUBLISHER_PROCESSING_TIMEOUT", "180"))


def retry_delay_for_attempt(attempt: int) -> timedelta:
    delays = publisher_retry_delays()
    index = min(max(attempt - 1, 0), len(delays) - 1)
    return timedelta(minutes=delays[index])


def publisher_poll_interval() -> int:
    return int(os.getenv("PUBLISHER_POLL_INTERVAL", "60"))


def recovery_interval() -> int:
    return int(os.getenv("RECOVERY_INTERVAL", "300"))


def worker_stale_timeout() -> int:
    return int(os.getenv("WORKER_STALE_TIMEOUT", "300"))


def youtube_processing_poll_interval() -> int:
    return int(os.getenv("YOUTUBE_PROCESSING_POLL_INTERVAL", "60"))


def publisher_max_concurrent() -> int:
    return int(os.getenv("PUBLISHER_MAX_CONCURRENT", "1"))


def cleanup_after_publish() -> bool:
    return os.getenv("CLEANUP_AFTER_PUBLISH", "true").lower() == "true"


def worker_run_once() -> bool:
    return os.getenv("WORKER_RUN_ONCE", "false").lower() == "true"


def tiktok_enabled() -> bool:
    return os.getenv("TIKTOK_ENABLED", "false").lower() == "true"


def frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")


def dct_uri() -> str | None:
    return os.getenv("CT_URI")
