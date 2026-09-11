def normalize_metadata(metadata: dict) -> dict:
    title = str(metadata.get("title", "")).strip()
    description = str(metadata.get("description", "")).strip()
    tags = metadata.get("tags", [])

    if not title:
        raise ValueError("Titulo ausente.")

    if not isinstance(tags, list):
        tags = []

    title = title[:100]
    category = str(metadata.get("category", metadata.get("categoryId", "22"))).strip() or "22"
    privacy_status = str(metadata.get("privacyStatus", metadata.get("privacy_status", "public"))).strip().lower()

    if privacy_status not in {"private", "unlisted", "public"}:
        privacy_status = "public"

    description_bytes = description.encode("utf-8")
    if len(description_bytes) > 5000:
        description = description_bytes[:5000].decode("utf-8", errors="ignore")

    normalized_tags = []
    seen = set()

    for tag in tags:
        tag = str(tag).strip()
        key = tag.casefold()

        if not tag or key in seen:
            continue

        normalized_tags.append(tag)
        seen.add(key)

        if len(normalized_tags) >= 15:
            break

    return {
        "title": title,
        "description": description,
        "tags": normalized_tags,
        "category": category,
        "privacyStatus": privacy_status,
    }
