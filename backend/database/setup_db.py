# backend/database/db_setup.py

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from backend.config import settings


async def create_database_if_missing():
    """
    Connects to the default 'postgres' database to check if the target DB exists.
    If not, it creates it. An existing database is left untouched.
    """
    # 1. Parse the URL to get the target DB name
    target_db_name = conninfo_to_dict(settings.POSTGRES_DB_URL).get("dbname")

    # 2. Build a connection string for the 'postgres' system database on the same server
    system_db_url = make_conninfo(settings.POSTGRES_DB_URL, dbname="postgres", connect_timeout=10)

    print(f"DB Setup: Checking if database '{target_db_name}' exists...")

    try:
        async with await psycopg.AsyncConnection.connect(system_db_url, autocommit=True) as conn:
            cur = await conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (target_db_name,)
            )
            if await cur.fetchone():
                print(f"DB Setup: Database '{target_db_name}' already exists.")
                return

            print(f"DB Setup: Database '{target_db_name}' not found. Creating it...")
            # SQL injection safe method to create DB
            await conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db_name))
            )
            print(f"DB Setup: Database '{target_db_name}' created successfully.")

    except Exception as e:
        print(f"DB Setup: Critical Error checking or creating database: {e}")
        raise e
