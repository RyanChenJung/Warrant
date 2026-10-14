"""The vendor's own schema documentation, read as a claim to be checked rather
than as truth. A dictionary may state that WOPRIORITY runs 0-100 with 0 lowest
while the data holds a small range that behaves in the opposite direction. Wrong
documentation is a finding, so this parser exists to be contradicted."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from warrant.battery.gloss.source import normalise

# "from 0-100", "Values from 0-100 are valid", "between 1 and 10"
_RANGE = re.compile(r"\bfrom\s+(\d+)\s*-\s*(\d+)|\bbetween\s+(\d+)\s+and\s+(\d+)",
                    re.IGNORECASE)

# "0 is the lowest priority and 100 is the highest"
_DIRECTION = re.compile(
    r"(\d+)\s+is\s+the\s+lowest.*?(\d+)\s+is\s+the\s+highest",
    re.IGNORECASE | re.DOTALL,
)

_COMPUTATION_MARKERS = (
    "calculated", "calculate", "sum of", "total of", "is derived",
    "divided by", "vs. planned", "added to",
)


@dataclass(frozen=True)
class DeclaredField:
    object_name: str
    attribute: str
    maxtype: str
    title: str
    remarks: str

    def documented_range(self) -> tuple[int, int] | None:
        m = _RANGE.search(self.remarks or "")
        if not m:
            return None
        lo, hi = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        return int(lo), int(hi)

    def documented_direction(self) -> str | None:
        """Which end of the scale the documentation calls "more"."""
        m = _DIRECTION.search(self.remarks or "")
        if not m:
            return None
        low_end, high_end = int(m.group(1)), int(m.group(2))
        return "higher_is_more" if high_end > low_end else "lower_is_more"

    def describes_a_computation(self) -> bool:
        text = (self.remarks or "").lower()
        return any(marker in text for marker in _COMPUTATION_MARKERS)


@dataclass(frozen=True)
class Dictionary:
    object_name: str
    fields: dict[str, DeclaredField]  # keyed by UPPERCASE attribute

    def get(self, attribute: str) -> DeclaredField | None:
        return self.fields.get(attribute.upper())

    def attributes(self) -> set[str]:
        return set(self.fields)

    def computed_fields(self) -> list[DeclaredField]:
        return [f for f in self.fields.values() if f.describes_a_computation()]


def load_dictionary(path: Path, object_name: str, cache_dir: Path) -> Dictionary:
    readable = normalise(path, cache_dir)
    conn = duckdb.connect()
    conn.read_csv(
        str(readable), all_varchar=True, sample_size=-1, header=True,
        ignore_errors=True,
    ).create_view("dictionary_source")
    rows = conn.execute(
        "SELECT ATTRIBUTENAME, MAXTYPE, TITLE, REMARKS FROM dictionary_source "
        "WHERE OBJECTNAME = ?",
        [object_name],
    ).fetchall()
    fields = {
        (attr or "").upper(): DeclaredField(
            object_name=object_name, attribute=(attr or "").upper(),
            maxtype=(maxtype or "").upper(), title=title or "", remarks=remarks or "",
        )
        for attr, maxtype, title, remarks in rows
        if attr
    }
    return Dictionary(object_name=object_name, fields=fields)
