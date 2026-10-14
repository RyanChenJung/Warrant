"""Running the baseline battery on a database (#30).

The battery is the eight checks of the release's `run_all`, called directly in its order: GRAIN
first, which fixes the population the others measure against, then SCOPE, FIELD, VALUE, LINK, RULE,
LIMIT and the ordinal-direction probe. `run_all` itself is not called, because it builds the link
detector without the declared foreign keys (see gloss/VENDORING.md); with no declared keys
`run_checks` returns exactly what `run_all` does. The checks read the tables through the export of
`warrant.data.export` and get no documentation; their date is always an argument, never the clock.
"""

from pathlib import Path

import duckdb

from warrant.battery.gloss.detect import Context, build_context
from warrant.battery.gloss.detect.field import FieldDetector
from warrant.battery.gloss.detect.grain import GrainDetector, derive_grain_filter
from warrant.battery.gloss.detect.limit import LimitDetector
from warrant.battery.gloss.detect.link import LinkDetector
from warrant.battery.gloss.detect.rule import RuleDetector
from warrant.battery.gloss.detect.scope import ScopeDetector
from warrant.battery.gloss.detect.value import ValueDetector
from warrant.battery.gloss.model import Finding
from warrant.battery.gloss.probe import OrdinalDirectionProbe
from warrant.battery.gloss.source import open_workspace
from warrant.data.export import Export, declared_keys, export_database, peers_of
from warrant.data.release import Database, ForeignKey


def open_database(db: Database, work_dir: Path) -> tuple[duckdb.DuckDBPyConnection, Export]:
    """Export every table of the database into `work_dir` and load the export as the detectors read it."""
    export = export_database(db.path, Path(work_dir) / "csv")
    return open_workspace(export.tables, cache_dir=Path(work_dir) / "cache"), export


def run_checks(ctx: Context, declared_keys) -> list[Finding]:
    """`run_all` on a context, except that the link detector also pairs columns on the declared keys."""
    findings = list(GrainDetector().run(ctx))
    ctx.grain_filter = derive_grain_filter(ctx)
    for detector in (ScopeDetector(), FieldDetector(), ValueDetector(),
                     LinkDetector(declared_keys=declared_keys), RuleDetector(), LimitDetector(),
                     OrdinalDirectionProbe()):
        findings += detector.run(ctx)
    return findings


def run_detectors(
    conn: duckdb.DuckDBPyConnection, table: str, today: str, foreign_keys: list[ForeignKey]
) -> list[Finding]:
    """The battery's findings on one table, whose peers are its declared-foreign-key tables."""
    ctx = build_context(conn, table, today, dictionary=None, peers=peers_of(foreign_keys, table))
    return run_checks(ctx, declared_keys(foreign_keys))


def run_battery(db: Database, today: str, work_dir: Path) -> dict[str, list[Finding]]:
    """The findings on every table of a database, keyed by table name."""
    conn, export = open_database(db, work_dir)
    try:
        return {table.name: run_detectors(conn, table.name, today, db.foreign_keys) for table in export.tables}
    finally:
        conn.close()
