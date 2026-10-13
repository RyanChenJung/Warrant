"""Running the baseline battery on a database (#30).

The seven vendored detectors are called directly, in the order of the release's `run_all`: GRAIN
first, which fixes the population the others measure against, then SCOPE, FIELD, VALUE, LINK, RULE
and LIMIT. `run_all` itself is not used, because it also imports the probe that is not vendored
(see gloss/VENDORING.md). The detectors read the tables through the export of `warrant.data.export`
and get no documentation; their date is always an argument, never the clock.
"""

from pathlib import Path

import duckdb

from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.field import FieldDetector
from warrant.battery.gloss.detect.grain import GrainDetector, derive_grain_filter
from warrant.battery.gloss.detect.limit import LimitDetector
from warrant.battery.gloss.detect.link import LinkDetector
from warrant.battery.gloss.detect.rule import RuleDetector
from warrant.battery.gloss.detect.scope import ScopeDetector
from warrant.battery.gloss.detect.value import ValueDetector
from warrant.battery.gloss.model import Finding
from warrant.battery.gloss.source import open_workspace
from warrant.data.export import Export, declared_keys, export_database, peers_of
from warrant.data.release import Database, ForeignKey


def open_database(db: Database, work_dir: Path) -> tuple[duckdb.DuckDBPyConnection, Export]:
    """Export every table of the database into `work_dir` and load the export as the detectors read it."""
    export = export_database(db.path, Path(work_dir) / "csv")
    return open_workspace(export.tables, cache_dir=Path(work_dir) / "cache"), export


def run_detectors(
    conn: duckdb.DuckDBPyConnection, table: str, today: str, foreign_keys: list[ForeignKey]
) -> list[Finding]:
    """The seven detectors' findings on one table, whose peers are its declared-foreign-key tables."""
    ctx = build_context(conn, table, today, dictionary=None, peers=peers_of(foreign_keys, table))
    findings = list(GrainDetector().run(ctx))
    ctx.grain_filter = derive_grain_filter(ctx)
    for detector in (ScopeDetector(), FieldDetector(), ValueDetector(),
                     LinkDetector(declared_keys=declared_keys(foreign_keys)), RuleDetector(), LimitDetector()):
        findings += detector.run(ctx)
    return findings


def run_battery(db: Database, today: str, work_dir: Path) -> dict[str, list[Finding]]:
    """The findings on every table of a database, keyed by table name."""
    conn, export = open_database(db, work_dir)
    try:
        return {table.name: run_detectors(conn, table.name, today, db.foreign_keys) for table in export.tables}
    finally:
        conn.close()
