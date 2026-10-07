# backend/database/schema.py

from pathlib import Path

import psycopg

from backend.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def apply_schema() -> None:
    """
    Creates the ingestion tables and indexes if they are missing.
    Safe to call repeatedly: every statement in schema.sql is idempotent.
    """
    ddl = SCHEMA_PATH.read_text(encoding="utf-8").format(embedding_dim=settings.VECTOR_DIMENSION)

    with psycopg.connect(settings.POSTGRES_DB_URL, autocommit=True, connect_timeout=10) as conn:
        conn.execute(ddl)
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ).fetchall()

    print(f"DB Schema: applied. Tables: {', '.join(t[0] for t in tables)}")


if __name__ == "__main__":
    apply_schema()
