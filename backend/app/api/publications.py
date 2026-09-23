from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2 import InsecureTransportError, MismatchingStateError, OAuth2Error
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.db.dependencies import get_db
from app.models.clip import Clip
from app.models.publication import Publication, PublicationAccount
from app.youtube.auth import (
    TOKEN_FILE,
    authorization_url,
    disconnect_credentials,
    get_saved_credentials,
    save_credentials_from_callback,
)
from app.services.notifications import notify
from app.services.publication_scheduler import (
    create_scheduled_publications,
    eligible_clips,
    scheduled_counts_by_date,
    suggest_publish_times,
    build_schedule_plan,
)
from app.youtube.config import (
    frontend_base_url,
    max_uploads_per_day,
    publication_settings_snapshot,
    publish_schedule,
    publish_timezone,
    save_publication_settings,
    youtube_redirect_uri,
)
from app.youtube.publication_queue import enqueue_publication
from app.youtube.publication_urls import publication_url
from app.youtube.schedule_control import (
    cancel_youtube_publish_at,
    get_youtube_publication_state,
    update_youtube_publish_at,
)

router = APIRouter()


class PublicationCreate(BaseModel):
    clip_id: int
    platform: str = "YOUTUBE"
    publication_account_id: int | None = None
    scheduled_at: str | None = None


class PublicationScheduleUpdate(BaseModel):
    scheduled_at: str


class PublicationSettingsUpdate(BaseModel):
    youtube_auto_publish: bool
    max_uploads_per_day: int
    publish_schedule: list[str]
    publish_timezone: str
    manual_upload_counts_toward_daily_limit: bool


class PublicationPlanRequest(BaseModel):
    clip_ids: list[int]
    platform: str = "YOUTUBE"
    max_per_day: int
    start_date: str
    times: list[str]


class PublicationSuggestionRequest(BaseModel):
    max_per_day: int = 4


def build_platform_url(publication: Publication) -> str | None:
    return publication_url(publication)


def serialize_account(account: PublicationAccount) -> dict:
    return {
        "id": account.id,
        "platform": account.platform,
        "account_name": account.account_name,
        "platform_account_id": account.platform_account_id,
        "enabled": account.enabled,
        "is_default": account.is_default,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def serialize_publication(publication: Publication) -> dict:
    clip = publication.clip
    account = publication.publication_account
    duration = None
    if clip and clip.start_time is not None and clip.end_time is not None:
        duration = round(float(clip.end_time) - float(clip.start_time), 1)
    return {
        "id": publication.id,
        "clip_id": publication.clip_id,
        "title": clip.title if clip else None,
        "duration": duration,
        "thumbnail_url": f"/clips/{clip.id}/thumbnail" if clip and clip.thumbnail_path else None,
        "platform": publication.platform,
        "account": serialize_account(account) if account else None,
        "status": publication.status,
        "error_type": publication.error_type,
        "error_details": publication.error_details,
        "attempts": publication.attempts,
        "created_at": publication.created_at,
        "updated_at": publication.updated_at,
        "published_at": publication.published_at,
        "scheduled_at": publication.scheduled_at,
        "manual": publication.manual,
        "next_retry": publication.next_retry,
        "platform_post_id": publication.platform_post_id,
        "publication_url": build_platform_url(publication),
        "timezone": str(publish_timezone()),
    }


def _parse_optional_youtube_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _http_exception_from_youtube_error(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, HttpError):
        status = int(getattr(getattr(exc, "resp", None), "status", 0) or 502)
        raise HTTPException(status_code=502, detail=f"YouTube rejeitou a atualizacao. HTTP {status}.") from exc
    raise HTTPException(status_code=502, detail=str(exc) or "Falha ao sincronizar com o YouTube.") from exc


def sync_publication_with_youtube(db: Session, publication: Publication) -> Publication:
    if publication.platform != "YOUTUBE" or not publication.platform_post_id:
        return publication
    if publication.status not in {"SCHEDULED", "UPLOADING", "PROCESSING", "PUBLISHED"}:
        return publication
    try:
        state = get_youtube_publication_state(publication.platform_post_id)
    except Exception:
        return publication

    if not state.get("exists"):
        return publication

    upload_status = state.get("upload_status")
    privacy_status = state.get("privacy_status")
    publish_at = _parse_optional_youtube_datetime(state.get("publish_at"))
    published_at = _parse_optional_youtube_datetime(state.get("published_at"))
    now = datetime.utcnow()

    if upload_status == "processed" and privacy_status == "public":
        publication.status = "PUBLISHED"
        publication.published_at = published_at or publication.published_at or now
        publication.next_retry = None
        publication.error_type = None
        publication.error_details = None
    elif privacy_status == "private" and publish_at and publish_at > now:
        publication.status = "SCHEDULED"
        publication.scheduled_at = publish_at
    elif publication.status == "PUBLISHED":
        publication.status = "PROCESSING"
    elif publication.status == "SCHEDULED" and privacy_status == "private" and not publish_at:
        publication.status = "CANCELLED"

    publication.updated_at = now
    db.commit()
    db.refresh(publication)
    return publication


def parse_scheduled_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Data de agendamento invalida.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=publish_timezone())
    utc_value = parsed.astimezone(timezone.utc)
    if utc_value <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Agendamento nao pode estar no passado.")
    return utc_value.replace(tzinfo=None)


