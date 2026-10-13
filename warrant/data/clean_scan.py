"""Clean-database scan: the baseline battery on the clean copies, grouped by claim kind (#30, for #34).

    uv run python -m warrant.data.clean_scan --today 2026-10-12

For every database of the fetched release it runs the vendored detectors on the exported tables and
groups each finding by the claim kind it bears on, through the fixed mapping `CLAIM_KINDS`. It also
lists the numeric relations the identity search finds. It makes no model call and passes the
detectors no documentation. The findings go to a JSON file that is identical between two runs with
the same date; the runtime per database is recorded separately. Exported CSV files are written to a
temporary directory and deleted.
"""

import argparse
import json
import re
import tempfile
import time
from pathlib import Path

import duckdb

from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.rule import _MAX_NUMERIC_COLUMNS, numeric_columns
from warrant.battery.gloss.model import AssertionType, Finding, SqlEvidence
from warrant.battery.run import open_database, run_detectors
from warrant.data.export import peers_of
from warrant.data.release import Release, load_database

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO / "configs" / "livesqlbench-base-lite.yaml"
DEFAULT_OUT_DIR = REPO / "docs" / "research"
REPORT_NAME = "2026-10-13-clean-scan.md"
JSON_NAME = "clean-scan.json"
RUNTIMES_NAME = "clean-scan-runtimes.json"

KINDS = ("coverage", "grain", "value_meaning", "column_formula", "term_boundary")

# The claim kinds (CONTEXT.md) a finding of each assertion type bears on. A finding is listed under
# every kind of its type: for #34's check that no defect touches a table or column with a
# confounding finding, listing one finding too many is the safe error.
CLAIM_KINDS: dict[AssertionType, tuple[str, ...]] = {
    AssertionType.SCOPE: ("coverage",),
    AssertionType.GRAIN: ("grain",),
    AssertionType.FIELD: ("value_meaning",),
    AssertionType.VALUE: ("value_meaning",),
    AssertionType.LINK: ("coverage", "grain"),
    AssertionType.RULE: ("column_formula",),
    AssertionType.LIMIT: ("coverage",),
}
MAPPING_REASONS = {
    AssertionType.SCOPE: "which population the table covers: its date window, or a column dominated by one value",
    AssertionType.GRAIN: "what one row is: the unique key, a top-level and child split, columns that map one-to-one",
    AssertionType.FIELD: "what a column's values are: with no documentation passed, only non-breaking spaces",
    AssertionType.VALUE: "what stored values stand for: code lists, value formats, variant spellings",
    AssertionType.LINK: "unmatched and never-referenced key values (what is omitted) and the cardinality of a join "
                        "(what a row counts as after it)",
    AssertionType.RULE: "an arithmetic relation between columns found by the identity search",
    AssertionType.LIMIT: "what is absent: empty and sparse columns",
}
NO_COLUMN = "(table)"

# The two statements the identity search writes (gloss/detect/rule.py, `_identity_finding`).
IDENTITY = re.compile(r"^(?P<target>\S+) equals (?P<formula>.+?) for (all [\d,]+ rows|[\d.]+% of the [\d,]+ rows) where")


def finding_record(table: str, finding: Finding) -> dict:
    """One finding as the scan stores it. `table` is the table scanned; the subject names the table
    or column the finding is about, which for a never-referenced key is a peer's."""
    assertion = finding.assertion
    return {
        "table": table,
        "assertion_type": assertion.type.value,
        "claim_kinds": list(CLAIM_KINDS[assertion.type]),
        "subject": assertion.subject,
        "statement": assertion.statement,
        "evidence": [
            {"sql": e.sql, "expected": e.expected} if isinstance(e, SqlEvidence)
            else {"quote": e.quote, "source": e.source, "locator": e.locator}
            for e in assertion.evidence
        ],
    }


def identity_relations(conn: duckdb.DuckDBPyConnection, table: str, today: str, findings: list[Finding]) -> list[dict]:
    """The relations target = sum of components the identity search found on one table.

    `rows` are the rows where the target is non-zero and `holds` those where the relation holds.
    `pool` is the numeric columns the search reads (the first 12 of the table) and `positions` the
    1-based positions of the relation's columns among the table's numeric columns.
    """
    out = []
    numeric = None
    for finding in findings:
        assertion = finding.assertion
        if assertion.type is not AssertionType.RULE:
            continue
        match = IDENTITY.match(assertion.statement)
        if match is None:
            raise ValueError(f"not an identity-search statement: {assertion.statement!r}")
        if numeric is None:
            numeric = numeric_columns(build_context(conn, table, today))
        target, components = match["target"], match["formula"].split(" + ")
        rows, holds, _below = (int(v or 0) for v in assertion.evidence[0].expected)
        out.append({
            "table": table,
            "target": target,
            "components": components,
            "rows": rows,
            "holds": holds,
            "share": round(holds / rows, 4),
            "positions": {c: numeric.index(c) + 1 for c in (target, *components)},
            "pool": numeric[:_MAX_NUMERIC_COLUMNS],
        })
    return out


