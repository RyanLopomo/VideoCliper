import subprocess
import time
from pathlib import Path

from app.utils.pipeline_logger import log

FFMPEG_TIMEOUT = 300


def generate_clip(
    input_video: str,
    output_video: str,
    start_time: float,
    end_time: float,
) -> bool:

    duration = end_time - start_time

    if duration <= 0:
        raise ValueError("Duração do clip inválida.")

    output = Path(output_video)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",

        "-ss",
        str(start_time),

        "-i",
        input_video,

        "-t",
        str(duration),

        "-c:v",
        "libx264",
        "-preset",
        "fast",

        "-c:a",
        "aac",

        str(output),
    ]

    log(
        "FFMPEG",
        f"Iniciando corte ({start_time:.2f}s -> {end_time:.2f}s)"
    )

    started = time.perf_counter()

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=FFMPEG_TIMEOUT,
            check=True,
        )

        elapsed = time.perf_counter() - started

        if not output.exists():
            raise RuntimeError(
                "FFmpeg terminou mas o arquivo não foi criado."
            )

        if output.stat().st_size == 0:
            raise RuntimeError(
                "Arquivo de saída vazio."
            )

        log(
            "FFMPEG",
            f"Clip gerado em {elapsed:.2f}s"
        )

        return True

    except subprocess.TimeoutExpired:

        log(
            "FFMPEG",
            "Timeout durante geração do clip."
        )

        raise

    except subprocess.CalledProcessError as e:

        log(
            "FFMPEG",
            "Erro do FFmpeg:"
        )

        log(
            "FFMPEG",
            e.stderr
        )

        raise RuntimeError(
            f"FFmpeg retornou erro:\n{e.stderr}"
        ) from e

    except Exception as e:

        log(
            "FFMPEG",
            f"Erro inesperado: {e}"
        )

        raise