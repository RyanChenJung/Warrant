"""Injecting defects into a copy of a clean database.

A defect's freeze fields (#33) are optional here; `warrant.freeze.validate` requires them of a freeze.
"""

import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from warrant.defects.audit import Audit, audit, snapshot
from warrant.store.claims import ClaimKind, Slot


@dataclass(frozen=True)
class Defect:
    id: str
    database: str
    slot: Slot
    transformation: tuple[str, ...]
    reference_claim: str
    touches: dict[str, list[str]] | None = None
    thresholds: tuple[str, ...] = ()
    cut_tables: tuple[str, ...] | None = None
    relation: dict | None = None
    readings: tuple[dict, ...] = ()
    drift_reading: dict | None = None


def load_defect(d: dict) -> Defect:
    """A defect as read from YAML: a write-line configuration's or a freeze's."""
    return Defect(
        id=d["id"],
        database=d["database"],
        slot=Slot(ClaimKind(d["slot"]["claim_kind"]), d["slot"]["subject"]),
        transformation=tuple(d["transformation"]),
        reference_claim=d["reference_claim"],
        touches=d.get("touches"),
        thresholds=tuple(str(t) for t in d.get("thresholds", ())),
        cut_tables=tuple(d["cut_tables"]) if "cut_tables" in d else None,
        relation=d.get("relation"),
        readings=tuple(d.get("readings", ())),
        drift_reading=d.get("drift_reading"),
    )


def inject(clean: Path, dest: Path, defects: list[Defect]) -> list[Audit]:
    """Copy the clean database to dest and apply each defect's transformation, in the order given.

    Each defect's audit record (#35) is returned and written beside the copy, as `<name>.audit.json`.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clean, dest)
    con = sqlite3.connect(dest)
    audits = []
    try:
        with con:
            for defect in defects:
                before, changes = snapshot(con), con.total_changes
                for statement in defect.transformation:
                    con.execute(statement)
                audits.append(audit(con, defect, before, snapshot(con), con.total_changes - changes))
    finally:
        con.close()
    dest.with_suffix(".audit.json").write_text(json.dumps([asdict(a) for a in audits], indent=2) + "\n")
    return audits
