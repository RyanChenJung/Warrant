"""Read-only access to SQLite databases."""

import sqlite3
from pathlib import Path

# Opening a file read-only stops writes to it, but not ATTACH, VACUUM INTO or temporary tables,
# which create files or state elsewhere. Statements the model or the team wrote may only read.
_READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _reads_only(action: int, *_) -> int:
    return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY


def connect_read_only(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    con.set_authorizer(_reads_only)
    return con


def query(path: Path, sql: str) -> list[tuple]:
    """Run one statement that only reads; anything else raises sqlite3.DatabaseError before it runs."""
    con = connect_read_only(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def query_with_columns(path: Path, sql: str) -> tuple[tuple[str, ...], list[tuple]]:
    """Like `query`, with the names of the result's columns, which set answers are compared on."""
    con = connect_read_only(path)
    try:
        cursor = con.execute(sql)
        return tuple(column[0] for column in cursor.description or ()), cursor.fetchall()
    finally:
        con.close()


def schema(path: Path) -> str:
    """The CREATE statements of every table, as the agent sees the schema."""
    rows = query(path, "SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL ORDER BY name")
    return ";\n\n".join(sql for (sql,) in rows) + ";"