def ensure_schedule_available(db: Session, platform: str, scheduled_at: datetime, publication_id: int | None = None):
    query = (
        db.query(Publication)
        .filter(
            Publication.platform == platform,
            Publication.status == "SCHEDULED",
            Publication.scheduled_at == scheduled_at,
        )
    )
    if publication_id is not None:
        query = query.filter(Publication.id != publication_id)
    existing = query.first()
    if existing:
        raise HTTPException(status_code=409, detail="Horario ja possui publicacao agendada.")


def ensure_daily_schedule_limit(db: Session, scheduled_at: datetime, publication_id: int | None = None):
    tz = publish_timezone()
    local = scheduled_at.replace(tzinfo=timezone.utc).astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    end = (local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
    limit = min(max_uploads_per_day(), len(publish_schedule()) or max_uploads_per_day())
    query = db.query(Publication).filter(
        Publication.status == "SCHEDULED",
        Publication.scheduled_at >= start,
        Publication.scheduled_at < end,
    )
    if publication_id is not None:
        query = query.filter(Publication.id != publication_id)
    if query.count() >= limit:
        raise HTTPException(status_code=409, detail="Limite diario de agendamentos atingido.")


def default_account(db: Session, platform: str) -> PublicationAccount | None:
    return (
        db.query(PublicationAccount)
        .filter(
            PublicationAccount.platform == platform,
            PublicationAccount.enabled.is_(True),
            PublicationAccount.is_default.is_(True),
        )
        .first()
    )


@router.get("/publication-accounts")
def list_publication_accounts(db: Session = Depends(get_db)):
    return [serialize_account(account) for account in db.query(PublicationAccount).order_by(PublicationAccount.id).all()]


@router.get("/publication-settings")
def publication_settings():
    return publication_settings_snapshot()


@router.put("/publication-settings")
def update_publication_settings(payload: PublicationSettingsUpdate):
    try:
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        return save_publication_settings(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/publication-accounts/{account_id}")
def get_publication_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(PublicationAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta nao encontrada.")
    return serialize_account(account)


def upsert_youtube_account(db: Session, credentials) -> PublicationAccount:
    youtube = build("youtube", "v3", credentials=credentials)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="Canal YouTube nao encontrado.")

    channel = items[0]
    channel_id = channel["id"]
    account_name = channel.get("snippet", {}).get("title") or "YouTube"
    account = (
        db.query(PublicationAccount)
        .filter(
            PublicationAccount.platform == "YOUTUBE",
            PublicationAccount.platform_account_id == channel_id,
        )
        .first()
    )

    if not account:
        account = PublicationAccount(
            platform="YOUTUBE",
            account_name=account_name,
            platform_account_id=channel_id,
            enabled=True,
            is_default=db.query(PublicationAccount).filter(PublicationAccount.platform == "YOUTUBE").count() == 0,
            credential_path=str(TOKEN_FILE),
        )
        db.add(account)
    else:
        account.account_name = account_name
        account.enabled = True
        account.credential_path = str(TOKEN_FILE)
        account.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(account)
    return account


@router.get("/youtube/account")
def youtube_account(db: Session = Depends(get_db)):
    account = default_account(db, "YOUTUBE")
    credentials = get_saved_credentials()
    if not account or not account.enabled:
        return {"connected": False, "status": "DISCONNECTED"}
    return {
        "connected": bool(credentials),
        "status": "CONNECTED" if credentials else "INVALID",
        "channel_name": account.account_name,
        "channel_title": account.account_name,
        "channel_thumbnail": None,
        "channel_id": account.platform_account_id,
        "account": serialize_account(account),
    }


@router.get("/youtube/auth")
def start_youtube_auth():
    try:
        redirect_uri = youtube_redirect_uri()
        print(f"OAuth authorization started redirect_uri={redirect_uri}")
        return {"auth_url": authorization_url(redirect_uri)}
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Credencial do YouTube nao configurada.")


@router.get("/youtube/callback", name="youtube_callback")
def youtube_callback(request: Request, db: Session = Depends(get_db)):
    redirect_uri = youtube_redirect_uri()
    print(f"OAuth callback received redirect_uri={redirect_uri}")
    if request.query_params.get("error"):
        print("OAuth callback denied")
        return RedirectResponse(f"{frontend_base_url()}/settings?youtube=error")
    try:
        print(
            "OAuth callback params "
            f"code_received={bool(request.query_params.get('code'))} "
            f"state_received={bool(request.query_params.get('state'))}"
        )
        print("OAuth token exchange started")
        credentials = save_credentials_from_callback(
            redirect_uri,
            str(request.url),
        )
        print("OAuth token exchange succeeded")
        account = upsert_youtube_account(db, credentials)
        print(f"Canal identificado channel_id={account.platform_account_id}")
        db.query(PublicationAccount).filter(PublicationAccount.platform == "YOUTUBE").update({"is_default": False})
        account.is_default = True
        account.enabled = True
        account.updated_at = datetime.utcnow()
        db.commit()
        print(f"Conta salva account_id={account.id}")
        print("Redirect executado")
        return RedirectResponse(f"{frontend_base_url()}/settings?youtube=connected")
    except (HttpError, RuntimeError, ValueError, InsecureTransportError, MismatchingStateError, OAuth2Error) as e:
        print(f"OAuth token exchange failed error_type={type(e).__name__}")
        return RedirectResponse(f"{frontend_base_url()}/settings?youtube=error")


@router.post("/youtube/disconnect")
def disconnect_youtube(db: Session = Depends(get_db)):
    disconnect_credentials()
    db.query(PublicationAccount).filter(PublicationAccount.platform == "YOUTUBE").update(
        {"enabled": False, "is_default": False, "updated_at": datetime.utcnow()}
    )
    db.commit()
    return {"connected": False, "status": "DISCONNECTED"}


@router.post("/publication-accounts/youtube/connect")
def connect_youtube_account(db: Session = Depends(get_db)):
    credentials = get_saved_credentials()
    if not credentials:
        raise HTTPException(status_code=400, detail="Conta YouTube nao conectada.")
    account = upsert_youtube_account(db, credentials)
    return serialize_account(account)


@router.post("/publication-accounts/{account_id}/set-default")
def set_default_publication_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(PublicationAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta nao encontrada.")
    db.query(PublicationAccount).filter(PublicationAccount.platform == account.platform).update({"is_default": False})
    account.is_default = True
    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.delete("/publication-accounts/{account_id}")
def delete_publication_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(PublicationAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta nao encontrada.")
    account.enabled = False
    account.is_default = False
    account.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/publications")
def list_publications(db: Session = Depends(get_db)):
    publications = (
        db.query(Publication)
        .options(
            joinedload(Publication.clip),
            joinedload(Publication.publication_account),
        )
        .order_by(Publication.created_at.desc())
        .all()
    )
    return [serialize_publication(sync_publication_with_youtube(db, item)) for item in publications]


@router.post("/publications/schedule/suggestions")
def publication_schedule_suggestions(payload: PublicationSuggestionRequest):
    return {"times": suggest_publish_times(payload.max_per_day)}


@router.post("/publications/schedule/preview")
def preview_publication_schedule(payload: PublicationPlanRequest, db: Session = Depends(get_db)):
    platform = payload.platform.upper()
    clips = eligible_clips(db, payload.clip_ids, platform, include_scheduled=True)
    clip_ids = {clip.id for clip in clips}
    return build_schedule_plan(
        clips,
        payload.max_per_day,
        payload.start_date,
        payload.times,
        reserved_by_date=scheduled_counts_by_date(db, platform, exclude_clip_ids=clip_ids),
    )


@router.post("/publications/schedule/confirm")
def confirm_publication_schedule(payload: PublicationPlanRequest, db: Session = Depends(get_db)):
    platform = payload.platform.upper()
    clips = eligible_clips(db, payload.clip_ids, platform, include_scheduled=True)
    result = create_scheduled_publications(
        db,
        clips,
        platform,
        payload.max_per_day,
        payload.start_date,
        payload.times,
    )
    return result


@router.get("/publications/{publication_id}")
def get_publication(publication_id: int, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Publicacao nao encontrada.")
    return serialize_publication(publication)


@router.post("/publications")
def create_publication(payload: PublicationCreate, db: Session = Depends(get_db)):
    clip = db.get(Clip, payload.clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip nao encontrado.")
    platform = payload.platform.upper()
    account_id = payload.publication_account_id
    if account_id is None:
        account = default_account(db, platform)
        account_id = account.id if account else None
    scheduled_at = parse_scheduled_at(payload.scheduled_at) if payload.scheduled_at else None
    if scheduled_at:
        ensure_schedule_available(db, platform, scheduled_at)
        ensure_daily_schedule_limit(db, scheduled_at)
    publication = enqueue_publication(
        db,
        clip,
        platform=platform,
        publication_account_id=account_id,
        status="SCHEDULED" if scheduled_at else "PENDING",
        scheduled_at=scheduled_at,
        manual=True,
    )
    is_scheduled = publication.status == "SCHEDULED"
    notify(
        db,
        event_key=f"publication:{publication.id}:{'scheduled' if is_scheduled else 'queued'}",
        type="PROCESSING_STARTED",
        title="Clip agendado" if is_scheduled else "Clip adicionado a fila de publicacao",
        message=(
            f"Publicacao agendada para {publication.scheduled_at.isoformat()}."
            if is_scheduled and publication.scheduled_at
            else "O publisher fara o upload pelo worker."
        ),
        clip_id=clip.id,
        publication_id=publication.id,
        platform=platform,
    )
    return serialize_publication(publication)


@router.patch("/publications/{publication_id}/schedule")
def update_publication_schedule(publication_id: int, payload: PublicationScheduleUpdate, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Publicacao nao encontrada.")
    if publication.status != "SCHEDULED":
        raise HTTPException(status_code=409, detail="Somente publicacoes agendadas podem ser editadas.")
    scheduled_at = parse_scheduled_at(payload.scheduled_at)
    ensure_schedule_available(db, publication.platform, scheduled_at, publication_id)
    ensure_daily_schedule_limit(db, scheduled_at, publication_id)
    if publication.platform == "YOUTUBE" and publication.platform_post_id:
        try:
            update_youtube_publish_at(publication.platform_post_id, scheduled_at)
        except Exception as exc:
            _http_exception_from_youtube_error(exc)
    publication.scheduled_at = scheduled_at
    publication.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(publication)
    return serialize_publication(publication)


@router.post("/publications/{publication_id}/cancel")
def cancel_publication(publication_id: int, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Publicacao nao encontrada.")
    if publication.status != "SCHEDULED":
        raise HTTPException(status_code=409, detail="Somente agendamentos podem ser cancelados.")
    if publication.platform == "YOUTUBE" and publication.platform_post_id:
        try:
            cancel_youtube_publish_at(publication.platform_post_id)
        except Exception as exc:
            _http_exception_from_youtube_error(exc)
    publication.status = "CANCELLED"
    publication.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(publication)
    return serialize_publication(publication)
