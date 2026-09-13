"""Seed the dev database with documents for read experiments.

Usage: uv run python experiments/seed.py --count 1000
Truncates `documents` first, so ids run 1..count (the load generator
picks random ids in that range).
"""

import argparse

from sqlalchemy import insert, text

from app.db.session import get_engine
from app.models.document import Document


def seed(count: int) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE documents RESTART IDENTITY"))
        chunk = 500
        created = 0
        while created < count:
            rows = [
                {
                    "title": f"Experiment document {created + i + 1}",
                    "source": "seed",
                    "content": "Lorem ipsum — experiment payload row.",
                }
                for i in range(min(chunk, count - created))
            ]
            conn.execute(insert(Document), rows)
            created += len(rows)
        total = conn.execute(text("SELECT count(*) FROM documents")).scalar_one()
    print(f"seeded {total} documents (ids 1..{count})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    seed(args.count)
