import json
import math
import re

from app.services.ollama_client import generate

MIN_CLIP_DURATION_SECONDS = 15
MAX_SHORTS_DURATION_SECONDS = 180
DEFAULT_TARGET_DURATION_SECONDS = 60


def default_clip_count(duration_seconds: float | None) -> int:
    if not duration_seconds or duration_seconds <= 0:
        return 1
    return max(1, int(math.floor((duration_seconds / 60) + 0.5)))


def normalize_clip_targets(
    duration_seconds: float | None,
    target_clip_count: int | None = None,
    target_clip_duration: int | None = None,
) -> tuple[int, int]:
    count = target_clip_count if target_clip_count is not None else default_clip_count(duration_seconds)
    clip_duration = target_clip_duration or DEFAULT_TARGET_DURATION_SECONDS

    if count < 1:
        raise ValueError("Quantidade de clips deve ser no minimo 1.")
    if clip_duration < MIN_CLIP_DURATION_SECONDS:
        raise ValueError("Duracao dos clips deve ser de pelo menos 15 segundos.")
    if clip_duration > MAX_SHORTS_DURATION_SECONDS:
        raise ValueError("Para YouTube Shorts, a duracao maxima e 180 segundos.")

    return int(count), int(clip_duration)


def clip_suggestion(duration_seconds: float | None) -> dict:
    count, clip_duration = normalize_clip_targets(duration_seconds)
    return {
        "recommended_count": count,
        "recommended_duration_seconds": clip_duration,
        "reason": "Sugestao inicial de aproximadamente 1 clip por minuto.",
        "confidence": 0.76,
    }


def clean_json_object(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Resposta da IA precisa ser um objeto JSON.")
    return data


async def suggest_clip_config_with_ai(duration_seconds: float, transcript_stats: dict | None = None) -> dict:
    stats = transcript_stats or {}
    prompt = f"""
Voce configura cortes para YouTube Shorts.

Analise somente os dados abaixo e sugira quantidade e duracao alvo.

Duracao do video: {duration_seconds:.0f} segundos
Segmentos de fala: {stats.get("segments", "desconhecido")}
Palavras estimadas: {stats.get("words", "desconhecido")}

Retorne SOMENTE JSON neste formato:
{{
  "recommended_count": 30,
  "recommended_duration_seconds": 60,
  "reason": "...",
  "confidence": 0.91
}}

Regras:
- recommended_count minimo 1
- recommended_duration_seconds entre 15 e 180
- nao use texto livre fora do JSON
- para videos curtos, nao exagere na quantidade
"""
    data = clean_json_object(await generate(prompt))
    count, duration = normalize_clip_targets(
        duration_seconds,
        int(data.get("recommended_count", 0)),
        int(data.get("recommended_duration_seconds", 0)),
    )
    confidence = float(data.get("confidence", 0.7))
    return {
        "recommended_count": count,
        "recommended_duration_seconds": duration,
        "reason": str(data.get("reason") or "Sugestao gerada pela IA.").strip()[:500],
        "confidence": max(0, min(confidence, 1)),
    }
