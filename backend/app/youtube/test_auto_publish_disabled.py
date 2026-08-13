import os
from types import SimpleNamespace

from app.youtube.integration import publish_completed_clip


os.environ["YOUTUBE_AUTO_PUBLISH"] = "false"


def main():
    clip = SimpleNamespace(
        id=0,
        status="COMPLETED",
        clip_path="x.mp4",
        subtitle_path="x.srt",
        thumbnail_path="x.jpg",
    )

    result = publish_completed_clip(None, clip)
    print(result)


if __name__ == "__main__":
    main()
