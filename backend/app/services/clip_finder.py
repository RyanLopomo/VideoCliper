import asyncio
import json
import math
import os
import re

from app.services.ollama_client import generate
from app.utils.pipeline_logger import log

MIN_DURATION = 15
MAX_DURATION = 180
PREFERRED_DURATION = 45
OLLAMA_TIMEOUT = 180
END_PUNCTUATION = (".", "!", "?", "...")
KEYWORDS = ("segredo", "erro", "dica", "importante", "resultado", "como", "por que", "melhor", "nunca")


def discovery_attempt_limit() -> int:
    try:
        return max(1, int(os.getenv("CLIP_FINDER_MAX_DISCOVERY_ATTEMPTS", "1")))
    except ValueError:
        return 1


def load_transcript(transcript_path: str) -> dict:
    with open(transcript_path, "r", encoding="utf-8") as f:
        return json.load(f)


def transcript_duration(transcript: dict) -> float:
    segments = transcript.get("segments", [])
    duration = float(transcript.get("duration") or 0)
    if duration > 0:
        return duration
    if not segments:
        return 0
    return max(float(segment.get("end", 0)) for segment in segments)


def target_clip_count(transcript: dict) -> int:
    duration = transcript_duration(transcript)
    if duration <= 0:
        return 0
    return max(1, int(math.floor((duration / 60) + 0.5)))


def target_clip_duration(value: int | None) -> int:
    if value is None:
        return 60
    return min(MAX_DURATION, max(MIN_DURATION, int(value)))


def build_prompt(transcript: dict, target_clips: int, target_duration: int) -> str:
    transcript_text = ""

    for segment in transcript.get("segments", []):
        transcript_text += (
            f"[{segment['start']:.2f} - {segment['end']:.2f}] "
            f"{segment['text']}\n"
        )

    return f"""
Voce e um editor profissional de videos.

Analise a transcricao abaixo.

O video tem aproximadamente {transcript_duration(transcript):.0f} segundos.
Tente encontrar ate {target_clips} clips relevantes, distribuidos ao longo de todo o video.
Use {target_clips} como quantidade alvo, nao como obrigacao.
Use {target_duration} segundos como duracao alvo aproximada de cada clip.
Procure o melhor momento de cada regiao temporal, sem criar clips artificiais.

Retorne SOMENTE JSON.

Nunca escreva explicacoes.
Nunca utilize markdown.
Nunca utilize ```json.
Nunca escreva comentarios.
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

- maximo {target_duration} segundos, com pequena tolerancia somente para completar contexto
- minimo 15 segundos
- nao sobrepor clips
- distribuir os clips por todas as regioes do video
- evitar clips quase identicos ou com a mesma frase
- priorizar frases completas, perguntas/respostas, historias, opinioes e informacoes relevantes
- nunca inventar tempos
- utilizar somente informacoes existentes
- responder apenas JSON

TRANSCRICAO:

{transcript_text}
"""


def text_for_clip(clip: dict, segments: list) -> str:
    start = clip["start_time"]
    end = clip["end_time"]
    return " ".join(
        str(s.get("text", "")).strip()
        for s in segments
        if float(s.get("end", 0)) >= start and float(s.get("start", 0)) <= end
    ).strip()


def words_for_text(text: str) -> set:
    return set(re.findall(r"\w+", text.lower()))


def window_index(start: float, duration: float, target_clips: int) -> int:
    if duration <= 0 or target_clips <= 0:
        return 0
    return min(target_clips - 1, int(start / max(duration / target_clips, 1)))


def candidate_from_segment(segment: dict, segments: list, video_duration: float, target_duration: int | None = None) -> dict | None:
    start = float(segment.get("start", 0))
    clip_target = target_clip_duration(target_duration)
    end_limit = min(start + clip_target, video_duration or start + clip_target)
    end = float(segment.get("end", start))

    for current in segments:
        current_start = float(current.get("start", 0))
        current_end = float(current.get("end", 0))
        if current_start < start:
            continue
        if current_end > end_limit:
            break
        end = current_end
        if end - start >= min(PREFERRED_DURATION, clip_target) and str(current.get("text", "")).strip().endswith(END_PUNCTUATION):
            break

    if end - start < MIN_DURATION:
        valid_ends = [
            float(current.get("end", 0))
            for current in segments
            if start + MIN_DURATION <= float(current.get("end", 0)) <= end_limit
        ]
        if valid_ends:
            end = min(valid_ends)

    if end - start < MIN_DURATION or end <= start:
        return None

    text = " ".join(
        str(current.get("text", "")).strip()
        for current in segments
        if float(current.get("end", 0)) >= start and float(current.get("start", 0)) <= end
    ).strip()

    return {
        "start_time": start,
        "end_time": end,
        "title": (text[:80] or "Corte sugerido"),
    }


