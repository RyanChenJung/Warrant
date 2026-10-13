"""Tools the harness binds for the agent, and the schemas it declares them with.

A request offers tools by name; `SCHEMAS` is how those names are described to the model. #39 adds
the record lookup and the escalation tool here.
"""

from pathlib import Path

from warrant.data.sqlite import query


class ReadOnlySQL:
    """Runs one SQL statement on the named SQLite file; one that does more than read raises
    sqlite3.DatabaseError before it runs."""

    name = "sql"

    def __init__(self, path: Path):
        self._path = path

    def __call__(self, sql: str) -> list[tuple]:
        return query(self._path, sql)


SCHEMAS: dict[str, dict] = {
    ReadOnlySQL.name: {
        "name": ReadOnlySQL.name,
        "description": (
            "Run one read-only SQL statement on the database and return its rows. "
            "The connection is read-only: any statement that writes fails."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "One SQL statement."}},
            "required": ["sql"],
        },
    }
}
