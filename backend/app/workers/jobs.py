import traceback

from app.db.database import SessionLocal

from app.pipeline.pipeline import VideoPipeline

from app.utils.pipeline_logger import log


def process_video(video_id: int):

    db = SessionLocal()

    log(
        "WORKER",
        f"Iniciando processamento do vídeo {video_id}"
    )

    try:

        pipeline = VideoPipeline(
            db=db,
            video_id=video_id,
        )

        pipeline.run()

        log(
            "WORKER",
            f"Vídeo {video_id} concluído."
        )

    except Exception:

        log(
            "WORKER",
            traceback.format_exc()
        )

        raise

    finally:

        db.close()

        log(
            "WORKER",
            "Sessão do banco encerrada."
        )