def fallback_clips(transcript: dict, target_clips: int | None = None, used_clips: list | None = None, target_duration: int | None = None) -> list:
    segments = transcript.get("segments", [])
    video_duration = transcript_duration(transcript)
    target_clips = target_clips if target_clips is not None else target_clip_count(transcript)
    used_clips = used_clips or []
    clips = []

    if not segments or target_clips <= 0:
        return []

    window_seconds = max(video_duration / target_clips, 1)

    for index in range(target_clips):
        window_start = index * window_seconds
        window_end = min((index + 1) * window_seconds, video_duration)
        region = [
            segment
            for segment in segments
            if float(segment.get("end", 0)) >= window_start
            and float(segment.get("start", 0)) <= window_end
        ]
        candidates = [
            candidate
            for candidate in (candidate_from_segment(segment, segments, video_duration, target_duration) for segment in region)
            if candidate
        ]

        if not candidates:
            continue

        candidates = normalize_clips(candidates, transcript, target_clips=target_clips, target_duration=target_duration)
        candidates = deduplicate_clips(candidates + used_clips, segments, target_clips)
        candidates = [clip for clip in candidates if clip not in used_clips]

        if candidates:
            clips.append(candidates[0])
            used_clips.append(candidates[0])

    log("CLIP-FINDER", f"Fallback gerou {len(clips)} clips.")

    return clips


def clip_score(clip: dict, segments: list, target_duration: int | None = None) -> float:
    start = clip["start_time"]
    end = clip["end_time"]
    duration = max(end - start, 1)
    text = text_for_clip(clip, segments)
    words = re.findall(r"\w+", text.lower())
    density = min(len(words) / duration, 4)
    keyword_bonus = sum(1 for word in KEYWORDS if word in text.lower()) * 0.35
    natural_start = 1 if any(abs(float(s.get("start", 0)) - start) <= 0.6 for s in segments) else 0
    natural_end = 1 if text.endswith(END_PUNCTUATION) or any(abs(float(s.get("end", 0)) - end) <= 0.8 for s in segments) else 0
    preferred = target_clip_duration(target_duration)
    duration_fit = 1 - min(abs(duration - preferred) / preferred, 1)
    return round(density + keyword_bonus + natural_start + natural_end + duration_fit, 3)


def naturalize_clip(clip: dict, segments: list, target_duration: int | None = None) -> dict | None:
    start = float(clip["start_time"])
    end = float(clip["end_time"])
    nearby_start = [s for s in segments if abs(float(s.get("start", 0)) - start) <= 2.0]
    nearby_end = [s for s in segments if abs(float(s.get("end", 0)) - end) <= 3.0]

    if nearby_start:
        start = float(min(nearby_start, key=lambda s: abs(float(s.get("start", 0)) - start))["start"])
    if nearby_end:
        end = float(min(nearby_end, key=lambda s: abs(float(s.get("end", 0)) - end))["end"])

    max_duration = target_clip_duration(target_duration)
    if end - start > max_duration:
        end = start + max_duration
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
    text = text_for_clip({"start_time": start, "end_time": end}, segments)
    if text and title == "Corte sugerido":
        title = text[:80]

    return {"start_time": start, "end_time": end, "title": title[:100]}


def deduplicate_clips(clips: list, segments: list, target_clips: int | None = None) -> list:
    selected = []
    for clip in sorted(clips, key=lambda c: c.get("score", 0), reverse=True):
        duplicate = False
        clip_text = text_for_clip(clip, segments)
        clip_words = words_for_text(clip_text)
        for current in selected:
            shared = max(0, min(clip["end_time"], current["end_time"]) - max(clip["start_time"], current["start_time"]))
            shortest = min(clip["end_time"] - clip["start_time"], current["end_time"] - current["start_time"])
            if shortest and shared / shortest > 0.55:
                duplicate = True
                break
            current_words = words_for_text(text_for_clip(current, segments))
            union = clip_words | current_words
            if union and len(clip_words & current_words) / len(union) > 0.86:
                duplicate = True
                break
        if not duplicate:
            selected.append(clip)

    selected = sorted(selected, key=lambda c: c["start_time"])
    if target_clips is not None:
        return selected[:target_clips]
    return selected


def clean_response(response: str) -> str:
    response = response.strip()

    if response.startswith("```"):
        response = re.sub(r"^```(?:json)?\s*", "", response)
        response = re.sub(r"\s*```$", "", response)

    match = re.search(r"\[[\s\S]*\]", response)

    if match:
        response = match.group(0)

    return response


def parse_response(response: str) -> list:
    response = clean_response(response)
    clips = json.loads(response)

    if isinstance(clips, dict):
        clips = clips.get("clips", [])

    if not isinstance(clips, list):
        raise ValueError("Resposta invalida do Ollama.")

    return clips


