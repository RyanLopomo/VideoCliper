from datetime import datetime
from pathlib import Path


HEARTBEAT_FILE = Path(__file__).resolve().parents[2] / ".publisher_heartbeat"
RECOVERY_FILE = Path(__file__).resolve().parents[2] / ".recovery_heartbeat"


def write_timestamp(path: Path):
    path.write_text(datetime.utcnow().isoformat(), encoding="utf-8")


def read_timestamp(path: Path):
    if not path.exists():
        return None

    try:
        return datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def worker_heartbeat():
    write_timestamp(HEARTBEAT_FILE)


def recovery_heartbeat():
    write_timestamp(RECOVERY_FILE)


def last_worker_heartbeat():
    return read_timestamp(HEARTBEAT_FILE)


def last_recovery_heartbeat():
    return read_timestamp(RECOVERY_FILE)
