from datetime import datetime
from types import SimpleNamespace

from app.api.publications import serialize_account


def main():
    account = SimpleNamespace(
        id=1,
        platform="YOUTUBE",
        account_name="Canal",
        platform_account_id="channel-1",
        enabled=True,
        is_default=True,
        credential_path="backend/app/youtube/token.json",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    data = serialize_account(account)
    print("credential_path" not in data)
    print("access_token" not in data)
    print("refresh_token" not in data)
    print(data["platform_account_id"] == "channel-1")


if __name__ == "__main__":
    main()
