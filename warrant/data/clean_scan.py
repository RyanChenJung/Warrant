"""Clean-database scan: the baseline battery on the clean copies, grouped by claim kind (#30, for #34).

    uv run python -m warrant.data.clean_scan --today 2026-10-12
    uv run python -m warrant.data.clean_scan --today 2026-10-12 \
        --defect-subjects column_formula:crypto.accountbalances.walletsum coverage:crypto.orders

For every database of the fetched release it runs the baseline battery (the eight checks of Gloss's
`run_all`, with the declared foreign keys given to the link detector) on the exported tables and
groups each finding by the claim kind it bears on, through the fixed mapping `CLAIM_KINDS`. It also
lists the numeric relations the identity search finds. It makes no model call and passes the
detectors no documentation. The findings go to a JSON file that is identical between two runs with
the same date; the runtime per database is recorded separately. Exported CSV files are written to a
temporary directory and deleted.

Two further lists serve #34. `grain_splits` names every table the GRAIN detector splits into
top-level and child rows, and whether a declared foreign key supports the split: on such a table
every other detector measures the top-level rows only. With `--defect-subjects`, the report lists
the findings on the tables and columns given; it states them and judges nothing.
"""

import argparse
import json
import re
import tempfile
import time
from pathlib import Path

import duckdb

from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.grain import derive_grain_filter
from warrant.battery.gloss.detect.rule import _MAX_NUMERIC_COLUMNS, numeric_columns
from warrant.battery.gloss.model import AssertionType, Finding, SqlEvidence
from warrant.battery.gloss.probe import _date_columns, _ordinal_levels
from warrant.battery.run import open_database, run_detectors
from warrant.data.export import peers_of
from warrant.data.release import ForeignKey, Release, load_database

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
    AssertionType.FIELD: "what a column's values are: with no documentation passed, non-breaking spaces, and the "
                         "direction of an ordinal scale from the ordinal-direction probe",
    AssertionType.VALUE: "what stored values stand for: code lists, value formats, variant spellings",
    AssertionType.LINK: "unmatched and never-referenced key values (what is omitted) and the cardinality of a join "
                        "(what a row counts as after it)",
    AssertionType.RULE: "an arithmetic relation between columns found by the identity search",
    AssertionType.LIMIT: "what is absent: empty and sparse columns",
}
NO_COLUMN = "(table)"

# The two statements the identity search writes (gloss/detect/rule.py, `_identity_finding`).
# The statement of a table split on a self-reference (gloss/detect/grain.py).
GRAIN_SPLIT = re.compile(r"^One row is not one top-level record\. (?P<column>\S+) points back at")
PROBE_STATEMENT = "Direction established by behavioural probe"
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


def grain_splits(table: str, findings: list[Finding], foreign_keys: list[ForeignKey]) -> list[dict]:
    """The split the GRAIN detector makes of one table on a column it reads as pointing back at the
    table's own key, if any. After it, every other detector measures the top-level rows only.

    `declared_self_reference` says whether a declared foreign key from that column to the same table
    supports the split.
    """
    out = []
    for finding in findings:
        match = GRAIN_SPLIT.match(finding.assertion.statement)
        if finding.assertion.type is AssertionType.GRAIN and match:
            top_level, rows = (int(v or 0) for v in finding.assertion.evidence[0].expected)
            out.append({
                "table": table,
                "column": match["column"],
                "rows": rows,
                "top_level_rows": top_level,
                "declared_self_reference": any(
                    fk.table == table == fk.ref_table and fk.column == match["column"] for fk in foreign_keys),
            })
    return out


