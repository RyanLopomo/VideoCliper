import asyncio
import json
import re

from app.services.ollama_client import generate
from app.utils.pipeline_logger import log

MAX_CLIPS = 5
MIN_DURATION = 15
MAX_DURATION = 60
OLLAMA_TIMEOUT = 180
END_PUNCTUATION = (".", "!", "?", "...")
KEYWORDS = ("segredo", "erro", "dica", "importante", "resultado", "como", "por que", "melhor", "nunca")


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


def clip_score(clip: dict, segments: list) -> float:
    start = clip["start_time"]
    end = clip["end_time"]
    duration = max(end - start, 1)
    text = " ".join(
        str(s.get("text", "")).strip()
        for s in segments
        if float(s.get("end", 0)) >= start and float(s.get("start", 0)) <= end
    ).strip()
    words = re.findall(r"\w+", text.lower())
    density = min(len(words) / duration, 4)
    keyword_bonus = sum(1 for word in KEYWORDS if word in text.lower()) * 0.35
    natural_start = 1 if any(abs(float(s.get("start", 0)) - start) <= 0.6 for s in segments) else 0
    natural_end = 1 if text.endswith(END_PUNCTUATION) or any(abs(float(s.get("end", 0)) - end) <= 0.8 for s in segments) else 0
    duration_fit = 1 - min(abs(duration - 35) / 35, 1)
    return round(density + keyword_bonus + natural_start + natural_end + duration_fit, 3)


def naturalize_clip(clip: dict, segments: list) -> dict | None:
    start = float(clip["start_time"])
    end = float(clip["end_time"])
    nearby_start = [s for s in segments if abs(float(s.get("start", 0)) - start) <= 2.0]
    nearby_end = [s for s in segments if abs(float(s.get("end", 0)) - end) <= 3.0]

    if nearby_start:
        start = float(min(nearby_start, key=lambda s: abs(float(s.get("start", 0)) - start))["start"])
    if nearby_end:
        end = float(min(nearby_end, key=lambda s: abs(float(s.get("end", 0)) - end))["end"])

    if end - start > MAX_DURATION:
        end = start + MAX_DURATION
        valid_ends = [float(s.get("end", 0)) for s in segments if start + MIN_DURATION <= float(s.get("end", 0)) <= end]
        if valid_ends:
            end = max(valid_ends)

    if end - start < MIN_DURATION:
        valid_ends = [float(s.get("end", 0)) for s in segments if float(s.get("end", 0)) >= start + MIN_DURATION]
        if valid_ends:
            end = min(valid_ends)

    if end - start < MIN_DURATION or end <= start:
        return None

    title = str(clip.get("title") or "Corte sugerido").strip()
    text = " ".join(
        str(s.get("text", "")).strip()
        for s in segments
        if float(s.get("end", 0)) >= start and float(s.get("start", 0)) <= end
    ).strip()
    if text and title == "Corte sugerido":
        title = text[:80]

    return {"start_time": start, "end_time": end, "title": title[:100]}


def remove_overlaps(clips: list) -> list:
    selected = []
    for clip in sorted(clips, key=lambda c: c.get("score", 0), reverse=True):
        overlap = False
        for current in selected:
            shared = max(0, min(clip["end_time"], current["end_time"]) - max(clip["start_time"], current["start_time"]))
            shortest = min(clip["end_time"] - clip["start_time"], current["end_time"] - current["start_time"])
            if shortest and shared / shortest > 0.55:
                overlap = True
                break
        if not overlap:
            selected.append(clip)
    return sorted(selected, key=lambda c: c["start_time"])[:MAX_CLIPS]


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


def normalize_clips(clips: list, transcript: dict | None = None) -> list:

    normalized = []
    segments = (transcript or {}).get("segments", [])

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

        item = {"start_time": start, "end_time": end, "title": title[:100]}
        if segments:
            item = naturalize_clip(item, segments)
            if not item:
                continue
            item["score"] = clip_score(item, segments)
        normalized.append(item)

    normalized = remove_overlaps(normalized) if segments else normalized
    normalized.sort(key=lambda x: x["start_time"])

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

        normalized = normalize_clips(clips, transcript)

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
