from app.youtube.config import tiktok_enabled, youtube_privacy_status
from app.youtube.metadata import generate_metadata
from app.youtube.status import get_video_status
from app.youtube.thumbnail import upload_thumbnail
from app.youtube.uploader import upload_video
from app.youtube.validator import normalize_metadata


class PlatformAdapter:
    platform = ""

    async def metadata(self, clip):
        return normalize_metadata(await generate_metadata(clip.subtitle_path))

    def upload(self, clip, metadata):
        raise NotImplementedError

    def processing_status(self, publication):
        return {"processing_status": "succeeded"}

    def thumbnail(self, publication, clip):
        return None


class YouTubeAdapter(PlatformAdapter):
    platform = "YOUTUBE"

    def upload(self, clip, metadata):
        return upload_video(
            video_path=clip.clip_path,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            privacy_status=metadata.get("privacyStatus") or youtube_privacy_status(),
        )

    def processing_status(self, publication):
        return get_video_status(publication.platform_post_id)

    def thumbnail(self, publication, clip):
        if getattr(publication, "thumbnail_uploaded_at", None):
            return None
        return upload_thumbnail(publication.platform_post_id, clip.thumbnail_path)


class TikTokAdapter(PlatformAdapter):
    platform = "TIKTOK"

    def upload(self, clip, metadata):
        if not tiktok_enabled():
            raise RuntimeError("TIKTOK_DISABLED")
        return f"tiktok_fake_{clip.id}"


def get_adapter(platform: str) -> PlatformAdapter:
    value = (platform or "YOUTUBE").upper()
    if value == "TIKTOK":
        return TikTokAdapter()
    return YouTubeAdapter()