def probe_reach(conn: duckdb.DuckDBPyConnection, table: str, today: str) -> list[dict]:
    """Whether the ordinal-direction probe has anything to read on one table (gloss/probe.py).

    The probe compares the delay between two date columns of a table across the levels of a column
    with 3 to 50 distinct numeric values, among the rows the GRAIN split keeps. A table with fewer
    than two date columns is out of its reach and is not listed.
    """
    ctx = build_context(conn, table, today)
    ctx.grain_filter = derive_grain_filter(ctx)
    dates = [column for column, _ in _date_columns(ctx)]
    if len(dates) < 2:
        return []
    return [{"table": table, "date_columns": dates,
             "level_columns": [c for c in ctx.columns if _ordinal_levels(ctx, c) is not None]}]


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
        findings, relations, splits, reach = [], [], [], []
        for table in export.tables:
            found = run_detectors(conn, table.name, today, db.foreign_keys)
            findings += [finding_record(table.name, f) for f in found]
            relations += identity_relations(conn, table.name, today, found)
            splits += grain_splits(table.name, found, db.foreign_keys)
            reach += probe_reach(conn, table.name, today)
    finally:
        conn.close()
    result = {
        "tables": {t.name: {"peers": list(peers_of(db.foreign_keys, t.name))} for t in export.tables},
        "empty_string_cells": export.empty_string_cells,
        "findings": findings,
        "by_claim_kind": group_by_claim_kind(findings),
        "identity_relations": relations,
        "grain_splits": splits,
        "probe_reach": reach,
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


def parse_defect_subject(text: str) -> dict:
    """`<claim kind>:<database>.<table>[.<column>]` as a defect subject."""
    kind, _, subject = text.partition(":")
    parts = subject.split(".")
    if kind not in KINDS or len(parts) not in (2, 3) or not all(parts):
        raise ValueError(f"expected <claim kind>:<database>.<table>[.<column>], got {text!r}")
    return {"claim_kind": kind, "database": parts[0], "table": parts[1], "column": parts[2] if len(parts) == 3 else None}


def defect_section(report: dict) -> list[str]:
    """The findings on each defect subject's table, as facts for #34."""
    label = lambda kind: kind.replace("_", " ")
    out = [
        "## Tables of the frozen defects",
        "",
        "For #34. The subjects are the tables and columns the freeze's defects are on, given to the command with "
        "`--defect-subjects`. For each, this section lists every finding "
        "of the clean scan on that table and its columns, by claim kind, and the LINK findings on other tables' "
        "columns that name the table. It states what the scan found; whether a finding is confounding is #34's "
        "call and is not judged here.",
        "",
    ]
    for subject in report["defect_subjects"]:
        database, table, column = report["databases"][subject["database"]], subject["table"], subject["column"]
        findings = database["findings"]
        name = f"{subject['database']}.{table}" + (f".{column}" if column else "")
        own = [f for f in findings if f["subject"].partition(".")[0] == table]
        on_column = [f for f in own if f["subject"] == f"{table}.{column}"]
        naming = [f for f in findings if f["assertion_type"] == "LINK" and f["subject"].partition(".")[0] != table
                  and re.search(rf"\b{re.escape(table)}\.", f["statement"])]
        split = [s for s in database["grain_splits"] if s["table"] == table]
        peer_splits = [s for s in database["grain_splits"] if s["table"] in database["tables"][table]["peers"]]
        out += [
            f"### {label(subject['claim_kind']).capitalize()} defect: `{name}`",
            "",
            f"- Peers of `{table}`: {', '.join(database['tables'][table]['peers']) or 'none'}.",
            f"- Findings on `{table}` and its columns: {len(own)}"
            + (f", of which {len(on_column)} on `{column}`" if column else "") + ".",
            "- GRAIN split: " + (
                "; ".join(f"**yes**, on `{s['column']}` ({s['top_level_rows']:,} of {s['rows']:,} rows kept"
                          + ("" if s["declared_self_reference"] else ", no declared key") + ")" for s in split)
                if split else f"none on `{table}`") + (
                "; its peers " + ", ".join(f"`{s['table']}`" for s in peer_splits) + " are split"
                if peer_splits else "; none on its peers") + ".",
            "",
        ]
        for kind in KINDS:
            listed = [f for f in own if kind in f["claim_kinds"]]
            if kind == "term_boundary":
                continue
            out.append(f"**{label(kind).capitalize()}** ({len(listed)})")
            out.append("")
            out += [f"- {f['assertion_type']} `{f['subject']}`: {cell(f['statement'])}" for f in listed] or ["- none"]
            out.append("")
        out.append(f"**LINK findings on other tables' columns that name `{table}`** ({len(naming)}; each counts under "
                   f"coverage and grain)")
        out.append("")
        out += [f"- `{f['subject']}` (scanning `{f['table']}`): {cell(f['statement'])}" for f in naming] or ["- none"]
        out.append("")
    return out


def cell(text: str) -> str:
    return " ".join(str(text).split())


def finding_keys(report: dict) -> dict[str, tuple]:
    """Every finding of a scan under a key that holds all of it, with the database it is in."""
    return {json.dumps([name, f], sort_keys=True): (name, f)
            for name, database in report["databases"].items() for f in database["findings"]}


def changes_section(report: dict, previous: dict) -> list[str]:
    """What differs from an earlier scan: counts per assertion type and the findings added or removed."""
    now, before = finding_keys(report), finding_keys(previous)
    added = [now[k] for k in now if k not in before]
    removed = [before[k] for k in before if k not in now]
    count = lambda findings, t: sum(f["assertion_type"] == t.value for _, f in findings)
    on_subjects = {(s["database"], s["table"]) for s in report.get("defect_subjects", [])}
    touches = lambda name, f: (name, f["subject"].partition(".")[0]) in on_subjects or (name, f["table"]) in on_subjects
    out = [
        "## Changes since the previous scan",
        "",
        "The previous scan (same date, same release) ran the seven detectors without the ordinal-direction probe. "
        "The battery now includes the probe, as Gloss's `run_all` does (decided on #28). A finding counts as "
        "unchanged only if its table, type, subject, statement and evidence are all identical.",
        "",
        "| Assertion type | Previous scan | This scan | Added | Removed |",
        "|---|---|---|---|---|",
    ]
    for t in AssertionType:
        out.append(f"| {t.value} | {count(before.values(), t)} | {count(now.values(), t)} | {count(added, t)} | "
                   f"{count(removed, t)} |")
    out += [f"| **Total** | {len(before)} | {len(now)} | {len(added)} | {len(removed)} |", ""]
    for title, findings in (("Added", added), ("Removed", removed)):
        out += [f"**{title} findings** ({len(findings)})", ""]
        out += [f"- {name}: {f['assertion_type']} `{f['subject']}`: {cell(f['statement'])}"
                for name, f in findings] or ["- none"]
        out.append("")
    if on_subjects:
        changed = [(name, f) for name, f in added + removed if touches(name, f)]
        out += [f"On the tables of the frozen defects, {len(changed)} findings were added or removed."
                + ("" if not changed else " They are: " + "; ".join(f"`{name}.{f['subject']}`" for name, f in changed)
                   + "."), ""]
    return out


def render_markdown(report: dict, runtimes: dict[str, float], previous: dict | None = None) -> str:
    """The human-readable scan report; with `previous`, an earlier scan's report, also what changed."""
    databases = report["databases"]
    measured = [k for k in KINDS if k != "term_boundary"]
    label = lambda kind: kind.replace("_", " ")
    source = (f"the pinned release (`{report['dataset']}` at revision `{report['revision']}`)"
              if "dataset" in report else "the given release directory")
    subjects = report.get("defect_subjects", [])
    arguments = "".join(
        " " + f"{s['claim_kind']}:{s['database']}.{s['table']}" + (f".{s['column']}" if s["column"] else "")
        for s in subjects)
    splits = [(name, s) for name, d in databases.items() for s in d["grain_splits"]]
    undeclared = [(name, s) for name, s in splits if not s["declared_self_reference"]]
    n_tables = sum(len(d["tables"]) for d in databases.values())
    out = [
        "# Clean-database scan with the baseline battery",
        "",
        f"Issue #30, for the freeze check in #34. Generated by `uv run python -m warrant.data.clean_scan --today "
        f"{report['today']}{' --defect-subjects' + arguments if subjects else ''}` from {source}: the eight checks of Gloss's `run_all` (the seven vendored detectors and "
        f"the ordinal-direction probe), called directly in its order on a CSV export of each clean copy, with DuckDB {report['duckdb_version']} and the detectors' date fixed to "
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
        "## Caveat: tables the GRAIN detector splits on a column that is not a declared key",
        "",
        f"The GRAIN detector splits a table into top-level and child rows when it reads a column as pointing back "
        f"at the table's own unique key: at least 95 percent of the column's populated values are among the key's "
        f"values, and some rows leave the column empty. Every "
        f"other detector then measures the top-level rows only. {len(splits)} of the {n_tables} tables are split, "
        f"and in {len(undeclared)} of them no declared foreign key from that column to the table supports the "
        f"split:",
        "",
    ]
    out += [f"- {name}.`{s['table']}`: split on `{s['column']}`, keeping {s['top_level_rows']:,} of {s['rows']:,} rows"
            for name, s in undeclared] or ["- none"]
    if undeclared:
        out += [
            "",
            "On these tables the column is populated with numbers that also occur as key values, and the rows the "
            "split keeps are those where it is empty. The SCOPE, VALUE, RULE and LIMIT findings there, including the "
            "identity relations marked below, describe only the rows kept, and the week-one check (#59), which "
            "applies no grain filter, does not report those relations.",
        ]
    affected = {(name, s["table"]) for name, s in undeclared}
    relations = [(name, r) for name, d in databases.items() for r in d["identity_relations"]]
    out += ["", "## Identity-search relations", ""]
    out += [f"- {name}.{describe_relation(r)}"
            + (" (only on the rows the GRAIN split keeps; see the caveat)" if (name, r["table"]) in affected else "")
            for name, r in relations] or ["The identity search finds none."]
    reach = [(name, r) for name, d in databases.items() for r in d["probe_reach"]]
    with_levels = [(name, r) for name, r in reach if r["level_columns"]]
    probed = sum(f["statement"].startswith(PROBE_STATEMENT) for d in databases.values() for f in d["findings"])
    out += [
        "",
        "## Reach of the ordinal-direction probe",
        "",
        f"The probe needs two date columns in the same table, and a column with 3 to 50 distinct numeric values "
        f"among the rows the GRAIN split keeps. {len(reach)} of the {n_tables} tables have two or more date "
        f"columns, and {len(with_levels)} of those also have such a column: "
        + ("; ".join(f"{name}.`{r['table']}` ({', '.join(r['level_columns'])})" for name, r in with_levels) or "none")
        + f". The probe reports {probed} findings"
        + (" on them." if probed else ", so it reports on none of them."),
    ]
    if previous is not None:
        out += ["", *changes_section(report, previous)]
    if subjects:
        out += ["", *defect_section(report)]
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
    parser.add_argument("--defect-subjects", nargs="+", default=[], type=parse_defect_subject,
                        metavar="KIND:DATABASE.TABLE[.COLUMN]",
                        help="list the findings on these defects' tables in the report (for #34)")
    parser.add_argument("--compare-to", type=Path, metavar="JSON",
                        help="an earlier scan's JSON file; the report then says what changed since")
    args = parser.parse_args(argv)
    if args.keep_export is not None and args.keep_export.resolve().is_relative_to(REPO):
        parser.error("exported CSV files are never kept inside the repository")

    release = Release.from_yaml(args.config)
    names = args.databases or list(release.databases)
    unknown = sorted(set(names) - set(release.databases))
    if unknown:
        parser.error(f"not in the configuration: {', '.join(unknown)}")
    previous = json.loads(args.compare_to.read_text()) if args.compare_to else None
    for subject in args.defect_subjects:
        if subject["database"] not in names:
            parser.error(f"defect subject in a database that is not scanned: {subject['database']}")
    with tempfile.TemporaryDirectory() as temporary:
        scanned, runtimes = scan_release(release.local_dir(), names, args.today, args.keep_export or Path(temporary))
    report = {
        "dataset": release.dataset,
        "revision": release.revision,
        "attribution": "Table and column names and values come from LiveSQLBench-Base-Lite (CC BY-SA 4.0).",
        **scanned,
        "defect_subjects": args.defect_subjects,
    }
    for subject in args.defect_subjects:
        if subject["table"] not in report["databases"][subject["database"]]["tables"]:
            parser.error(f"no table {subject['table']} in {subject['database']}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / JSON_NAME).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    (args.out_dir / RUNTIMES_NAME).write_text(
        json.dumps({"today": args.today, "seconds": runtimes}, indent=1) + "\n")
    (args.out_dir / REPORT_NAME).write_text(render_markdown(report, runtimes, previous))
    print(f"Scanned {len(names)} databases in {sum(runtimes.values()):.1f} s; wrote {REPORT_NAME}, {JSON_NAME} "
          f"and {RUNTIMES_NAME} to {args.out_dir}")


if __name__ == "__main__":
    main()
