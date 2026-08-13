from datetime import datetime, timedelta
from types import SimpleNamespace

from app.models.publication import Publication
from app.youtube.publication_queue import enqueue_publication


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class DB:
    def __init__(self):
        self.rows = []

    def query(self, model):
        return Query(self.rows)

    def add(self, item):
        item.id = len(self.rows) + 1
        self.rows.append(item)

    def commit(self):
        pass

    def refresh(self, item):
        pass


def main():
    db = DB()
    clip = SimpleNamespace(id=1)
    first = enqueue_publication(db, clip)
    second = enqueue_publication(db, clip)
    print(first.id == second.id)
    print(first.status)


if __name__ == "__main__":
    main()
