"""Validate a freeze: `python -m warrant.freeze.validate --config <file>`.

A freeze is a YAML file with a `global` part and a list of `defects` (the write-line configuration
format of #27, extended). Validation reads only the file, so it needs neither the battery nor any
database. The one check that needs a schema, the position of a column-formula's columns among the
table's numeric columns, takes it as an argument and is reported as skipped when there is none.
Content hashes are not computed here (#36).

`validate` returns (errors, warnings): errors make a freeze invalid; warnings only flag.
"""

import argparse
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import yaml

from warrant.data.sqlite import connect_read_only
from warrant.store.claims import ClaimKind

# Schema of a database: {table: [(column, declared type), ...]} in table order.
Schema = dict[str, list[tuple[str, str]]]

GLOBAL_KEYS = (
    "battery", "fixed_date", "duckdb_version", "seeds", "drift_reading_rule", "outcome_rule",
    "per_kind_combination", "judge", "confidence_combination", "matched_asks", "numeric_tolerance",
    "refusal_check", "confirmatory_test",
)
CONFIRMATORY_KEYS = ("statistic", "pairing", "question_set", "error_coding", "failures")
PRIMARY_FAILURE_RULE = "pairs_where_both_rules_scored"
SCORED_EXCLUDES = ("failure_after_retries", "clarification_request")
SENSITIVITY = ("failures_as_wrong", "clarifications_as_wrong")

# The vendored identity search finds target = sum of two or three of a table's first 12 numeric columns.
MAX_NUMERIC_COLUMNS = 12
NUMERIC_TYPE = re.compile(r"INT|REAL|FLOA|DOUB|DEC|NUM")

SQL_KEYWORD = re.compile(
    r"\b(?:SELECT|FROM|WHERE|JOIN|GROUP BY|ORDER BY|HAVING|COUNT|SUM|AVG|DISTINCT|AND|OR|NOT|IN|LIKE|BETWEEN)\b"
)
COMPARISON = re.compile(r"<=|>=|<>|!=|=|<|>")
QUOTED = re.compile(r"'[^']*'|`[^`]*`|\"[^\"]*\"")
DIGITS = re.compile(r"\d[\d,.]*\d|\d")


def _blank(value) -> bool:
    return value is None or (isinstance(value, (str, list, dict)) and not (value.strip() if isinstance(value, str) else value))


def reference_claim_problems(claim, thresholds=()) -> list[str]:
    """Why a reference claim hands the agent more than a person knows (ADR 0003); empty when it does not.

    An uppercase SQL keyword token or a comparison symbol is rejected wherever it stands; a digit
    sequence is accepted inside quotes or backticks or when it is a declared threshold literal.
    """
    if _blank(claim) or not isinstance(claim, str):
        return ["it has no reference claim"]
    found = [f"SQL keyword {m.group()!r}" for m in SQL_KEYWORD.finditer(claim)]
    found += [f"comparison symbol {m.group()!r}" for m in COMPARISON.finditer(claim)]
    allowed = {str(t) for t in thresholds}
    unquoted = QUOTED.sub(" ", claim)
    found += [
        f"number {m.group()!r}, neither quoted nor a declared threshold literal"
        for m in DIGITS.finditer(unquoted)
        if m.group() not in allowed
    ]
    return found


def _readings(name: str, d: dict) -> list[str]:
    """Problems in the reading set's own fields; the drift reading is checked after them."""
    found = []
    readings = d.get("readings")
    if not isinstance(readings, list) or not readings:
        return [f"{name}: it has no reading set"]
    ids = [r.get("id") for r in readings]
    if len(set(ids)) != len(ids) or any(_blank(i) for i in ids):
        found.append(f"{name}: reading ids must be unique and non-empty")
    for r in readings:
        rid = f"{name}: reading {r.get('id')!r}"
        if _blank(r.get("statement")):
            found.append(f"{rid} has no statement")
        form = r.get("form")
        transformation = r.get("transformation")
        if "transformation" not in r or not isinstance(transformation, list):
            found.append(f"{rid} must write its transformation out as a list (`[]` for none)")
        if not isinstance(r.get("holds"), bool):
            found.append(f"{rid} must say whether the reference claim holds under it (holds: true or false)")
        if not isinstance(r.get("is_true"), bool):
            found.append(f"{rid} must say whether it is the true reading (is_true: true or false)")
        if form == "meaning_only":
            if transformation:
                found.append(f"{rid} is meaning-only, so its transformation must be empty")
            if r.get("kind") not in ("convention", "provenance"):
                found.append(f"{rid} is meaning-only, so its kind must be convention or provenance")
        elif form == "world_fixed":
            if "kind" in r:
                found.append(f"{rid} is world-fixed, so it declares no kind")
        else:
            found.append(f"{rid} has form {form!r}, not meaning_only or world_fixed")
    if sum(r.get("is_true") is True for r in readings) != 1:
        found.append(f"{name}: it must have exactly one true reading")
    return found


