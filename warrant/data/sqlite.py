"""Read-only access to SQLite databases."""

import sqlite3
from pathlib import Path


def connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


def query(path: Path, sql: str) -> list[tuple]:
    """Run one statement on a database opened read-only; writes raise sqlite3.OperationalError."""
    con = connect_read_only(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def schema(path: Path) -> str:
    """The CREATE statements of every table, as the agent sees the schema."""
    rows = query(path, "SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL ORDER BY name")
    return ";\n\n".join(sql for (sql,) in rows) + ";"
