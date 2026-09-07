import os
import json
import re
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SETTINGS_FILE = Path(os.getenv("PUBLICATION_SETTINGS_FILE", "/storage/publication_settings.json"))


def _settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _value(key: str, default: str):
    settings = _settings()
    return settings[key] if key in settings else os.getenv(key, default)


def _bool(value) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def youtube_auto_publish_enabled() -> bool:
    return _bool(_value("YOUTUBE_AUTO_PUBLISH", "false"))


def youtube_privacy_status() -> str:
    value = os.getenv("YOUTUBE_PRIVACY_STATUS", "public").lower()

    if value not in {"private", "unlisted", "public"}:
        return "private"

    return value


def max_uploads_per_day() -> int:
    return int(_value("MAX_UPLOADS_PER_DAY", "5"))


def publish_schedule() -> list[str]:
    raw = _value("PUBLISH_SCHEDULE", "09:00,12:00,18:00")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in raw.split(",") if item.strip()]


def publish_timezone() -> ZoneInfo:
    return ZoneInfo(str(_value("PUBLISH_TIMEZONE", "America/Sao_Paulo")))


def manual_upload_counts_toward_daily_limit() -> bool:
    return _bool(_value("MANUAL_UPLOAD_COUNTS_TOWARD_DAILY_LIMIT", "true"))


def publication_settings_snapshot() -> dict:
    return {
        "youtube_auto_publish": youtube_auto_publish_enabled(),
        "max_uploads_per_day": max_uploads_per_day(),
        "publish_schedule": publish_schedule(),
        "publish_timezone": str(publish_timezone()),
        "manual_upload_counts_toward_daily_limit": manual_upload_counts_toward_daily_limit(),
        "tiktok_enabled": tiktok_enabled(),
    }


def save_publication_settings(data: dict) -> dict:
    schedule = [str(item).strip() for item in data["publish_schedule"] if str(item).strip()]
    for item in schedule:
        if not re.match(r"^\d{2}:\d{2}$", item):
            raise ValueError("Horario invalido.")
        hour, minute = [int(part) for part in item.split(":", 1)]
        if hour > 23 or minute > 59:
            raise ValueError("Horario invalido.")

    ZoneInfo(str(data["publish_timezone"]))
    max_per_day = int(data["max_uploads_per_day"])
    if max_per_day < 0:
        raise ValueError("Limite diario invalido.")

    settings = _settings()
    settings.update(
        {
            "YOUTUBE_AUTO_PUBLISH": bool(data["youtube_auto_publish"]),
            "MAX_UPLOADS_PER_DAY": max_per_day,
            "PUBLISH_SCHEDULE": schedule,
            "PUBLISH_TIMEZONE": str(data["publish_timezone"]),
            "MANUAL_UPLOAD_COUNTS_TOWARD_DAILY_LIMIT": bool(data["manual_upload_counts_toward_daily_limit"]),
        }
    )
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return publication_settings_snapshot()


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


def youtube_redirect_uri() -> str:
    return os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8000/youtube/callback")


def dct_uri() -> str | None:
    return os.getenv("CT_URI")
