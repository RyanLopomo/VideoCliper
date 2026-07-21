import subprocess
from pathlib import Path

from app.utils.pipeline_logger import log

FFMPEG_TIMEOUT = 300


def burn_subtitles(
    input_video: str,
    input_srt: str,
    output_video: str,
) -> bool:

    output = Path(output_video)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    log("SRT", "Aplicando legendas.")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",

        "-i",
        input_video,

        "-vf",
        f"subtitles={input_srt}",

        "-c:a",
        "copy",

        str(output),
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=FFMPEG_TIMEOUT,
            check=True,
        )

        if not output.exists():
            raise RuntimeError(
                "Vídeo legendado não foi criado."
            )

        if output.stat().st_size == 0:
            raise RuntimeError(
                "Vídeo legendado ficou vazio."
            )

        log("SRT", "Legendas aplicadas.")

        return True

    except subprocess.TimeoutExpired:

        log("SRT", "Timeout no FFmpeg.")

        raise

    except subprocess.CalledProcessError as e:

        log("SRT", e.stderr)

        raise RuntimeError(
            f"Erro ao aplicar legenda:\n{e.stderr}"
        ) from e


def filter_segments_for_clip(
    transcript_segments,
    clip_start,
    clip_end,
):

    return [
        segment
        for segment in transcript_segments
        if (
            segment["start"] < clip_end
            and
            segment["end"] > clip_start
        )
    ]


def adjust_segments(
    segments,
    clip_start,
    duration,
):

    adjusted = []

    for segment in segments:

        start = max(
            0,
            segment["start"] - clip_start,
        )

        end = min(
            duration,
            segment["end"] - clip_start,
        )

        if end <= start:
            continue

        adjusted.append(
            {
                "start": start,
                "end": end,
                "text": segment["text"],
            }
        )

    return adjusted


def seconds_to_srt_time(
    seconds: float,
) -> str:

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(
        (seconds - int(seconds)) * 1000
    )

    return (
        f"{hours:02}:"
        f"{minutes:02}:"
        f"{secs:02},"
        f"{milliseconds:03}"
    )


def generate_srt(
    segments,
    output_path,
):

    output = Path(output_path)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not segments:
        raise RuntimeError(
            "Nenhum segmento recebido para gerar SRT."
        )

    log(
        "SRT",
        f"Gerando {output.name}"
    )

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as file:

        for index, segment in enumerate(
            segments,
            start=1,
        ):

            file.write(
                f"{index}\n"
            )

            file.write(
                f"{seconds_to_srt_time(segment['start'])}"
            )

            file.write(
                " --> "
            )

            file.write(
                f"{seconds_to_srt_time(segment['end'])}\n"
            )

            file.write(
                f"{segment['text']}\n\n"
            )

    if not output.exists():
        raise RuntimeError(
            "Arquivo SRT não foi criado."
        )

    if output.stat().st_size == 0:
        raise RuntimeError(
            "Arquivo SRT vazio."
        )

    log("SRT", "Legenda criada.")

    return True