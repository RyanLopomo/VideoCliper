from types import SimpleNamespace

from app.youtube.publication_urls import publication_url


def main():
    youtube = SimpleNamespace(
        platform="YOUTUBE",
        status="PUBLISHED",
        platform_post_id="abc123",
    )
    tiktok = SimpleNamespace(
        platform="TIKTOK",
        status="PUBLISHED",
        platform_post_id="abc123",
    )
    failed = SimpleNamespace(
        platform="YOUTUBE",
        status="FAILED",
        platform_post_id="abc123",
    )
    missing_id = SimpleNamespace(
        platform="YOUTUBE",
        status="PUBLISHED",
        platform_post_id=None,
    )

    print(publication_url(youtube) == "https://www.youtube.com/watch?v=abc123")
    print(publication_url(tiktok) is None)
    print(publication_url(failed) is None)
    print(publication_url(missing_id) is None)


if __name__ == "__main__":
    main()
