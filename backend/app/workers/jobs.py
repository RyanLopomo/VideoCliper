import time
from pathlib import Path

from app.db.database import SessionLocal
from app import models
from app.services.audio import extract_audio
from app.services.transcriber import transcribe_audio


def update_status(db, video_obj, status, error=None):
    video_obj.status = status
    video_obj.error_message = error
    db.add(video_obj)
    db.commit()


def process_video(video_id: int):
    db = SessionLocal()
    video_obj = None

    try:
        video_obj = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video_obj:
            return

        update_status(db, video_obj, "FINDING_CLIPS")
        clips = find_clips(transcript_path)
        print(clips)

        update_status(db, video_obj, "PROCESSING")
        time.sleep(2)
        update_status(db, video_obj, "TRANSCRIBING")

        video_path = Path(video_obj.file_path)
        project_folder = video_path.parent
        audio_path = project_folder / "audio.wav"
        transcript_path = project_folder / "transcript.json"

        extract_audio(str(video_path), str(audio_path))
        transcribe_audio(str(audio_path), str(transcript_path))

        time.sleep(3)
        update_status(db, video_obj, "FINDING_CLIPS")
        time.sleep(3)
        update_status(db, video_obj, "GENERATING_CLIPS")
        time.sleep(3)
        update_status(db, video_obj, "GENERATING_SUBTITLES")
        time.sleep(3)
        update_status(db, video_obj, "COMPLETED")

    except Exception as e:
        if video_obj:
            update_status(db, video_obj, "FAILED", str(e))
    finally:
        db.close()