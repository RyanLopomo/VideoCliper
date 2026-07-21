from app.utils.pipeline_logger import log


class VideoPipeline:

    def __init__(self, db, video, project):
        self.db = db
        self.video = video
        self.project = project

    def run(self):
        log(
            "PIPELINE",
            f"Iniciando processamento do vídeo {self.video.id}"
        )