def group_by_claim_kind(findings: list[dict]) -> dict:
    """Indexes into `findings`, by claim kind, then the subject's table, then its column."""
    grouped: dict = {kind: {} for kind in KINDS}
    for i, finding in enumerate(findings):
        table, _, column = finding["subject"].partition(".")
        for kind in finding["claim_kinds"]:
            grouped[kind].setdefault(table, {}).setdefault(column or NO_COLUMN, []).append(i)
    return grouped


def scan_database(release_dir: Path, name: str, today: str, work_dir: Path) -> tuple[dict, float]:
    """The scan of one clean database, and the seconds it took (export, load and detectors)."""
    start = time.perf_counter()
    db = load_database(release_dir, name)
    conn, export = open_database(db, Path(work_dir) / name)
    try:
        findings, relations = [], []
        for table in export.tables:
            found = run_detectors(conn, table.name, today, db.foreign_keys)
            findings += [finding_record(table.name, f) for f in found]
            relations += identity_relations(conn, table.name, today, found)
    finally:
        conn.close()
    result = {
        "tables": {t.name: {"peers": list(peers_of(db.foreign_keys, t.name))} for t in export.tables},
        "empty_string_cells": export.empty_string_cells,
        "findings": findings,
        "by_claim_kind": group_by_claim_kind(findings),
        "identity_relations": relations,
    }
    return result, time.perf_counter() - start


def scan_release(release_dir: Path, names: list[str], today: str, work_dir: Path) -> tuple[dict, dict[str, float]]:
    """The scan of these databases of a fetched release, and each database's runtime in seconds."""
    databases, runtimes = {}, {}
    for name in names:
        databases[name], seconds = scan_database(release_dir, name, today, work_dir)
        runtimes[name] = round(seconds, 2)
    report = {
        "today": today,
        "duckdb_version": duckdb.__version__,
        "mapping": {t.value: list(kinds) for t, kinds in CLAIM_KINDS.items()},
        "databases": databases,
    }
    return report, runtimes


# Report ------------------------------------------------------------------------------------------


def kind_counts(database: dict) -> dict[str, int]:
    return {kind: sum(len(indexes) for columns in tables.values() for indexes in columns.values())
            for kind, tables in database["by_claim_kind"].items()}


def describe_relation(relation: dict) -> str:
    positions = relation["positions"]
    return (f"`{relation['table']}`: {relation['target']} = {' + '.join(relation['components'])} on "
            f"{relation['holds']:,} of {relation['rows']:,} rows with a non-zero target (numeric-column positions "
            f"{positions[relation['target']]} = {' + '.join(str(positions[c]) for c in relation['components'])})")


