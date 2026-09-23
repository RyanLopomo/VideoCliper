import traceback

from app.pipeline.context import PipelineContext

from app.pipeline import stages
from app.pipeline import recovery
from app.pipeline import checkpoint

from app.services.video_cutter import generate_clip
from app.services.reel_adapter import adapt_to_reel
from app.services.editing_styles import concrete_style, normalize_style, suggest_style_for_clip_sync, transcript_text_for_clip
from app.services.subtitle_generator import (
    filter_segments_for_clip,
    adjust_segments,
    generate_srt,
    burn_subtitles,
)
from app.services.thumbnail import generate_thumbnail

from app.core.clip_validator import ValidationError, validate_clip
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

            self.apply_publication_step()

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

    def apply_publication_step(self):
        try:
            if self.ctx.video.publication_plan_enabled:
                result = apply_video_publication_plan(self.ctx.db, self.ctx.video)
                scheduled = result.get("created_publications", 0) if result else 0
                log(
                    "PUBLICATION-PLAN",
                    f"status=SUCCESS video={self.ctx.video.id} clips={len(self.ctx.video.clips)} scheduled={scheduled}",
                )
            else:
                for clip in self.ctx.video.clips:
                    if clip.status == "COMPLETED":
                        publish_completed_clip(self.ctx.db, clip)
            if self.ctx.video.error_type == "PUBLICATION_PLAN_ERROR":
                self.ctx.video.error_type = None
                self.ctx.video.error_message = None
                self.ctx.video.processing_message = "Processamento concluido."
                self.ctx.db.commit()
        except Exception:
            error = traceback.format_exc()
            self.ctx.video.status = "COMPLETED"
            self.ctx.video.processing_stage = "COMPLETED"
            self.ctx.video.processing_progress = 100
            self.ctx.video.error_type = "PUBLICATION_PLAN_ERROR"
            self.ctx.video.error_message = error
            self.ctx.video.processing_message = "Processamento concluido. Falha no agendamento das publicacoes."
            self.ctx.db.commit()
            notify(
                self.ctx.db,
                event_key=f"video:{self.ctx.video.id}:publication_plan_error",
                type="ERROR",
                title="Falha no agendamento",
                message="Os clips foram gerados, mas o planejamento de publicacao falhou.",
                video_id=self.ctx.video.id,
            )
            log(
                "PUBLICATION-PLAN",
                f"status=ERROR video={self.ctx.video.id} reason={error.splitlines()[-1] if error else 'unknown'}",
            )

    def process_clips(self):

        total_clips = len(self.ctx.suggested_clips) or self.ctx.video.target_clip_count or 0
        checkpoint.save_stage(
            self.ctx.db,
            self.ctx.video,
            "GENERATING_CLIPS",
            progress=round((self.ctx.video.last_completed_clip / max(total_clips, 1)) * 100) if total_clips else None,
            message=f"Gerando clips {self.ctx.video.last_completed_clip}/{total_clips}.",
        )
        recovery.reconcile_clip_checkpoints(self.ctx, total_clips)

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

        total = len(self.ctx.suggested_clips) or self.ctx.video.target_clip_count or clip_index
        checkpoint.touch_progress(
            self.ctx.db,
            self.ctx.video,
            progress=round((self.ctx.video.last_completed_clip / max(total, 1)) * 100),
            message=f"Gerando clip {clip_index}/{total}.",
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

        if clip.status == "COMPLETED":
            try:
                validate_clip(
                    video_path=clip.clip_path or str(final_mp4),
                    subtitle_path=clip.subtitle_path or str(clip_srt),
                    thumbnail_path=clip.thumbnail_path or str(thumb),
                )
                log(
                    "GENERATE_CLIP",
                    f"video_id={self.ctx.video.id} clip_index={clip_index} clip_id={clip.id} status=SKIP_EXISTING_VALID",
                )
                recovery.update_last_clip(
                    self.ctx,
                    clip_index,
                    total_clips=total,
                )
                self.apply_optional_style_recommendation(clip, clip_index, total)
                publish_completed_clip(
                    self.ctx.db,
                    clip,
                )
                return
            except ValidationError as exc:
                log(
                    "GENERATE_CLIP",
                    f"video_id={self.ctx.video.id} clip_index={clip_index} clip_id={clip.id} status=REGENERATE_INVALID_EXISTING reason={exc}",
                )

        log(
            "GENERATE_CLIP",
            f"video_id={self.ctx.video.id} clip_index={clip_index} clip_id={clip.id} status=START",
        )
        clip.status = "PROCESSING"
        clip.error_message = None
        self.ctx.video.last_completed_step = f"clip:{clip_index}:processing"
        self.ctx.db.commit()

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

        selected_style = self.render_style_for_clip(clip)

        clip.applied_preset = concrete_style(selected_style)
        self.ctx.db.commit()

        retry(
            adapt_to_reel,
            input_video=str(clip_mp4),
            output_video=str(reel_mp4),
            style=clip.applied_preset,
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

        validate_clip(
            video_path=str(final_mp4),
            subtitle_path=str(clip_srt),
            thumbnail_path=str(thumb),
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
            total_clips=total,
        )

        self.apply_optional_style_recommendation(clip, clip_index, total)

        publish_completed_clip(
            self.ctx.db,
            clip,
        )

        log(
            "GENERATE_CLIP",
            f"video_id={self.ctx.video.id} clip_index={clip_index} clip_id={clip.id} status=COMPLETED",
        )

    def render_style_for_clip(self, clip):
        selected_style = normalize_style(getattr(clip, "editing_style", None) or getattr(self.ctx.video, "editing_style", "AUTO"))
        cached_style = normalize_style(getattr(clip, "ai_style_recommendation", None))
        if selected_style == "AUTO" and cached_style != "AUTO":
            return cached_style
        return selected_style

    def apply_optional_style_recommendation(self, clip, clip_index: int, total_clips: int):
        selected_style = normalize_style(getattr(clip, "editing_style", None) or getattr(self.ctx.video, "editing_style", "AUTO"))
        if selected_style != "AUTO":
            return
        if getattr(clip, "ai_style_recommendation", None) and getattr(clip, "ai_style_confidence", None) is not None:
            return

        try:
            progress = round((clip_index / max(total_clips, 1)) * 100)
            recommendation = suggest_style_for_clip_sync(
                clip,
                transcript_text_for_clip(self.ctx.transcript, clip.start_time, clip.end_time),
            )
            clip.ai_style_recommendation = recommendation["recommended_style"]
            clip.ai_style_confidence = recommendation["confidence"]
            clip.ai_style_reason = recommendation["reason"]
            clip.editing_style = "AUTO"
            self.ctx.db.commit()
            log(
                "EDITING_STYLE",
                f"clip={clip.id} pipeline_progress={progress}% completed_clips={clip_index}/{total_clips}",
            )
        except Exception as exc:
            log(
                "EDITING_STYLE",
                f"clip={clip.id} status=FALLBACK reason={type(exc).__name__} pipeline_progress={round((clip_index / max(total_clips, 1)) * 100)}% completed_clips={clip_index}/{total_clips}",
            )
