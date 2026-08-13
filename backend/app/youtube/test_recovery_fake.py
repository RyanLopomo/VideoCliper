from datetime import datetime, timedelta

from app.models.publication import Publication
from app.workers.recovery import recover_stuck_publications


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def all(self):
        return self.rows


class DB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return Query(self.rows)

    def commit(self):
        pass


def main():
    old = datetime.utcnow() - timedelta(hours=4)
    rows = [
        Publication(id=1, status="UPLOADING", attempts=0, updated_at=old),
        Publication(id=2, status="PROCESSING", attempts=0, updated_at=old),
    ]

    count = recover_stuck_publications(DB(rows))
    print(count)
    print(rows[0].status)
    print(rows[1].status)


if __name__ == "__main__":
    main()
