import asyncio
import json
import os
import re
import time

from app.services.ollama_client import generate, generate_sync
from app.utils.pipeline_logger import log

STYLE_AUTO = "AUTO"
STYLE_CLEAN = "CLEAN"
STYLE_NAMES = {STYLE_AUTO, "DRAMATIC", "HAPPY", "ENERGETIC", "CINEMATIC", "PODCAST", STYLE_CLEAN}
STYLE_AI_TIMEOUT_SECONDS = 60
STYLE_AI_MAX_TEXT_CHARS = 2500
STYLE_AI_MAX_ATTEMPTS = 2

STYLE_PRESETS = {
    "DRAMATIC": {
        "name": "Dramatico",
        "caption_style": "strong",
        "caption_animation": "steady_pop",
        "caption_emphasis": "high",
        "zoom_level": 1.06,
        "zoom_speed": "slow",
        "transition_style": "soft",
        "color_profile": "deep",
        "contrast": 1.18,
        "saturation": 1.08,
        "cut_pacing": "moderate",
        "emphasis_strength": 0.82,
    },
    "HAPPY": {
        "name": "Alegre",
        "caption_style": "friendly",
        "caption_animation": "light_pop",
        "caption_emphasis": "medium",
        "zoom_level": 1.03,
        "zoom_speed": "gentle",
        "transition_style": "light",
        "color_profile": "vivid",
        "contrast": 1.06,
        "saturation": 1.22,
        "cut_pacing": "light",
        "emphasis_strength": 0.62,
    },
    "ENERGETIC": {
        "name": "Energetico",
        "caption_style": "dynamic",
        "caption_animation": "fast_pop",
        "caption_emphasis": "strong",
        "zoom_level": 1.08,
        "zoom_speed": "fast",
        "transition_style": "punchy",
        "color_profile": "high_energy",
        "contrast": 1.12,
        "saturation": 1.28,
        "cut_pacing": "fast",
        "emphasis_strength": 0.9,
    },
    "CINEMATIC": {
        "name": "Cinematico",
        "caption_style": "subtle",
        "caption_animation": "fade",
        "caption_emphasis": "low",
        "zoom_level": 1.04,
        "zoom_speed": "slow",
        "transition_style": "smooth",
        "color_profile": "cinematic",
        "contrast": 1.10,
        "saturation": 0.96,
        "cut_pacing": "slow",
        "emphasis_strength": 0.48,
    },
    "PODCAST": {
        "name": "Podcast",
        "caption_style": "readable",
        "caption_animation": "none",
        "caption_emphasis": "medium",
        "zoom_level": 1.02,
        "zoom_speed": "natural",
        "transition_style": "none",
        "color_profile": "balanced",
        "contrast": 1.04,
        "saturation": 1.02,
        "cut_pacing": "natural",
        "emphasis_strength": 0.55,
    },
    "CLEAN": {
        "name": "Clean",
        "caption_style": "clean",
        "caption_animation": "none",
        "caption_emphasis": "low",
        "zoom_level": 1.0,
        "zoom_speed": "none",
        "transition_style": "none",
        "color_profile": "neutral",
        "contrast": 1.0,
        "saturation": 1.0,
        "cut_pacing": "stable",
        "emphasis_strength": 0.35,
    },
}


def normalize_style(value: str | None) -> str:
    style = str(value or STYLE_AUTO).upper().strip()
    aliases = {"ALEGRE": "HAPPY", "DRAMATICO": "DRAMATIC", "ENERGICO": "ENERGETIC", "CINEMATICO": "CINEMATIC"}
    style = aliases.get(style, style)
    return style if style in STYLE_NAMES else STYLE_AUTO


def concrete_style(value: str | None) -> str:
    style = normalize_style(value)
    return STYLE_CLEAN if style == STYLE_AUTO else style


def style_preset(value: str | None) -> dict:
    return STYLE_PRESETS[concrete_style(value)]


def clean_json_response(response: str) -> str:
    response = response.strip()
    if response.startswith("```"):
        response = re.sub(r"^```(?:json)?\s*", "", response)
        response = re.sub(r"\s*```$", "", response)
    match = re.search(r"\{[\s\S]*\}", response)
    return match.group(0) if match else response


def fallback_recommendation(reason: str = "Nao foi possivel obter JSON valido da IA.") -> dict:
    return {
        "recommended_style": STYLE_AUTO,
        "confidence": 0.5,
        "reason": reason,
        "editing_direction": [
            "captions limpas",
            "enquadramento estavel",
            "contraste equilibrado",
        ],
    }


