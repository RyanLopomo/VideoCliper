from app.models.publication import Publication


def publication_url(publication: Publication) -> str | None:
    if publication.status != "PUBLISHED" or not publication.platform_post_id:
        return None

    if publication.platform == "YOUTUBE":
        return f"https://www.youtube.com/watch?v={publication.platform_post_id}"

    if publication.platform == "TIKTOK":
        return None

    return None
