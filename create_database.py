import os

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from sqlalchemy.engine.url import make_url


def create_database_if_missing() -> None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in environment or .env.")

    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("DATABASE_URL must use PostgreSQL for this script.")

    db_name = parsed.database
    if not db_name:
        raise RuntimeError("DATABASE_URL must include a database name.")

    admin_db = "postgres"
    conn = psycopg2.connect(
        host=parsed.host or "localhost",
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        dbname=admin_db,
    )
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone() is not None

            if exists:
                print(f"Database '{db_name}' already exists.")
                return

            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"Database '{db_name}' created.")
    finally:
        conn.close()


if __name__ == "__main__":
    create_database_if_missing()
