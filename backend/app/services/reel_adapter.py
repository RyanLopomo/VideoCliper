import json
import subprocess
from pathlib import Path

from app.utils.pipeline_logger import log
from app.services.editing_styles import concrete_style, style_preset

FFMPEG_TIMEOUT = 300
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
LOGO_OPACITY = 0.40
MIN_LOGO_AREA_HEIGHT = 96


def probe_media(path: str) -> tuple[int, int, float | None]:
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


def even(value: float) -> int:
    rounded = int(round(value))
    return rounded if rounded % 2 == 0 else rounded - 1


def scaled_foreground_size(width: int, height: int) -> tuple[int, int]:
    source_ratio = width / height
    canvas_ratio = CANVAS_WIDTH / CANVAS_HEIGHT

    if source_ratio > canvas_ratio:
        return CANVAS_WIDTH, even(CANVAS_WIDTH / source_ratio)

    return even(CANVAS_HEIGHT * source_ratio), CANVAS_HEIGHT


def default_logo_path() -> Path | None:
    candidates = [
        Path("assets/axis-clips-logo-transparent.png"),
        Path("backend/assets/axis-clips-logo-transparent.png"),
        Path(__file__).resolve().parents[2] / "assets" / "axis-clips-logo-transparent.png",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def build_filter(width: int, height: int, has_logo: bool, style: str | None = None) -> tuple[str, bool]:
    fg_width, fg_height = scaled_foreground_size(width, height)
    top_extra = max(0, (CANVAS_HEIGHT - fg_height) // 2)
    can_place_logo = has_logo and top_extra >= MIN_LOGO_AREA_HEIGHT
    preset = style_preset(style)
    zoom = float(preset["zoom_level"])
    color_filter = f"eq=contrast={preset['contrast']}:saturation={preset['saturation']}"
    fg_scale = (
        f"scale=iw*{zoom}:ih*{zoom},"
        "crop=iw:ih:(in_w-out_w)/2:(in_h-out_h)/2,"
        if zoom > 1.0
        else ""
    )

    base_filter = (
        f"[0:v]scale={CANVAS_WIDTH}:{CANVAS_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_WIDTH}:{CANVAS_HEIGHT},boxblur=20:1,{color_filter}[bg];"
        f"[0:v]scale={CANVAS_WIDTH}:{CANVAS_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
        f"[fg]{fg_scale}{color_filter}[styledfg];"
        "[bg][styledfg]overlay=(W-w)/2:(H-h)/2"
    )

    if not can_place_logo:
        return f"{base_filter},setsar=1[out]", False

    logo_height = max(48, int(top_extra * 0.72))
    logo_top = max(12, int(top_extra * 0.08))
    logo_filter = (
        f";[1:v]format=rgba,colorchannelmixer=aa={LOGO_OPACITY},"
        f"scale={CANVAS_WIDTH // 3}:{logo_height}:force_original_aspect_ratio=decrease[logo];"
        f"[base][logo]overlay=(W-w)/2:{logo_top},setsar=1[out]"
    )
    return f"{base_filter}[base]{logo_filter}", True


def adapt_to_reel(
    input_video: str,
    output_video: str,
    logo_path: str | None = None,
    style: str | None = None,
) -> bool:
    output = Path(output_video)
    output.parent.mkdir(parents=True, exist_ok=True)

    width, height, _duration = probe_media(input_video)
    logo = Path(logo_path) if logo_path else default_logo_path()
    resolved_style = concrete_style(style)
    filter_complex, logo_applied = build_filter(width, height, bool(logo), resolved_style)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        input_video,
    ]

    if logo:
        command.extend(["-i", str(logo)])

    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    )

    log(
        "REEL",
        f"Adaptando para 9:16 source={width}x{height} style={resolved_style} logo={'aplicada' if logo_applied else 'omitida'}",
    )

    try:
        subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=FFMPEG_TIMEOUT,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        log("REEL", e.stderr)
        raise RuntimeError(f"Erro ao adaptar clip para Reel:\n{e.stderr}") from e

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Video Reel nao foi criado.")

    return True
