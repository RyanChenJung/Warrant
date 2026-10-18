"""The table export the check battery reads (#30).

The vendored detectors were written for flat exports: they read CSV files, every column as text.
This module writes each table of a SQLite database to one CSV file and names the peers of a table.
It is the only glue between the SQLite clean copies and the detectors; any type handling belongs
here, never in detector logic.

- Names: files are `<table>.csv` and headers are the column names, exactly as SQLite declares
  them. The link detector matches declared foreign keys on exact names.
- Numbers: an integer is written with `str`; a float in positional notation, never scientific,
  as the shortest text that reads back as the same float (`1e-05` is written `0.00001`). A
  scientific form would give the detectors a spurious value format.
- NULL and the empty string are both written as an empty cell, and the detectors read both as
  NULL. `Export.empty_string_cells` counts the cells this merges.
- No documentation is exported: column meanings and the knowledge base never reach the detectors.
"""

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from warrant.battery.gloss.source import SourceTable
from warrant.data.release import ForeignKey
from warrant.data.sqlite import connect_read_only


@dataclass(frozen=True)
class Export:
    tables: list[SourceTable]
    empty_string_cells: int


def format_cell(value: Any) -> str:
    """One SQLite value as the text of a CSV cell."""
    if value is None:
        return ""
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    if isinstance(value, (str, int)):
        return str(value)
    raise TypeError(f"no CSV form for a {type(value).__name__} value")


def export_database(path: Path, out_dir: Path) -> Export:
    """Write every table of a SQLite database, opened read-only, to `<out_dir>/<table>.csv`, by table name."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tables, empty_strings = [], 0
    con = connect_read_only(path)
    try:
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
            cursor = con.execute(f'SELECT * FROM "{name}"')
            target = out_dir / f"{name}.csv"
            with open(target, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(column[0] for column in cursor.description)
                for row in cursor:
                    empty_strings += row.count("")
                    writer.writerow(format_cell(value) for value in row)
            tables.append(SourceTable(name=name, path=target, encoding="utf-8"))
    finally:
        con.close()
    return Export(tables, empty_strings)


def peers_of(foreign_keys: list[ForeignKey], table: str) -> dict[str, str]:
    """The tables linked to `table` by a declared foreign key, in either direction, as the detectors'
    peers (logical name to table name; here the two are the same)."""
    linked = {fk.ref_table for fk in foreign_keys if fk.table == table}
    linked |= {fk.table for fk in foreign_keys if fk.ref_table == table}
    return {name: name for name in sorted(linked - {table})}


def declared_keys(foreign_keys: list[ForeignKey]) -> list[tuple[str, str, str, str]]:
    """The declared foreign keys as the link detector takes them: (child table, child column, parent
    table, parent column)."""
    return [(fk.table, fk.column, fk.ref_table, fk.ref_column) for fk in foreign_keys]
