import json
from pathlib import Path

from app.services.ollama_client import generate
from app.youtube.validator import normalize_metadata


def read_srt(srt_path: str) -> str:
    path = Path(srt_path)

    if not path.exists():
        raise FileNotFoundError(f"SRT nao encontrado: {path}")

    content = path.read_text(encoding="utf-8")
    lines = []

    for line in content.splitlines():
        line = line.strip()

        if not line or line.isdigit() or "-->" in line:
            continue

        lines.append(line)

    return "\n".join(lines)


def clean_json_response(response: str) -> str:
    response = response.strip()

    if response.startswith("```"):
        lines = response.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        response = "\n".join(lines).strip()

    start = response.find("{")
    end = response.rfind("}")

    if start >= 0 and end > start:
        response = response[start:end + 1]

    return response


async def generate_metadata(srt_path: str) -> dict:
    transcript = read_srt(srt_path)

    if not transcript.strip():
        raise ValueError("O SRT nao possui texto.")

    prompt = f"""
Voce e um especialista em criacao de conteudo para YouTube Shorts.

Analise o texto abaixo e crie metadados para o video.

Retorne SOMENTE JSON valido.

Formato obrigatorio:

{{
    "title": "",
    "description": "",
    "tags": []
}}

Regras:
- title deve ter no maximo 100 caracteres.
- description deve ter no maximo 5000 bytes.
- tags deve ser uma lista de strings.
- Gere no maximo 15 tags.
- Evite tags duplicadas.
- Nao invente informacoes ausentes no texto.
- Nao use markdown.
- Nao escreva nada fora do JSON.

TEXTO DO VIDEO:

{transcript}
"""

    response = clean_json_response(await generate(prompt))
    metadata = json.loads(response)

    return normalize_metadata(metadata)
