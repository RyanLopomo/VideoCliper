import json

from app.youtube.validator import normalize_metadata


METADATA = {
    "title": "Teste " * 30,
    "description": "Descricao de teste",
    "tags": ["axisclip", "AxisClip", "shorts", "", "youtube"],
}


def main():
    result = normalize_metadata(METADATA)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
