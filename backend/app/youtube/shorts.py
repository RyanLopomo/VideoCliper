import json
import subprocess
from pathlib import Path

from app.utils.pipeline_logger import log

MAX_SHORT_SECONDS = 180


def probe_video(path: str) -> tuple[int, int, float | None]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    duration = data.get("format", {}).get("duration")
    return int(stream["width"]), int(stream["height"]), float(duration) if duration else None


def is_short_format(width: int, height: int) -> bool:
    return height >= width


def youtube_upload_path_for_clip(clip) -> str:
    path = Path(clip.clip_path)
    width, height, duration = probe_video(str(path))
    clip_duration = duration or (float(clip.end_time) - float(clip.start_time))

    if clip_duration > MAX_SHORT_SECONDS:
        raise ValueError(f"Clip {clip.id} excede 180s e nao sera publicado como Short.")

    if is_short_format(width, height):
        log("YOUTUBE", f"Clip {clip.id} ja atende formato Shorts {width}x{height}.")
        return str(path)

    output = path.with_name(f"{path.stem}_youtube_short.mp4")
    if output.exists() and output.stat().st_size > 0:
        return str(output)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(path),
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:1[bg];"
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-c:a",
        "aac",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    log("YOUTUBE", f"Clip {clip.id} convertido para Shorts: {output}")
    return str(output)
