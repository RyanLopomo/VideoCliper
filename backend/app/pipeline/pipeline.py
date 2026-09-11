import traceback

from app.pipeline.context import PipelineContext

from app.pipeline import stages
from app.pipeline import recovery
from app.pipeline import checkpoint

from app.services.video_cutter import generate_clip
from app.services.reel_adapter import adapt_to_reel
from app.services.subtitle_generator import (
    filter_segments_for_clip,
    adjust_segments,
    generate_srt,
    burn_subtitles,
)
from app.services.thumbnail import generate_thumbnail

from app.core.retry import retry
from app.utils.pipeline_logger import log
from app.services.notifications import notify
from app.services.video_publication_plan import apply_video_publication_plan
from app.youtube.integration import publish_completed_clip


class PipelinePaused(Exception):
    pass


class VideoPipeline:

    def __init__(
        self,
        db,
        video_id,
    ):

        self.ctx = PipelineContext(
            db=db,
            video_id=video_id,
        )

    def run(self):

        try:

            stages.load_video(self.ctx)
            self.stop_if_paused()

            notify(
                self.ctx.db,
                event_key=f"video:{self.ctx.video.id}:processing_started",
                type="PROCESSING_STARTED",
                title="Processamento iniciado",
                message=f"Video {self.ctx.video.id} entrou na fila de processamento.",
                video_id=self.ctx.video.id,
            )

            stages.prepare_storage(self.ctx)
            self.stop_if_paused()

            recovery.recover_stage(self.ctx)
            self.stop_if_paused()

            stages.transcribe_video(self.ctx)
            self.stop_if_paused()

            stages.find_video_clips(self.ctx)
            self.stop_if_paused()

            self.process_clips()
            self.stop_if_paused()

            if self.ctx.video.publication_plan_enabled:
                apply_video_publication_plan(self.ctx.db, self.ctx.video)
            else:
                for clip in self.ctx.video.clips:
                    if clip.status == "COMPLETED":
                        publish_completed_clip(self.ctx.db, clip)

            checkpoint.video_completed(
                self.ctx.db,
                self.ctx.video,
            )

            notify(
                self.ctx.db,
                event_key=f"video:{self.ctx.video.id}:processing_completed",
                type="PROCESSING_COMPLETED",
                title="Clips prontos",
                message=f"Video {self.ctx.video.id} finalizado. Clips disponiveis.",
                video_id=self.ctx.video.id,
            )

            recovery.clear_processing(
                self.ctx,
            )

            log(
                "PIPELINE",
                "Pipeline finalizado."
            )

        except PipelinePaused:
            log("PIPELINE", f"Video {self.ctx.video.id} pausado.")

        except Exception:

            if self.ctx.video is not None:
                checkpoint.video_failed(
                    self.ctx.db,
                    self.ctx.video,
                    traceback.format_exc(),
                )

                notify(
                    self.ctx.db,
                    event_key=f"video:{self.ctx.video.id}:processing_error",
                    type="ERROR",
                    title="Falha no processamento",
                    message=f"Etapa: {self.ctx.video.processing_stage}. Motivo: processamento interrompido.",
                    video_id=self.ctx.video.id,
                )

            raise

    def process_clips(self):

        checkpoint.save_stage(
            self.ctx.db,
            self.ctx.video,
            "GENERATING_CLIPS",
        )

        for index, clip_data in enumerate(
            self.ctx.suggested_clips,
            start=1,
        ):
            self.stop_if_paused()

            if recovery.should_skip_clip(
                self.ctx,
                index,
            ):

                log(
                    "PIPELINE",
                    f"Clip {index} ignorado."
                )

                continue

            self.process_single_clip(
                index,
                clip_data,
            )
            self.stop_if_paused()

    def stop_if_paused(self):
        self.ctx.db.refresh(self.ctx.video)
        if self.ctx.video.status == "PAUSED":
            raise PipelinePaused()

    def process_single_clip(
        self,
        clip_index,
        clip_data,
    ):

        clip = stages.create_clip_record(
            self.ctx,
            clip_data,
        )

        clip_mp4 = (
            self.ctx.clips_folder
            /
            f"clip_{clip.id}.mp4"
        )

        clip_srt = (
            self.ctx.clips_folder
            /
            f"clip_{clip.id}.srt"
        )

        final_mp4 = (
            self.ctx.clips_folder
            /
            f"clip_{clip.id}_final.mp4"
        )

        reel_mp4 = (
            self.ctx.clips_folder
            /
            f"clip_{clip.id}_reel.mp4"
        )

        thumb = (
            self.ctx.clips_folder
            /
            f"thumb_{clip.id}.jpg"
        )

        retry(
            generate_clip,

            input_video=self.ctx.video.file_path,

            output_video=str(
                clip_mp4
            ),

            start_time=clip.start_time,

            end_time=clip.end_time,
            retries=2,
            delay=2,
            stage="FFMPEG",
        )

        segments = filter_segments_for_clip(

            self.ctx.transcript["segments"],

            clip.start_time,

            clip.end_time,
        )

        adjusted = adjust_segments(

            segments,

            clip.start_time,

            clip.end_time
            -
            clip.start_time,
        )

        retry(
            generate_srt,
            adjusted,
            str(clip_srt),
            retries=2,
            stage="SRT",
        )

        retry(
            adapt_to_reel,
            input_video=str(clip_mp4),
            output_video=str(reel_mp4),
            retries=2,
            stage="REEL",
        )

        retry(
            burn_subtitles,
            input_video=str(reel_mp4),
            input_srt=str(clip_srt),
            output_video=str(final_mp4),
            retries=2,
            stage="BURN_SUBTITLE",
        )
   
        midpoint = (
            clip.end_time
            -
            clip.start_time
        ) / 2

        retry(
            generate_thumbnail,

            input_video=str(
                final_mp4
            ),

            output_image=str(
                thumb
            ),

            timestamp=midpoint,
            retries=2,
            stage="THUMBNAIL",
        )

        clip.clip_path = str(
            final_mp4
        )

        clip.subtitle_path = str(
            clip_srt
        )

        clip.thumbnail_path = str(
            thumb
        )

        checkpoint.clip_completed(
            self.ctx.db,
            clip,
        )

        recovery.update_last_clip(
            self.ctx,
            clip_index,
        )

        publish_completed_clip(
            self.ctx.db,
            clip,
        )