def style_ai_enabled() -> bool:
    value = os.getenv("STYLE_AI_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def style_ai_timeout() -> int:
    try:
        return max(1, int(os.getenv("STYLE_AI_TIMEOUT_SECONDS", str(STYLE_AI_TIMEOUT_SECONDS))))
    except ValueError:
        return STYLE_AI_TIMEOUT_SECONDS


def style_ai_max_text_chars() -> int:
    try:
        return max(200, int(os.getenv("STYLE_AI_MAX_TEXT_CHARS", str(STYLE_AI_MAX_TEXT_CHARS))))
    except ValueError:
        return STYLE_AI_MAX_TEXT_CHARS


def style_ai_max_attempts() -> int:
    try:
        return min(2, max(1, int(os.getenv("STYLE_AI_MAX_ATTEMPTS", str(STYLE_AI_MAX_ATTEMPTS)))))
    except ValueError:
        return STYLE_AI_MAX_ATTEMPTS


def heuristic_recommendation(title: str, text: str, reason: str | None = None) -> dict:
    content = f"{title} {text}".lower()
    keyword_styles = [
        (
            "ENERGETIC",
            ("rapido", "urgente", "explod", "viral", "energia", "acao", "agora", "nunca", "segredo"),
        ),
        (
            "DRAMATIC",
            ("erro", "medo", "crise", "perigo", "triste", "dor", "problema", "chocante", "drama"),
        ),
        (
            "HAPPY",
            ("feliz", "alegre", "risada", "incrivel", "bom", "otimo", "vitoria", "conquista"),
        ),
        (
            "CINEMATIC",
            ("historia", "jornada", "emocion", "memoria", "sonho", "futuro", "passado"),
        ),
        (
            "PODCAST",
            ("entrevista", "conversa", "pergunta", "resposta", "podcast", "opiniao", "eu acho"),
        ),
    ]
    scores = {
        style: sum(1 for keyword in keywords if keyword in content)
        for style, keywords in keyword_styles
    }
    selected_style = max(scores, key=scores.get)

    if scores[selected_style] <= 0:
        selected_style = STYLE_AUTO

    return {
        "recommended_style": selected_style,
        "confidence": 0.56 if selected_style != STYLE_AUTO else 0.5,
        "reason": reason or "Estilo escolhido por heuristica local para evitar demora na IA.",
        "editing_direction": [
            "captions limpas",
            "ritmo compativel com o conteudo",
            "contraste equilibrado",
        ],
    }


def transcript_text_for_clip(transcript: dict | None, start: float, end: float) -> str:
    if not transcript:
        return ""
    return " ".join(
        str(segment.get("text", "")).strip()
        for segment in transcript.get("segments", [])
        if float(segment.get("start", 0)) < end and float(segment.get("end", 0)) > start
    ).strip()


def _style_prompt(title: str, text: str) -> str:
    title = title[:300]
    text = text[:style_ai_max_text_chars()]
    return f"""
Voce e um diretor de edicao de videos curtos.

Escolha exatamente um estilo:
DRAMATIC, HAPPY, ENERGETIC, CINEMATIC, PODCAST, CLEAN.

Responda SOMENTE JSON.
Nunca use markdown.

Formato:
{{
  "recommended_style": "DRAMATIC",
  "confidence": 0.91,
  "reason": "",
  "editing_direction": ["", "", ""]
}}

Titulo do clip:
{title}

Transcricao do clip:
{text}
"""


def _parse_style_response(response: str) -> dict:
    parsed = json.loads(clean_json_response(response))
    style = concrete_style(parsed.get("recommended_style"))
    confidence = float(parsed.get("confidence", 0.5))
    direction = parsed.get("editing_direction", [])
    if not isinstance(direction, list):
        direction = [str(direction)]
    return {
        "recommended_style": style,
        "confidence": max(0, min(confidence, 1)),
        "reason": str(parsed.get("reason") or "Estilo escolhido com base no conteudo do clip."),
        "editing_direction": [str(item) for item in direction[:5]],
    }


def _fallback_with_log(clip_id, reason: str, started: float, title: str, text: str) -> dict:
    duration_ms = int((time.monotonic() - started) * 1000)
    log("EDITING_STYLE", f"clip={clip_id or '-'} status=FALLBACK reason={reason} style=AUTO duration_ms={duration_ms}")
    return fallback_recommendation(reason)


def suggest_style_sync(title: str, text: str, clip_id: int | None = None) -> dict:
    started = time.monotonic()
    log("EDITING_STYLE", f"clip={clip_id or '-'} status=START")

    if not style_ai_enabled():
        return _fallback_with_log(
            clip_id,
            "DISABLED",
            started,
            title,
            text,
        )

    prompt = _style_prompt(title, text)
    timeout = style_ai_timeout()
    last_reason = "UNKNOWN"

    for attempt in range(1, style_ai_max_attempts() + 1):
        try:
            response = generate_sync(prompt, request_timeout=timeout)
            recommendation = _parse_style_response(response)
            duration_ms = int((time.monotonic() - started) * 1000)
            log(
                "EDITING_STYLE",
                f"clip={clip_id or '-'} status=SUCCESS style={recommendation['recommended_style']} attempt={attempt} duration_ms={duration_ms}",
            )
            return recommendation
        except TimeoutError:
            last_reason = "TIMEOUT"
            log("EDITING_STYLE", f"clip={clip_id or '-'} status=TIMEOUT timeout={timeout} attempt={attempt}")
        except ConnectionError:
            last_reason = "CONNECTION_ERROR"
            log("EDITING_STYLE", f"clip={clip_id or '-'} status=ERROR reason=CONNECTION_ERROR attempt={attempt}")
        except json.JSONDecodeError:
            last_reason = "INVALID_JSON"
            log("EDITING_STYLE", f"clip={clip_id or '-'} status=ERROR reason=INVALID_JSON attempt={attempt}")
        except Exception as exc:
            last_reason = type(exc).__name__.upper()
            log("EDITING_STYLE", f"clip={clip_id or '-'} status=ERROR reason={last_reason} attempt={attempt}")

    return _fallback_with_log(clip_id, last_reason, started, title, text)


def suggest_style_for_clip_sync(clip, text: str) -> dict:
    cached_style = normalize_style(getattr(clip, "ai_style_recommendation", None))
    cached_confidence = getattr(clip, "ai_style_confidence", None)
    if cached_style not in {STYLE_AUTO, ""} and cached_confidence is not None:
        log(
            "EDITING_STYLE",
            f"clip={getattr(clip, 'id', '-')} status=CACHE style={cached_style}",
        )
        return {
            "recommended_style": cached_style,
            "confidence": float(cached_confidence),
            "reason": str(getattr(clip, "ai_style_reason", None) or "Recomendacao reutilizada do cache."),
            "editing_direction": [],
        }

    return suggest_style_sync(
        getattr(clip, "title", ""),
        text,
        clip_id=getattr(clip, "id", None),
    )


async def suggest_style(title: str, text: str) -> dict:
    if not style_ai_enabled():
        return heuristic_recommendation(
            title,
            text,
            "IA de estilo desativada; usando heuristica local.",
        )

    title = title[:300]
    text = text[:style_ai_max_text_chars()]
    prompt = f"""
Voce e um diretor de edicao de videos curtos.

Escolha exatamente um estilo:
DRAMATIC, HAPPY, ENERGETIC, CINEMATIC, PODCAST, CLEAN.

Responda SOMENTE JSON.
Nunca use markdown.

Formato:
{{
  "recommended_style": "DRAMATIC",
  "confidence": 0.91,
  "reason": "",
  "editing_direction": ["", "", ""]
}}

Titulo do clip:
{title}

Transcricao do clip:
{text}
"""
    try:
        timeout = style_ai_timeout()
        response = await asyncio.wait_for(generate(prompt), timeout=timeout)
        parsed = json.loads(clean_json_response(response))
        style = concrete_style(parsed.get("recommended_style"))
        confidence = float(parsed.get("confidence", 0.5))
        direction = parsed.get("editing_direction", [])
        if not isinstance(direction, list):
            direction = [str(direction)]
        return {
            "recommended_style": style,
            "confidence": max(0, min(confidence, 1)),
            "reason": str(parsed.get("reason") or "Estilo escolhido com base no conteudo do clip."),
            "editing_direction": [str(item) for item in direction[:5]],
        }
    except asyncio.TimeoutError:
        log("STYLE-AI", f"Timeout depois de {style_ai_timeout()}s. Usando heuristica local.")
        return heuristic_recommendation(
            title,
            text,
            "IA de estilo excedeu o tempo limite; usando heuristica local.",
        )
    except Exception as exc:
        log("STYLE-AI", f"Fallback local: {exc}")
        return heuristic_recommendation(title, text)
