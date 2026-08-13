import asyncio
import json
import os
from pathlib import Path

from app.youtube.publisher import publish_clip


ROOT_DIR = Path(__file__).resolve().parents[3]
CLIPS_DIR = ROOT_DIR / "storage" / "project_4" / "clips"

VIDEO_PATH = str(CLIPS_DIR / "clip_2_final.mp4")
SRT_PATH = str(CLIPS_DIR / "clip_2.srt")
THUMBNAIL_PATH = str(CLIPS_DIR / "thumb_2.jpg")


async def main():
    if os.getenv("YOUTUBE_AUTO_PUBLISH", "false").lower() != "true":
        print("YOUTUBE_AUTO_PUBLISH=false")
        return

    result = await publish_clip(
        video_path=VIDEO_PATH,
        srt_path=SRT_PATH,
        thumbnail_path=THUMBNAIL_PATH,
        privacy_status=os.getenv("YOUTUBE_PRIVACY_STATUS", "public"),
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