def render_markdown(report: dict, runtimes: dict[str, float]) -> str:
    """The human-readable scan report."""
    databases = report["databases"]
    measured = [k for k in KINDS if k != "term_boundary"]
    label = lambda kind: kind.replace("_", " ")
    source = (f"the pinned release (`{report['dataset']}` at revision `{report['revision']}`)"
              if "dataset" in report else "the given release directory")
    out = [
        "# Clean-database scan with the baseline battery",
        "",
        f"Issue #30, for the freeze check in #34. Generated by `uv run python -m warrant.data.clean_scan --today "
        f"{report['today']}` from {source}: the seven vendored Gloss detectors, called directly on a CSV export of "
        f"each clean copy, with DuckDB {report['duckdb_version']} and the detectors' date fixed to "
        f"{report['today']}. No model is called and no documentation is passed to the detectors. Every finding, "
        f"with its statement and evidence, is in [{JSON_NAME}]({JSON_NAME}), which is identical between two runs "
        f"with the same date. Table and column names and values quoted here come from LiveSQLBench-Base-Lite "
        f"(CC BY-SA 4.0).",
        "",
        "## How the scan reads the data",
        "",
        "- **Peers.** A table's peers are the tables linked to it by a declared foreign key, in either direction. "
        "The link detector also gets the declared keys and pairs them from child to parent only (#28).",
        "- **Export.** Table and column names are kept as declared; floats are written in positional notation.",
        "- **Empty strings.** NULL and the empty string are both exported as an empty cell, and the detectors read "
        "both as NULL. The summary counts the cells this merges per database.",
        "",
        "## Mapping from assertion type to claim kind",
        "",
        "A finding is listed under every claim kind of its assertion type.",
        "",
        "| Assertion type | Claim kind | What the detector reports |",
        "|---|---|---|",
    ]
    for assertion_type, kinds in CLAIM_KINDS.items():
        out.append(f"| {assertion_type.value} | {' and '.join(label(k) for k in kinds)} | "
                   f"{MAPPING_REASONS[assertion_type]} |")
    out += [
        "",
        "**No assertion type maps to term boundary.** No detector reports on what a business term includes, so the "
        "scan can list no finding of that kind. LINK is the only type that maps to two kinds.",
        "",
        "## Summary",
        "",
        "Findings are counted once per claim kind, so a LINK finding counts under coverage and under grain.",
        "",
        "| Database | Tables | Findings | " + " | ".join(label(k).capitalize() for k in measured)
        + " | Identity relations | Empty-string cells | Runtime (s) |",
        "|---|---|---|" + "---|" * len(measured) + "---|---|---|",
    ]
    for name, database in databases.items():
        counts = kind_counts(database)
        out.append(f"| {name} | {len(database['tables'])} | {len(database['findings'])} | "
                   + " | ".join(str(counts[k]) for k in measured)
                   + f" | {len(database['identity_relations'])} | {database['empty_string_cells']} | "
                     f"{runtimes[name]:.2f} |")
    out += [
        f"| **Total** | {sum(len(d['tables']) for d in databases.values())} | "
        f"{sum(len(d['findings']) for d in databases.values())} | "
        + " | ".join(str(sum(kind_counts(d)[k] for d in databases.values())) for k in measured)
        + f" | {sum(len(d['identity_relations']) for d in databases.values())} | "
          f"{sum(d['empty_string_cells'] for d in databases.values())} | {sum(runtimes.values()):.2f} |",
        "",
        "## Identity-search relations",
        "",
    ]
    relations = [(name, r) for name, d in databases.items() for r in d["identity_relations"]]
    out += [f"- {name}.{describe_relation(r)}" for name, r in relations] or ["The identity search finds none."]
    out += ["", "## Findings per table and claim kind", "",
            "Each cell counts the findings about that table or its columns; the columns are in the JSON.", ""]
    for name, database in databases.items():
        grouped = database["by_claim_kind"]
        out += [f"### {name}", "", "| Table | Peers | " + " | ".join(label(k).capitalize() for k in measured) + " |",
                "|---|---|" + "---|" * len(measured)]
        for table, info in database["tables"].items():
            cells = [str(sum(len(i) for i in grouped[k].get(table, {}).values())) for k in measured]
            out.append(f"| {table} | {', '.join(info['peers']) or '-'} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--today", required=True, help="the detectors' date, YYYY-MM-DD (the freeze's fixed date)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--databases", nargs="+", help="scan only these databases of the configuration")
    parser.add_argument("--keep-export", type=Path, help="keep the exported CSV files here (outside the repo)")
    args = parser.parse_args(argv)
    if args.keep_export is not None and args.keep_export.resolve().is_relative_to(REPO):
        parser.error("exported CSV files are never kept inside the repository")

    release = Release.from_yaml(args.config)
    names = args.databases or list(release.databases)
    unknown = sorted(set(names) - set(release.databases))
    if unknown:
        parser.error(f"not in the configuration: {', '.join(unknown)}")
    with tempfile.TemporaryDirectory() as temporary:
        scanned, runtimes = scan_release(release.local_dir(), names, args.today, args.keep_export or Path(temporary))
    report = {
        "dataset": release.dataset,
        "revision": release.revision,
        "attribution": "Table and column names and values come from LiveSQLBench-Base-Lite (CC BY-SA 4.0).",
        **scanned,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / JSON_NAME).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    (args.out_dir / RUNTIMES_NAME).write_text(
        json.dumps({"today": args.today, "seconds": runtimes}, indent=1) + "\n")
    (args.out_dir / REPORT_NAME).write_text(render_markdown(report, runtimes))
    print(f"Scanned {len(names)} databases in {sum(runtimes.values()):.1f} s; wrote {REPORT_NAME}, {JSON_NAME} "
          f"and {RUNTIMES_NAME} to {args.out_dir}")


if __name__ == "__main__":
    main()
