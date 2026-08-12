"""
Creates the database (if needed) and applies sql/schema.sql.

Lives in: python/init_db.py
Run from the python/ folder with: python init_db.py
"""

import os
from pathlib import Path

from sqlalchemy import text

from connection import create_database_if_not_exists, get_connection

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def run_schema() -> None:
    sql_text = SCHEMA_PATH.read_text()
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]

    with get_connection() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()

    print(f"✅ Applied {len(statements)} statement(s) from sql/schema.sql")


if __name__ == "__main__":
    create_database_if_not_exists()
    run_schema()