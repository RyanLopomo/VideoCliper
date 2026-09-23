import asyncio
import json
import threading
import uuid
from datetime import datetime


class DownloadCancelled(RuntimeError):
    pass


_lock = threading.RLock()
_downloads: dict[str, dict] = {}
_subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
_cancelled: set[str] = set()


def _snapshot(item: dict) -> dict:
    return {
        "download_id": item["download_id"],
        "video_id": item.get("video_id"),
        "status": item["status"],
        "progress": item.get("progress"),
        "downloaded_bytes": item.get("downloaded_bytes"),
        "total_bytes": item.get("total_bytes"),
        "speed_bytes": item.get("speed_bytes"),
        "eta_seconds": item.get("eta_seconds"),
        "filename": item.get("filename"),
        "message": item.get("message"),
        "updated_at": item.get("updated_at"),
    }


def _event(event: str, item: dict) -> dict:
    return {"event": event, "data": _snapshot(item)}


def _publish(event: str, item: dict) -> None:
    payload = _event(event, item)
    stale = []
    for loop, queue in list(_subscribers):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, payload)
        except RuntimeError:
            stale.append((loop, queue))
    for subscriber in stale:
        if subscriber in _subscribers:
            _subscribers.remove(subscriber)


def start_download(filename: str | None = None, video_id: int | None = None) -> str:
    download_id = str(uuid.uuid4())
    item = {
        "download_id": download_id,
        "video_id": video_id,
        "status": "downloading",
        "progress": None,
        "downloaded_bytes": None,
        "total_bytes": None,
        "speed_bytes": None,
        "eta_seconds": None,
        "filename": filename,
        "updated_at": datetime.utcnow().isoformat(),
    }
    with _lock:
        _downloads[download_id] = item
    _publish("DOWNLOAD_STARTED", item)
    return download_id


def update_download(download_id: str, payload: dict) -> None:
    with _lock:
        item = _downloads.get(download_id)
        if not item or item["status"] != "downloading":
            return
        total = payload.get("total_bytes") or payload.get("total_bytes_estimate")
        downloaded = payload.get("downloaded_bytes")
        progress = None
        if total and downloaded is not None:
            progress = max(0, min((float(downloaded) / float(total)) * 100, 100))
        item.update(
            {
                "progress": round(progress, 1) if progress is not None else None,
                "downloaded_bytes": downloaded,
                "total_bytes": total,
                "speed_bytes": payload.get("speed"),
                "eta_seconds": payload.get("eta"),
                "filename": payload.get("filename") or item.get("filename"),
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        snapshot = dict(item)
    _publish("DOWNLOAD_PROGRESS", snapshot)


def complete_download(download_id: str, video_id: int | None = None) -> None:
    with _lock:
        item = _downloads.get(download_id)
        if not item:
            return
        item["status"] = "completed"
        item["video_id"] = video_id or item.get("video_id")
        item["updated_at"] = datetime.utcnow().isoformat()
        snapshot = dict(item)
    _publish("DOWNLOAD_COMPLETED", snapshot)


def fail_download(download_id: str, message: str) -> None:
    with _lock:
        item = _downloads.get(download_id)
        if not item:
            return
        item["status"] = "error"
        item["message"] = message[:300]
        item["updated_at"] = datetime.utcnow().isoformat()
        snapshot = dict(item)
    _publish("DOWNLOAD_ERROR", snapshot)


def cancel_download(download_id: str) -> bool:
    with _lock:
        item = _downloads.get(download_id)
        if not item:
            return False
        _cancelled.add(download_id)
        item["status"] = "cancelled"
        item["message"] = "Download cancelado."
        item["updated_at"] = datetime.utcnow().isoformat()
        snapshot = dict(item)
    _publish("DOWNLOAD_CANCELLED", snapshot)
    return True


def raise_if_cancelled(download_id: str) -> None:
    with _lock:
        cancelled = download_id in _cancelled
    if cancelled:
        raise DownloadCancelled("Download cancelado.")


def active_downloads() -> list[dict]:
    with _lock:
        return [_snapshot(item) for item in _downloads.values() if item["status"] == "downloading"]


async def subscribe():
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    loop = asyncio.get_running_loop()
    with _lock:
        _subscribers.append((loop, queue))
        current = [_event("DOWNLOAD_PROGRESS", item) for item in _downloads.values()]
    for item in current:
        await queue.put(item)
    try:
        while True:
            item = await queue.get()
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
    finally:
        with _lock:
            subscriber = (loop, queue)
            if subscriber in _subscribers:
                _subscribers.remove(subscriber)