def _drift(name: str, d: dict) -> list[str]:
    readings = d.get("readings")
    if not isinstance(readings, list) or not readings:
        return []
    drift = d.get("drift_reading")
    if not isinstance(drift, dict) or _blank(drift.get("reading")):
        return [f"{name}: it has no drift reading"]
    by_id = {r.get("id"): r for r in readings}
    if drift["reading"] not in by_id:
        return [f"{name}: its drift reading {drift['reading']!r} is not in its reading set"]
    reading = by_id[drift["reading"]]
    found = []
    if reading.get("is_true") is True:
        return [f"{name}: its drift reading is the true reading"]
    if reading.get("holds") is True:
        found.append(f"{name}: the reference claim holds under the drift reading")
    # The drift-reading rule reads declarations only: the no-defect reading is the world-fixed reading
    # with an empty transformation or, with no world-fixed rival, the meaning-only reading marked no_defect.
    world = [r for r in readings if r.get("is_true") is not True and r.get("form") == "world_fixed"]
    if world:
        empty = [r for r in world if r.get("transformation") == []]
        if len(empty) != 1 or empty[0] is not reading:
            found.append(
                f"{name}: with world-fixed rivals the drift reading must be the one with an empty transformation"
            )
    else:
        marked = [r for r in readings if r.get("no_defect") is True]
        if len(marked) != 1 or marked[0] is not reading:
            found.append(
                f"{name}: exactly one meaning-only reading, the drift reading, must be marked no_defect: true"
            )
        if _blank(drift.get("reference_claim")):
            found.append(f"{name}: a meaning-only drift reading needs the reference claim a person would state under it")
    if "reference_claim" in drift:
        found += [f"{name}: drift reading's reference claim: {p}" for p in
                  reference_claim_problems(drift["reference_claim"], d.get("thresholds", ()))]
    return found


def _touches(name: str, d: dict) -> list[str]:
    touches = d.get("touches")
    if not isinstance(touches, dict) or not touches or not all(
        isinstance(cols, list) and cols and all(isinstance(c, str) for c in cols) for cols in touches.values()
    ):
        return [f"{name}: touches must map each table to its columns (`*` for the whole table)"]
    return []


def _disjoint(defects: list[dict]) -> list[str]:
    """Two defects on one database must not touch the same column; `*` touches the whole table."""
    found = []
    seen = defaultdict(list)  # (database, table) -> [(defect id, columns)]
    for d in defects:
        touches = d.get("touches")
        if not isinstance(touches, dict):
            continue
        for table, cols in touches.items():
            if not isinstance(cols, list):
                continue
            for other, other_cols in seen[(d.get("database"), table)]:
                shared = set(cols) & set(other_cols) or (["*"] if "*" in cols or "*" in other_cols else [])
                if shared:
                    found.append(
                        f"defects {other!r} and {d.get('id')!r} both touch {table} ({', '.join(sorted(shared))}) "
                        f"in database {d.get('database')}"
                    )
            seen[(d.get("database"), table)].append((d.get("id"), cols))
    return found


def _reach(name: str, d: dict, schema: dict[str, Schema] | None) -> tuple[list[str], list[str]]:
    """A column-formula relation's errors and its warnings about the identity search's reach."""
    relation = d.get("relation")
    if not isinstance(relation, dict) or any(_blank(relation.get(k)) for k in ("table", "target", "form", "operands")):
        return [f"{name}: a column-formula defect must declare its relation (table, target, form, operands)"], []
    warnings = []
    operands = relation["operands"]
    if relation["form"] != "sum" or len(operands) not in (2, 3):
        warnings.append(
            f"{name}: outside the identity search's reach: it finds a sum of two or three columns, "
            f"not a {relation['form']} of {len(operands)}"
        )
    columns = (schema or {}).get(d.get("database"), {}).get(relation["table"])
    if columns is None:
        warnings.append(f"{name}: column positions not checked, no schema for {d.get('database')}.{relation['table']}")
        return [], warnings
    # ponytail: numeric means a declared numeric type; the vendored search reads values, so a number
    # stored in a TEXT column would be missed. Read the values instead if a database ever needs it.
    numeric = [c for c, t in columns if NUMERIC_TYPE.search((t or "").upper())]
    for column in (relation["target"], *operands):
        if column not in numeric[:MAX_NUMERIC_COLUMNS]:
            warnings.append(
                f"{name}: column {column} is not among the first {MAX_NUMERIC_COLUMNS} numeric columns "
                f"of {relation['table']}, outside the identity search's reach"
            )
    return [], warnings


