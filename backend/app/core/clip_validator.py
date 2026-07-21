from pathlib import Path
import subprocess

from app.utils.pipeline_logger import log


class ValidationError(Exception):
    pass


def _file_exists(path: str):

    if not Path(path).exists():
        raise ValidationError(f"Arquivo inexistente: {path}")


def _file_not_empty(path: str):

    if Path(path).stat().st_size == 0:
        raise ValidationError(f"Arquivo vazio: {path}")


def _video_is_valid(path: str):

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ValidationError(f"Vídeo inválido: {path}")


def validate_clip(
    video_path: str,
    subtitle_path: str,
    thumbnail_path: str,
):

    log("VALIDATOR", "Validando arquivos")

    for file in (
        video_path,
        subtitle_path,
        thumbnail_path,
    ):

        _file_exists(file)
        _file_not_empty(file)

    _video_is_valid(video_path)

    log("VALIDATOR", "Clip validado")