def normalize_clips(clips: list, transcript: dict | None = None, target_clips: int | None = None, target_duration: int | None = None) -> list:
    normalized = []
    segments = (transcript or {}).get("segments", [])
    video_duration = transcript_duration(transcript or {})
    max_duration = target_clip_duration(target_duration)

    for clip in clips:
        start = clip.get("start_time")
        if start is None:
            start = clip.get("start")
        if start is None:
            start = clip.get("inicio")

        end = clip.get("end_time")
        if end is None:
            end = clip.get("end")
        if end is None:
            end = clip.get("fim")

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

        if video_duration and start >= video_duration:
            continue

        if video_duration:
            end = min(end, video_duration)

        if end <= start:
            continue

        duration = end - start

        if duration < MIN_DURATION:
            continue

        if duration > max_duration + 5:
            continue

        title = str(title).strip()

        if not title:
            title = "Corte sugerido"

        item = {"start_time": start, "end_time": end, "title": title[:100]}
        if segments:
            item = naturalize_clip(item, segments, target_duration)
            if not item:
                continue
            item["score"] = clip_score(item, segments, target_duration)
            item["window"] = window_index(item["start_time"], video_duration, target_clips or target_clip_count(transcript or {}))
        normalized.append(item)

    normalized = deduplicate_clips(normalized, segments, target_clips) if segments else normalized
    normalized.sort(key=lambda x: x["start_time"])

    if target_clips is not None:
        return normalized[:target_clips]
    return normalized


def fill_missing_regions(normalized: list, transcript: dict, target_clips: int, target_duration: int | None = None) -> list:
    if len(normalized) >= target_clips:
        return normalized

    fallback = fallback_clips(
        transcript,
        target_clips=target_clips,
        used_clips=list(normalized),
        target_duration=target_duration,
    )
    merged = normalize_clips(normalized + fallback, transcript, target_clips=target_clips, target_duration=target_duration)
    return merged


async def find_clips(transcript_path: str, target_clips: int | None = None, target_duration: int | None = None):
    transcript = load_transcript(transcript_path)
    video_duration = transcript_duration(transcript)
    target_clips = target_clips or target_clip_count(transcript)
    target_duration = target_clip_duration(target_duration)

    log("CLIP-FINDER", f"video_duration={video_duration:.0f}")
    log("CLIP-FINDER", f"target_clips={target_clips}")
    log("CLIP-FINDER", f"target_duration={target_duration}")
    max_attempts = discovery_attempt_limit()
    log("CLIP-FINDER", f"attempt=1 max_attempts={max_attempts}")

    prompt = build_prompt(transcript, target_clips, target_duration)

    log("CLIP-FINDER", "Enviando prompt para o Ollama.")

    try:
        response = await asyncio.wait_for(
            generate(prompt),
            timeout=OLLAMA_TIMEOUT,
        )

        log("CLIP-FINDER", "Resposta recebida do Ollama.")
        log("CLIP-FINDER", response[:500])

        clips = parse_response(response)
        log("CLIP-FINDER", f"candidate_clips={len(clips)}")

        normalized = normalize_clips(clips, transcript, target_clips=target_clips, target_duration=target_duration)
        log("CLIP-FINDER", f"after_deduplication={len(normalized)}")

        normalized = fill_missing_regions(normalized, transcript, target_clips, target_duration)

        if not normalized:
            log("CLIP-FINDER", "Nenhum clip valido. Utilizando fallback.")
            normalized = fallback_clips(transcript, target_clips=target_clips, target_duration=target_duration)

        log("CLIP-FINDER", f"final_clips={len(normalized)}")
        if len(normalized) < target_clips:
            log(
                "CLIP-FINDER",
                f"target={target_clips} found={len(normalized)} attempt=1 max_attempts={max_attempts} result=STOPPED_TARGET_NOT_REACHED",
            )

        return normalized

    except asyncio.TimeoutError:
        log("CLIP-FINDER", "Timeout do Ollama. Utilizando fallback.")

        clips = fallback_clips(transcript, target_clips=target_clips, target_duration=target_duration)
        log("CLIP-FINDER", "candidate_clips=0")
        log("CLIP-FINDER", "after_deduplication=0")
        log("CLIP-FINDER", f"final_clips={len(clips)}")
        log(
            "CLIP-FINDER",
            f"target={target_clips} found={len(clips)} attempt=1 max_attempts={max_attempts} result=FALLBACK_STOP",
        )
        return clips

    except Exception as e:
        log("CLIP-FINDER", f"Erro: {e}")

        clips = fallback_clips(transcript, target_clips=target_clips, target_duration=target_duration)
        log("CLIP-FINDER", "candidate_clips=0")
        log("CLIP-FINDER", "after_deduplication=0")
        log("CLIP-FINDER", f"final_clips={len(clips)}")
        log(
            "CLIP-FINDER",
            f"target={target_clips} found={len(clips)} attempt=1 max_attempts={max_attempts} result=FALLBACK_STOP",
        )
        return clips
