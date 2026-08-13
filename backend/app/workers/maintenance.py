import argparse

from app.db.database import SessionLocal
from app.models.publication import Publication
from app.utils.pipeline_logger import log
from app.workers.recovery import recover_stuck_publications
from app.youtube.cleanup import cleanup_clip_files


def list_publications(status: str):
    db = SessionLocal()
    try:
        for pub in db.query(Publication).filter(Publication.status == status).order_by(Publication.created_at.asc()).all():
            print(f"{pub.id} clip={pub.clip_id} platform={pub.platform} attempts={pub.attempts} error={pub.error_type}")
    finally:
        db.close()


def cleanup_published():
    db = SessionLocal()
    try:
        count = 0
        for pub in db.query(Publication).filter(Publication.status == "PUBLISHED").all():
            cleanup_clip_files(pub.clip)
            count += 1
        log("CLEANUP", f"cleanup_manual count={count}")
    finally:
        db.close()


def alert_admin(message: str):
    log("ALERT", message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["failed", "pending", "recovery", "cleanup", "health"])
    args = parser.parse_args()

    if args.command == "failed":
        list_publications("FAILED")
    elif args.command == "pending":
        list_publications("PENDING")
    elif args.command == "recovery":
        db = SessionLocal()
        try:
            print(recover_stuck_publications(db))
        finally:
            db.close()
    elif args.command == "cleanup":
        cleanup_published()
    elif args.command == "health":
        from app.main import health
        print(health())


if __name__ == "__main__":
    main()
