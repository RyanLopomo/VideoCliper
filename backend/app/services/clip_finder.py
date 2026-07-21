import asyncio
import json
import re

from app.services.ollama_client import generate
from app.utils.pipeline_logger import log

MAX_CLIPS = 5
MIN_DURATION = 15
MAX_DURATION = 60
OLLAMA_TIMEOUT = 180


def load_transcript(transcript_path: str) -> dict:
    with open(transcript_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(transcript: dict) -> str:
    transcript_text = ""

    for segment in transcript.get("segments", []):
        transcript_text += (
            f"[{segment['start']:.2f} - {segment['end']:.2f}] "
            f"{segment['text']}\n"
        )

    return f"""
Você é um editor profissional de vídeos.

Analise a transcrição abaixo.

Retorne SOMENTE JSON.

Nunca escreva explicações.
Nunca utilize markdown.
Nunca utilize ```json.
Nunca escreva comentários.
Nunca escreva texto antes do JSON.
Nunca escreva texto depois do JSON.

Formato:

[
  {{
    "title":"",
    "start_time":0,
    "end_time":0
  }}
]

Regras:

- máximo 60 segundos
- mínimo 15 segundos
- não sobrepor clips
- nunca inventar tempos
- utilizar somente informações existentes
- responder apenas JSON

TRANSCRIÇÃO:

{transcript_text}
"""


def fallback_clips(transcript: dict) -> list:
    segments = transcript.get("segments", [])
    clips = []

    for segment in segments:

        start = float(segment["start"])
        end = min(
            float(segment["end"]) + 45,
            start + MAX_DURATION,
        )

        if end - start < MIN_DURATION:
            continue

        title = (
            segment["text"].strip()[:80]
            or "Corte sugerido"
        )

        clips.append(
            {
                "start_time": start,
                "end_time": end,
                "title": title,
            }
        )

        if len(clips) >= MAX_CLIPS:
            break

    log(
        "CLIP_FINDER",
        f"Fallback gerou {len(clips)} clips."
    )

    return clips


def clean_response(response: str) -> str:

    response = response.strip()

    if response.startswith("```"):
        response = re.sub(
            r"^```(?:json)?\s*",
            "",
            response,
        )

        response = re.sub(
            r"\s*```$",
            "",
            response,
        )

    match = re.search(
        r"\[[\s\S]*\]",
        response,
    )

    if match:
        response = match.group(0)

    return response


def parse_response(response: str) -> list:

    response = clean_response(response)

    clips = json.loads(response)

    if isinstance(clips, dict):
        clips = clips.get("clips", [])

    if not isinstance(clips, list):
        raise ValueError("Resposta inválida do Ollama.")

    return clips


def normalize_clips(clips: list) -> list:

    normalized = []

    for clip in clips:

        start = (
            clip.get("start_time")
            or clip.get("start")
            or clip.get("inicio")
        )

        end = (
            clip.get("end_time")
            or clip.get("end")
            or clip.get("fim")
        )

        title = (
            clip.get("title")
            or clip.get("text")
            or clip.get("titulo")
            or "Corte sugerido"
        )

        if start is None or end is None:
            continue

        start = float(start)
        end = float(end)

        if start < 0:
            continue

        if end <= start:
            continue

        duration = end - start

        if duration < MIN_DURATION:
            continue

        if duration > MAX_DURATION:
            continue

        title = str(title).strip()

        if not title:
            title = "Corte sugerido"

        normalized.append(
            {
                "start_time": start,
                "end_time": end,
                "title": title,
            }
        )

    normalized.sort(
        key=lambda x: x["start_time"]
    )

    return normalized[:MAX_CLIPS]


async def find_clips(transcript_path: str):

    transcript = load_transcript(transcript_path)

    prompt = build_prompt(transcript)

    log("CLIP_FINDER", "Enviando prompt para o Ollama.")

    try:

        response = await asyncio.wait_for(
            generate(prompt),
            timeout=OLLAMA_TIMEOUT,
        )

        log(
            "CLIP_FINDER",
            "Resposta recebida do Ollama."
        )

        log(
            "CLIP_FINDER",
            response[:500],
        )

        clips = parse_response(response)

        normalized = normalize_clips(clips)

        log(
            "CLIP_FINDER",
            f"{len(normalized)} clips válidos."
        )

        if not normalized:
            log(
                "CLIP_FINDER",
                "Nenhum clip válido. Utilizando fallback."
            )

            return fallback_clips(transcript)

        return normalized

    except asyncio.TimeoutError:

        log(
            "CLIP_FINDER",
            "Timeout do Ollama. Utilizando fallback."
        )

        return fallback_clips(transcript)

    except Exception as e:

        log(
            "CLIP_FINDER",
            f"Erro: {e}"
        )

        return fallback_clips(transcript)