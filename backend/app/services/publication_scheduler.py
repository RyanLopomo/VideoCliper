from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.clip import Clip
from app.models.publication import Publication, PublicationAccount
from app.services.notifications import notify
from app.youtube.config import publish_timezone
from app.youtube.publication_queue import enqueue_publication


DEFAULT_SUGGESTED_TIMES = ["09:00", "13:00", "18:00", "21:00"]
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass(frozen=True)
class ScheduleSlot:
    clip_id: int
    day: date
    time: str
    scheduled_at: datetime


def suggest_publish_times(max_per_day: int = 4) -> list[str]:
    if max_per_day <= 0:
        raise HTTPException(status_code=422, detail="Quantidade por dia deve ser maior que zero.")
    if max_per_day <= len(DEFAULT_SUGGESTED_TIMES):
        return DEFAULT_SUGGESTED_TIMES[:max_per_day]
    return DEFAULT_SUGGESTED_TIMES.copy()


def parse_start_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Data inicial invalida.")


def normalize_times(times: list[str]) -> list[str]:
    if not times:
        raise HTTPException(status_code=422, detail="Informe ao menos um horario.")

    seen = set()
    normalized = []
    for raw in times:
        value = str(raw).strip()
        if not TIME_RE.match(value):
            raise HTTPException(status_code=422, detail="Horario invalido.")
        hour, minute = [int(part) for part in value.split(":", 1)]
        if hour > 23 or minute > 59:
            raise HTTPException(status_code=422, detail="Horario invalido.")
        if value in seen:
            raise HTTPException(status_code=422, detail="Horarios duplicados nao sao permitidos.")
        seen.add(value)
        normalized.append(value)

    return sorted(normalized)


def _clip_order_key(clip: Clip):
    return (clip.start_time if clip.start_time is not None else 0, clip.id)


