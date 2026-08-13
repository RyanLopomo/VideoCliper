import asyncio
import json
from pathlib import Path

from app.youtube.metadata import generate_metadata


ROOT_DIR = Path(__file__).resolve().parents[3]
SRT_PATH = str(ROOT_DIR / "storage" / "project_4" / "clips" / "clip_2.srt")


async def main():

    metadata = await generate_metadata(
        SRT_PATH
    )

    print()
    print("==============================")
    print("METADADOS GERADOS")
    print("==============================")

    print(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
