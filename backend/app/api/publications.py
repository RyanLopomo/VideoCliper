from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2 import InsecureTransportError, MismatchingStateError, OAuth2Error
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
from app.youtube.config import frontend_base_url, youtube_redirect_uri
from app.youtube.publication_urls import publication_url

router = APIRouter()


class PublicationCreate(BaseModel):
    clip_id: int
    platform: str = "YOUTUBE"
    publication_account_id: int | None = None


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
    return {
        "id": publication.id,
        "clip_id": publication.clip_id,
        "title": clip.title if clip else None,
        "thumbnail_url": f"/clips/{clip.id}/thumbnail" if clip and clip.thumbnail_path else None,
        "platform": publication.platform,
        "account": serialize_account(account) if account else None,
        "status": publication.status,
        "attempts": publication.attempts,
        "created_at": publication.created_at,
        "updated_at": publication.updated_at,
        "published_at": publication.published_at,
        "platform_post_id": publication.platform_post_id,
        "publication_url": build_platform_url(publication),
    }


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
    return [serialize_publication(item) for item in db.query(Publication).order_by(Publication.created_at.desc()).all()]


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

    publication = Publication(
        clip_id=clip.id,
        platform=platform,
        publication_account_id=account_id,
        status="PENDING",
    )
    db.add(publication)
    db.commit()
    db.refresh(publication)
    return serialize_publication(publication)
