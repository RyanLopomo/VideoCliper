import subprocess
import time
from pathlib import Path

from app.utils.pipeline_logger import log

FFMPEG_TIMEOUT = 120


def generate_thumbnail(
    input_video: str,
    output_image: str,
    timestamp: float,
) -> bool:

    if timestamp < 0:
        raise ValueError("Timestamp inválido.")

    output = Path(output_image)

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
        str(timestamp),

        "-i",
        input_video,

        "-frames:v",
        "1",

        "-q:v",
        "2",

        str(output),
    ]

    log(
        "THUMB",
        f"Gerando thumbnail em {timestamp:.2f}s"
    )

    started = time.perf_counter()

    try:

        subprocess.run(
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
                "Thumbnail não foi criada."
            )

        if output.stat().st_size == 0:
            raise RuntimeError(
                "Thumbnail criada vazia."
            )

        log(
            "THUMB",
            f"Thumbnail criada em {elapsed:.2f}s"
        )

        return True

    except subprocess.TimeoutExpired:

        log(
            "THUMB",
            "Timeout durante geração da thumbnail."
        )

        raise

    except subprocess.CalledProcessError as e:

        log(
            "THUMB",
            e.stderr
        )

        raise RuntimeError(
            f"Erro do FFmpeg:\n{e.stderr}"
        ) from e

    except Exception as e:

        log(
            "THUMB",
            f"Erro inesperado: {e}"
        )

        raise