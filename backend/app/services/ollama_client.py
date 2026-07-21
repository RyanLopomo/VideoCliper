import httpx

from app.utils.pipeline_logger import log

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
OLLAMA_MODEL = "qwen3:8b"
REQUEST_TIMEOUT = 180


async def generate(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{prompt}\n\n/no_think",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 700,
        },
    }

    log("OLLAMA", f"Conectando ao modelo {OLLAMA_MODEL}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                OLLAMA_URL,
                json=payload,
            )

        log("OLLAMA", f"HTTP {response.status_code}")

        response.raise_for_status()

        data = response.json()

        if "response" not in data:
            raise RuntimeError("Campo 'response' não encontrado na resposta do Ollama.")

        text = data["response"].strip()

        if not text:
            raise RuntimeError("O Ollama retornou uma resposta vazia.")

        log("OLLAMA", "Resposta recebida com sucesso.")

        return text

    except httpx.TimeoutException as e:
        log("OLLAMA", "Timeout aguardando resposta.")
        raise RuntimeError("Timeout ao comunicar com o Ollama.") from e

    except httpx.ConnectError as e:
        log("OLLAMA", "Falha de conexão.")
        raise RuntimeError("Não foi possível conectar ao Ollama.") from e

    except httpx.HTTPStatusError as e:
        log("OLLAMA", f"Erro HTTP {e.response.status_code}")
        raise RuntimeError(
            f"Ollama respondeu HTTP {e.response.status_code}."
        ) from e

    except ValueError as e:
        log("OLLAMA", "Resposta JSON inválida.")
        raise RuntimeError("Resposta inválida do Ollama.") from e

    except Exception as e:
        log("OLLAMA", f"Erro inesperado: {e}")
        raise