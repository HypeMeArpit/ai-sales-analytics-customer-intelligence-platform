"""
MySQL connection handling for the sales analytics project.

Lives in: python/connection.py
Other scripts in this same folder import it with: from connection import get_engine
"""

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# .env lives at the project root, one level up from python/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

_engine: Engine | None = None


def _build_connection_url() -> str:
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "sales_analytics")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")

    missing = [k for k, v in {"DB_NAME": name, "DB_USER": user}.items() if not v]
    if missing:
        raise RuntimeError(
            f"Missing required env vars: {', '.join(missing)}. "
            "Check your .env file in the project root."
        )

    return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{name}"


def get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_engine(_build_connection_url(), pool_pre_ping=True)
    return _engine


@contextmanager
def get_connection():
    """Context manager for a raw connection, e.g. for executing DDL."""
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()


def test_connection() -> bool:
    """Quick sanity check — run this after setting up .env."""
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Connected to MySQL successfully.")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def create_database_if_not_exists() -> None:
    """
    Connects WITHOUT selecting a database and issues CREATE DATABASE IF NOT
    EXISTS, so a fresh MySQL install works without manual setup.
    """
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "sales_analytics")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")

    server_url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}"
    server_engine = create_engine(server_url)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{name}`"))
        conn.commit()
    server_engine.dispose()
    print(f"✅ Database `{name}` is ready.")


if __name__ == "__main__":
    create_database_if_not_exists()
    test_connection()