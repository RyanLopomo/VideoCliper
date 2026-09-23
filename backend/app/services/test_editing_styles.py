import asyncio

from app.services import editing_styles


def test_suggest_style_uses_local_heuristic_when_ai_disabled(monkeypatch):
    monkeypatch.setenv("STYLE_AI_ENABLED", "false")

    recommendation = asyncio.run(
        editing_styles.suggest_style(
            "Erro chocante",
            "Esse problema gerou uma crise importante.",
        )
    )

    assert recommendation["recommended_style"] == "DRAMATIC"
    assert "desativada" in recommendation["reason"]


def test_suggest_style_times_out_to_local_heuristic(monkeypatch):
    async def slow_generate(prompt):
        await asyncio.sleep(0.05)
        return "{}"

    monkeypatch.setattr(editing_styles, "style_ai_timeout", lambda: 0.01)
    monkeypatch.setattr(editing_styles, "generate", slow_generate)

    recommendation = asyncio.run(
        editing_styles.suggest_style(
            "Energia viral agora",
            "Uma dica rapida com segredo importante.",
        )
    )

    assert recommendation["recommended_style"] == "ENERGETIC"
    assert "tempo limite" in recommendation["reason"]


def test_suggest_style_limits_prompt_text(monkeypatch):
    captured = {}

    async def fake_generate(prompt):
        captured["prompt"] = prompt
        return '{"recommended_style":"PODCAST","confidence":0.8,"reason":"ok","editing_direction":["legivel"]}'

    monkeypatch.setenv("STYLE_AI_MAX_TEXT_CHARS", "200")
    monkeypatch.setattr(editing_styles, "generate", fake_generate)

    recommendation = asyncio.run(
        editing_styles.suggest_style(
            "Conversa",
            "x" * 1000,
        )
    )

    assert recommendation["recommended_style"] == "PODCAST"
    assert "x" * 300 not in captured["prompt"]