def eligible_clips(db: Session, clip_ids: list[int], platform: str, include_scheduled: bool = False) -> list[Clip]:
    if not clip_ids:
        raise HTTPException(status_code=422, detail="Nenhum clip informado.")

    clips = db.query(Clip).filter(Clip.id.in_(clip_ids)).all()
    found = {clip.id for clip in clips}
    missing = [clip_id for clip_id in clip_ids if clip_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Clips nao encontrados: {missing}.")

    existing = (
        db.query(Publication)
        .filter(
            Publication.clip_id.in_(clip_ids),
            Publication.platform == platform,
            Publication.status.notin_(["CANCELLED", "FAILED"]),
        )
        .all()
    )
    blocked = {
        publication.clip_id
        for publication in existing
        if not (include_scheduled and publication.status == "SCHEDULED")
    }
    return sorted(
        [clip for clip in clips if clip.status == "COMPLETED" and clip.id not in blocked],
        key=_clip_order_key,
    )


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def unique_day_slots(current_day: date, selected_times: list[str], max_per_day: int, local_now: datetime):
    slots = []
    seen = set()
    offset = 0

    while len(slots) < max_per_day:
        added = False
        for slot_time in selected_times:
            hour, minute = [int(part) for part in slot_time.split(":", 1)]
            base_dt = datetime.combine(current_day, time(hour, minute), tzinfo=local_now.tzinfo)
            if base_dt <= local_now:
                continue
            local_dt = base_dt + timedelta(minutes=offset)
            if local_dt.date() != current_day or local_dt <= local_now:
                continue
            key = _format_time(local_dt)
            if key in seen:
                continue
            seen.add(key)
            slots.append((key, local_dt))
            added = True
            if len(slots) >= max_per_day:
                break
        if not added and offset >= 24 * 60:
            break
        offset += 1

    return sorted(slots, key=lambda item: item[1])


def build_schedule_plan(
    clips: list[Clip],
    max_per_day: int,
    start_date: str,
    times: list[str],
    now: datetime | None = None,
    reserved_by_date: dict[str, int] | None = None,
) -> dict:
    if max_per_day <= 0:
        raise HTTPException(status_code=422, detail="Quantidade por dia deve ser maior que zero.")

    tz = publish_timezone()
    local_now = (now or datetime.now(timezone.utc)).astimezone(tz)
    current_day = parse_start_date(start_date)
    if current_day < local_now.date():
        raise HTTPException(status_code=422, detail="Data inicial nao pode estar no passado.")
    selected_times = normalize_times(times)
    reserved = reserved_by_date or {}
    clip_ids = [clip.id for clip in clips]
    total = len(clip_ids)
    days: list[dict] = []
    slots: list[ScheduleSlot] = []
    clip_index = 0

    if total == 0:
        return {
            "total_clips": 0,
            "max_per_day": max_per_day,
            "start_date": start_date,
            "times": selected_times,
            "estimated_days": 0,
            "days": [],
            "scheduled": [],
        }

    while clip_index < total:
        remaining_capacity = max_per_day - int(reserved.get(current_day.isoformat(), 0))
        day_slots = unique_day_slots(current_day, selected_times, max(remaining_capacity, 0), local_now)
        day_capacity = len(day_slots)
        if day_capacity > 0:
            day_clip_ids = []
            day_times = []
            for day_index in range(day_capacity):
                if clip_index >= total:
                    break
                slot_time, local_dt = day_slots[day_index]
                clip_id = clip_ids[clip_index]
                utc_dt = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
                slots.append(ScheduleSlot(clip_id=clip_id, day=current_day, time=slot_time, scheduled_at=utc_dt))
                day_clip_ids.append(clip_id)
                day_times.append(slot_time)
                clip_index += 1
            days.append(
                {
                    "date": current_day.isoformat(),
                    "count": len(day_clip_ids),
                    "times": day_times,
                    "clip_ids": day_clip_ids,
                }
            )

        current_day = current_day + timedelta(days=1)

    return {
        "total_clips": total,
        "max_per_day": max_per_day,
        "start_date": start_date,
        "times": selected_times,
        "estimated_days": len(days),
        "days": days,
        "scheduled": [
            {
                "clip_id": slot.clip_id,
                "date": slot.day.isoformat(),
                "time": slot.time,
                "scheduled_at": slot.scheduled_at.isoformat(),
            }
            for slot in slots
        ],
    }


def _default_account_id(db: Session, platform: str) -> int | None:
    account = (
        db.query(PublicationAccount)
        .filter(
            PublicationAccount.platform == platform,
            PublicationAccount.enabled.is_(True),
            PublicationAccount.is_default.is_(True),
        )
        .first()
    )
    return account.id if account else None


def scheduled_counts_by_date(db: Session, platform: str, exclude_clip_ids: set[int] | None = None) -> dict[str, int]:
    tz = publish_timezone()
    rows = (
        db.query(Publication)
        .filter(
            Publication.platform == platform,
            Publication.status == "SCHEDULED",
            Publication.scheduled_at.isnot(None),
        )
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for publication in rows:
        if exclude_clip_ids and publication.clip_id in exclude_clip_ids:
            continue
        local = publication.scheduled_at.replace(tzinfo=timezone.utc).astimezone(tz)
        counts[local.date().isoformat()] += 1
    return dict(counts)


def create_scheduled_publications(
    db: Session,
    clips: list[Clip],
    platform: str,
    max_per_day: int,
    start_date: str,
    times: list[str],
) -> dict:
    clip_ids = {clip.id for clip in clips}
    plan = build_schedule_plan(
        clips,
        max_per_day,
        start_date,
        times,
        reserved_by_date=scheduled_counts_by_date(db, platform, exclude_clip_ids=clip_ids),
    )
    clips_by_id = {clip.id: clip for clip in clips}
    account_id = _default_account_id(db, platform)
    publications = []

    for item in plan["scheduled"]:
        clip = clips_by_id[item["clip_id"]]
        scheduled_at = datetime.fromisoformat(item["scheduled_at"])
        publication = (
            db.query(Publication)
            .filter(Publication.clip_id == clip.id, Publication.platform == platform)
            .first()
        )
        if publication and publication.status == "SCHEDULED" and not publication.platform_post_id:
            publication.scheduled_at = scheduled_at
            publication.manual = True
            publication.error_type = None
            publication.error_details = None
            publication.next_retry = None
            publication.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(publication)
        else:
            publication = enqueue_publication(
                db,
                clip,
                platform=platform,
                publication_account_id=account_id,
                status="SCHEDULED",
                scheduled_at=scheduled_at,
                manual=True,
            )
        publications.append(publication)
        notify(
            db,
            event_key=f"publication:{publication.id}:scheduled",
            type="PROCESSING_STARTED",
            title="Clip agendado",
            message=f"Publicacao agendada para {scheduled_at.isoformat()}.",
            clip_id=clip.id,
            publication_id=publication.id,
            platform=platform,
        )

    grouped = defaultdict(int)
    for item in plan["scheduled"]:
        grouped[item["date"]] += 1

    return {
        **plan,
        "created_publications": len(publications),
        "publication_ids": [publication.id for publication in publications],
        "days": [{**day, "count": grouped[day["date"]]} for day in plan["days"]],
    }
