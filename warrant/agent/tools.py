"""Tools the harness binds for the agent."""

from pathlib import Path

from warrant.data.sqlite import query


class ReadOnlySQL:
    """Runs one SQL statement on the named SQLite file; any write raises sqlite3.OperationalError."""

    name = "sql"

    def __init__(self, path: Path):
        self._path = path

    def __call__(self, sql: str) -> list[tuple]:
        return query(self._path, sql)
