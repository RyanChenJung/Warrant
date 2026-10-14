"""The audit record of an injected defect (#35): what its transformation did, measured on the copy.

Every defect records the tables whose rows changed, with their row counts before and after, and the
number of rows its statements changed. A value-meaning defect also records its recoding, which must
be one-to-one; a column-formula defect records its declared relation and the rows it holds on.
"""

import sqlite3
from collections import Counter
from dataclasses import dataclass

from warrant.store.claims import ClaimKind

# The identity search's own tolerance (`warrant/battery/gloss/detect/rule.py`), so that the audit
# says a relation holds where the battery would find it.
RELATION_TOLERANCE = 0.005

# Table -> (column names, {rowid: row}).
Snapshot = dict[str, tuple[tuple[str, ...], dict[int, tuple]]]


@dataclass(frozen=True)
class Recoding:
    """One code a value-meaning defect replaced, and on how many rows."""

    table: str
    column: str
    old: object
    new: object
    rows: int


@dataclass(frozen=True)
class Audit:
    defect: str
    # Each table whose rows the transformation changed: its row count before and after.
    rows: dict[str, tuple[int, int]]
    # Rows the statements inserted, updated or deleted, as SQLite counts them.
    changed: int
    # A value-meaning defect's recoding, one entry per code it replaced.
    recoding: tuple[Recoding, ...] = ()
    # A column-formula defect's declared relation, and the rows it holds on out of the table's rows.
    relation: str | None = None
    holds: tuple[int, int] | None = None


def snapshot(con: sqlite3.Connection) -> Snapshot:
    tables = [
        name
        for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    found = {}
    for name in tables:
        cursor = con.execute(f'SELECT rowid, * FROM "{name}" ORDER BY rowid')
        found[name] = (tuple(column[0] for column in cursor.description[1:]), {row[0]: row[1:] for row in cursor})
    return found


def _recoding(defect: str, before: Snapshot, after: Snapshot) -> tuple[Recoding, ...]:
    """The codes a value-meaning transformation replaced; ValueError unless it recoded one-to-one,
    leaving every row and column in place."""
    refused = f"defect {defect!r}: a value-meaning defect must recode one-to-one, leaving every row in place"
    if before.keys() != after.keys():
        raise ValueError(refused)
    found = []
    for name, (columns, old_rows) in before.items():
        new_columns, new_rows = after[name]
        if new_columns != columns or new_rows.keys() != old_rows.keys():
            raise ValueError(refused)
        for i, column in enumerate(columns):
            pairs = Counter((old_rows[rowid][i], new_rows[rowid][i]) for rowid in old_rows)
            olds, news = Counter(old for old, _ in pairs), Counter(new for _, new in pairs)
            if any(n > 1 for n in olds.values()) or any(n > 1 for n in news.values()):
                raise ValueError(f"{refused} ({name}.{column})")
            found += [Recoding(name, column, old, new, n) for (old, new), n in pairs.items() if old != new]
    return tuple(found)


def _holds(con: sqlite3.Connection, relation: dict) -> tuple[int, int]:
    if relation["form"] != "sum":
        raise ValueError(f"only a sum relation is audited, not a {relation['form']}")
    total = " + ".join(f'"{column}"' for column in relation["operands"])
    holds, rows = con.execute(
        f'SELECT COALESCE(SUM(abs("{relation["target"]}" - ({total})) < ?), 0), COUNT(*) FROM "{relation["table"]}"',
        (RELATION_TOLERANCE,),
    ).fetchone()
    return holds, rows


def audit(con: sqlite3.Connection, defect, before: Snapshot, after: Snapshot, changed: int) -> Audit:
    """The audit record of `defect`, from snapshots taken just before and after its transformation."""
    rows = {
        name: (len(before[name][1]) if name in before else 0, len(after[name][1]) if name in after else 0)
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    }
    kind = defect.slot.claim_kind
    recoding = _recoding(defect.id, before, after) if kind == ClaimKind.VALUE_MEANING else ()
    relation = defect.relation if kind == ClaimKind.COLUMN_FORMULA else None
    return Audit(
        defect=defect.id,
        rows=rows,
        changed=changed,
        recoding=recoding,
        relation=None if relation is None else f"{relation['target']} = {' + '.join(relation['operands'])}",
        holds=None if relation is None else _holds(con, relation),
    )
