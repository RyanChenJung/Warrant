"""Injecting defects into a copy of a clean database.

The declaration here is the tracer bullet's minimum; #33 replaces it with the freeze format.
"""

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from warrant.store.claims import Slot


@dataclass(frozen=True)
class Defect:
    id: str
    database: str
    slot: Slot
    transformation: tuple[str, ...]
    reference_claim: str


def inject(clean: Path, dest: Path, defects: list[Defect]) -> Path:
    """Copy the clean database to dest and apply each defect's transformation, in the order given."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clean, dest)
    con = sqlite3.connect(dest)
    try:
        with con:
            for defect in defects:
                for statement in defect.transformation:
                    con.execute(statement)
    finally:
        con.close()
    return dest
