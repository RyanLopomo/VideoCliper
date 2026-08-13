import json
from pathlib import Path

from app.youtube.thumbnail import upload_thumbnail


ROOT_DIR = Path(__file__).resolve().parents[3]
THUMBNAIL_PATH = str(ROOT_DIR / "storage" / "project_4" / "clips" / "thumb_2.jpg")
VIDEO_ID = "spQuxWe1Z1Q"


def main():
    result = upload_thumbnail(VIDEO_ID, THUMBNAIL_PATH)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