def _defect(raw: dict, schema: dict[str, Schema] | None) -> tuple[list[str], list[str]]:
    name = f"defect {raw.get('id')!r}"
    errors, warnings = [], []
    if _blank(raw.get("id")) or _blank(raw.get("database")):
        errors.append(f"{name}: it needs an id and a database")
    kind = (raw.get("slot") or {}).get("claim_kind")
    if kind not in {k.value for k in ClaimKind}:
        errors.append(f"{name}: slot claim_kind {kind!r} is not a claim kind")
    errors += [f"{name}: reference claim: {p}" for p in reference_claim_problems(raw.get("reference_claim"), raw.get("thresholds", ()))]
    errors += _touches(name, raw)
    errors += _readings(name, raw)
    errors += _drift(name, raw)
    if kind == ClaimKind.COVERAGE and not isinstance(raw.get("cut_tables"), list):
        errors.append(f"{name}: a coverage defect must declare cut_tables (`[]` when no related table is cut)")
    if kind == ClaimKind.COLUMN_FORMULA:
        e, w = _reach(name, raw, schema)
        errors += e
        warnings += w
    return errors, warnings


def _confirmatory_test(test: dict) -> list[str]:
    found = [f"the confirmatory test has no {k}" for k in CONFIRMATORY_KEYS if _blank(test.get(k))]
    pairing = test.get("pairing")
    if isinstance(pairing, dict):
        if pairing.get("by") != "question":
            found.append("the confirmatory test must be paired by question")
        runs = pairing.get("runs_per_question")
        if not isinstance(runs, int) or isinstance(runs, bool) or runs < 1:
            found.append("the confirmatory test pairing needs runs_per_question, a positive integer")
    failures = test.get("failures")
    if isinstance(failures, dict):
        if failures.get("primary") != PRIMARY_FAILURE_RULE:
            found.append(f"the confirmatory test's primary failure rule must be {PRIMARY_FAILURE_RULE}")
        excludes = failures.get("scored_excludes") or []
        found += [f"the confirmatory test's scored_excludes must list {x}" for x in SCORED_EXCLUDES if x not in excludes]
        sensitivity = failures.get("sensitivity") or []
        found += [f"the confirmatory test's sensitivity must list {x}" for x in SENSITIVITY if x not in sensitivity]
        if failures.get("report_failure_rate_per_rule") is not True:
            found.append("the confirmatory test must report the failure rate per rule")
    elif failures is not None:
        found.append("the confirmatory test's failures must say how failed and clarified responses enter")
    return found


def _global(part) -> list[str]:
    if not isinstance(part, dict) or not part:
        return ["the freeze has no global part"]
    found = [f"the global part has no {k}" for k in GLOBAL_KEYS if _blank(part.get(k))]
    if isinstance(part.get("confirmatory_test"), dict):
        found += _confirmatory_test(part["confirmatory_test"])
    return found


def validate(raw: dict, schema: dict[str, dict[str, list[tuple[str, str]]]] | None = None) -> tuple[list[str], list[str]]:
    """The errors and warnings of a freeze read from YAML. `schema` maps database to {table: [(column, type)]}."""
    errors = _global(raw.get("global"))
    warnings = []
    defects = raw.get("defects")
    if not isinstance(defects, list) or not defects:
        return errors + ["the freeze lists no defects"], warnings
    ids = [d.get("id") for d in defects]
    errors += [f"defect id {i!r} is used twice" for i in sorted({i for i in ids if ids.count(i) > 1}, key=str)]
    for d in defects:
        e, w = _defect(d, schema)
        errors += e
        warnings += w
    errors += _disjoint(defects)
    return errors, warnings


def read_schema(path: Path) -> Schema:
    """Table -> [(column, declared type)] of a SQLite file, in table order.

    The file's connection refuses PRAGMA (see `connect_read_only`), so the CREATE statements are read
    with a SELECT and replayed on an empty in-memory database, whose PRAGMA gives the columns.
    """
    con = connect_read_only(path)
    try:
        statements = con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL ORDER BY name").fetchall()
    finally:
        con.close()
    scratch = sqlite3.connect(":memory:")
    try:
        schema = {}
        for name, sql in statements:
            scratch.execute(sql)
            schema[name] = [(c[1], c[2]) for c in scratch.execute(f'PRAGMA table_info("{name}")')]
        return schema
    finally:
        scratch.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path, help="the freeze (configuration) file")
    args = parser.parse_args(argv)
    raw = yaml.safe_load(args.config.read_text())
    paths = {name: (args.config.parent / p).resolve() for name, p in (raw.get("databases") or {}).items()}
    schema = {name: read_schema(p) for name, p in paths.items() if p.is_file()} or None
    errors, warnings = validate(raw, schema)
    for line in errors:
        print(f"error: {line}")
    for line in warnings:
        print(f"warning: {line}")
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
