"""Week-one check of the candidate LiveSQLBench-Base-Lite databases (#59), for the database choice (#32).

    uv run python -m warrant.data.week_one

For every database of the fetched release it reports, with no model call and no battery run, the
candidates for the three claim kinds the thin write line injects defects for:

- column formula: additive numeric columns, found by the vendored Gloss identity search
  (gloss/detect/rule.py) mirrored over SQLite, and tables where such a relation could be injected;
- value meaning: coded value columns, and whether the column meanings or the knowledge base
  document their codes;
- coverage: low-cardinality text columns that split a table into populations, with the tables
  related to it on declared foreign keys.

It ranks the databases, lists the pairs that offer a candidate of each kind, suggests one pair, and
writes a Markdown report and the full JSON output to docs/research/.
"""

import argparse
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Any

from warrant.data.release import Database, Release, load_database

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO / "configs" / "livesqlbench-base-lite.yaml"
DEFAULT_OUT_DIR = REPO / "docs" / "research"
REPORT_NAME = "2026-10-11-week-one-database-check.md"
JSON_NAME = "week-one-database-check.json"

# The vendored identity search's reach (gloss/detect/rule.py).
IDENTITY_MIN_SHARE = 0.80
MAX_NUMERIC_COLUMNS = 12
TOLERANCE = 0.005
# A table where a data change could make one numeric column equal the sum of two others.
INJECTABLE_MIN_COLUMNS = 3
# A coded value column or a status column has this many distinct non-null values.
MIN_CODES, MAX_CODES = 2, 12

KINDS = ("column_formula", "value_meaning", "coverage")
# Column names are abbreviated (equipstatus, decodestat, risklev), so they are matched on fragments;
# column meanings are matched on whole words, leaving out their "Data type: ..." clause.
STATUS_IN_NAME = re.compile(r"stat(?!ion)|stage|phase|type|categ|flag|level|lvl|lev$|class|tier|grade")
STATUS_IN_MEANING = re.compile(
    r"\b(status|state|stage|phase|type|category|flag|level|class|classification|tier|grade)\b", re.IGNORECASE
)
DATA_TYPE_CLAUSE = re.compile(r"Data type:[^.]*\.")
LISTS_CATEGORIES = re.compile(r"possible (categories|values)", re.IGNORECASE)


@dataclass(frozen=True)
class Table:
    name: str
    columns: list[str]
    rows: list[tuple]
    primary_key: list[str]


def read_tables(path: Path) -> list[Table]:
    """Every table of a SQLite file, read-only: columns in table order, all rows, primary key columns."""
    con = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = []
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
            cursor = con.execute(f'SELECT * FROM "{name}"')
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            primary_key = [c[1] for c in con.execute(f'PRAGMA table_info("{name}")') if c[5]]
            tables.append(Table(name, columns, rows, primary_key))
        return tables
    finally:
        con.close()


# Column formula ----------------------------------------------------------------------------------


def as_number(value: Any) -> float | None:
    """A value as the vendored battery sees it: the text of a CSV cell, cast to a double if it parses."""
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def numeric_columns(table: Table) -> list[str]:
    """Columns, in table order, whose populated values (not NULL, not empty) all parse as numbers."""
    out = []
    for i, column in enumerate(table.columns):
        populated = [row[i] for row in table.rows if row[i] is not None and row[i] != ""]
        if populated and all(as_number(v) is not None for v in populated):
            out.append(column)
    return out


def identities(table: Table, numeric: list[str]) -> list[dict]:
    """target = sum of two or three other columns, searched exactly as the vendored RuleDetector does.

    Among the first 12 numeric columns, each target gets its best-scoring combination of two or three
    others, counted only on rows where the target parses and is non-zero; a component that is NULL or
    does not parse counts as 0. It is reported if it holds within the tolerance on at least 80 percent
    of those rows.
    """
    pool = numeric[:MAX_NUMERIC_COLUMNS]
    values = {c: [as_number(row[table.columns.index(c)]) for row in table.rows] for c in pool}
    out = []
    for target in pool:
        others = [c for c in pool if c != target]
        combos = [*combinations(others, 2), *combinations(others, 3)]
        if not combos:
            continue
        best = _best_combo(values, target, combos)
        if best is not None:
            combo, holds, n = best
            out.append({
                "table": table.name,
                "target": target,
                "components": list(combo),
                "share": round(holds / n, 4),
                "holds": holds,
                "rows": n,
                "positions": {c: numeric.index(c) + 1 for c in (target, *combo)},
            })
    return out


def _best_combo(values: dict[str, list], target: str, combos: list[tuple]) -> tuple[tuple, int, int] | None:
    """Highest-share combination for this target, ties to fewer terms, or None below the bar."""
    rows = [i for i, v in enumerate(values[target]) if v is not None and v != 0]
    n = len(rows)
    if not n:
        return None
    t = [values[target][i] for i in rows]
    parts = {c: [values[c][i] or 0.0 for i in rows] for c in values}
    # Sums are built left to right, as the SQL `a + b + c` does; Python's sum() would round differently.
    pair_sums: dict[tuple, list[float]] = {}
    scored = []
    for combo in combos:
        a, b = combo[0], combo[1]
        if (a, b) not in pair_sums:
            pair_sums[(a, b)] = [y + z for y, z in zip(parts[a], parts[b])]
        total = pair_sums[(a, b)]
        if len(combo) == 3:
            total = [s + w for s, w in zip(total, parts[combo[2]])]
        holds = sum(1 for x, s in zip(t, total) if abs(x - s) < TOLERANCE)
        scored.append((holds / n, len(combo), combo, holds))
    share, _, combo, holds = max(scored, key=lambda s: (s[0], -s[1]))
    return (combo, holds, n) if share >= IDENTITY_MIN_SHARE else None


# Value meaning and coverage ----------------------------------------------------------------------


def mentions(text: str, word: str, ignore_case: bool = False) -> bool:
    """Whether `word` occurs in `text` with no letter, digit or underscore directly on either side."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE if ignore_case else 0) is not None


def value_counts(table: Table, column: str) -> list[dict]:
    i = table.columns.index(column)
    counts = Counter(row[i] for row in table.rows if row[i] is not None)
    return [{"value": v, "rows": n} for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def kb_text(entry: dict) -> str:
    return " ".join(str(entry.get(k, "")) for k in ("knowledge", "description", "definition"))


def meaning_text(meaning: Any) -> str:
    """A column meaning as text; a JSON column's meaning is a dict describing its fields."""
    if meaning is None:
        return ""
    return meaning if isinstance(meaning, str) else json.dumps(meaning)


def coded_column(db: Database, text: str, table: Table, column: str, numeric: bool, values: list[dict]) -> dict:
    """A coded value column and where its codes are documented."""
    codes = [str(v["value"]) for v in values]
    in_meaning = [c for c in codes if mentions(text, c, ignore_case=True)]
    kb_values = {}
    for code in codes:
        if re.search(r"[A-Za-z]", code):
            ids = [e["id"] for e in db.knowledge_base if mentions(kb_text(e), code)]
            if ids:
                kb_values[code] = ids
    return {
        "table": table.name,
        "column": column,
        "meaning": text,
        "numeric": numeric,
        "distinct": len(values),
        "values": values,
        "lists_categories": bool(LISTS_CATEGORIES.search(text)),
        "values_in_meaning": in_meaning,
        "documented": bool(text) and len(in_meaning) == len(codes),
        "kb_mentions_column": [e["id"] for e in db.knowledge_base if mentions(kb_text(e), column, ignore_case=True)],
        "kb_mentions_value": kb_values,
        "kb_value_illustrations": [
            e["id"] for e in db.knowledge_base
            if e.get("type") == "value_illustration"
            and str(e.get("knowledge", "")).split(":")[0].strip().lower() == column.lower()
        ],
    }


def is_status_like(column: str, meaning: str) -> bool:
    return bool(STATUS_IN_NAME.search(column.lower()) or STATUS_IN_MEANING.search(DATA_TYPE_CLAUSE.sub(" ", meaning)))


def related_tables(db: Database, table: str) -> list[dict]:
    """Tables joined to `table` by a declared foreign key, in either direction."""
    out = []
    for fk in db.foreign_keys:
        link = {"from": f"{fk.table}.{fk.column}", "to": f"{fk.ref_table}.{fk.ref_column}",
                "same_named": fk.column.lower() == fk.ref_column.lower()}
        if fk.table.lower() == table.lower():
            out.append({"related_table": fk.ref_table, "direction": "references", **link})
        if fk.ref_table.lower() == table.lower():
            out.append({"related_table": fk.table, "direction": "referenced by", **link})
    return sorted(out, key=lambda r: (r["related_table"], r["from"]))


def coverage_order(candidate: dict, related: list[dict]) -> tuple:
    return (not candidate["status_like"], not any(r["same_named"] for r in related), -len(related),
            candidate["table"], candidate["column"])


def coded_order(candidate: dict) -> tuple:
    return (not candidate["documented"], not candidate["kb_value_illustrations"], -len(candidate["kb_mentions_column"]),
            candidate["table"], candidate["column"])


# Per database ------------------------------------------------------------------------------------


def check_database(release_dir: Path, name: str) -> dict:
    db = load_database(release_dir, name)
    # Keys are "<db>|<Table>|<Column>" in original casing, and the prefix is not always the database
    # name (cross_db uses "cross"), so they are matched on table and column only.
    meanings = {tuple(k.lower().split("|")[1:]): v for k, v in db.column_meanings.items()}
    keys = {(fk.table.lower(), fk.column.lower()) for fk in db.foreign_keys}
    keys |= {(fk.ref_table.lower(), fk.ref_column.lower()) for fk in db.foreign_keys}
    tables = read_tables(db.path)
    links = {table.name: related_tables(db, table.name) for table in tables}
    found, injectable, coded, coverage = [], [], [], []
    for table in tables:
        keys |= {(table.name.lower(), c.lower()) for c in table.primary_key}
        numeric = numeric_columns(table)
        for identity in identities(table, numeric):
            identity["kb_mentions_target"] = [e["id"] for e in db.knowledge_base
                                              if mentions(kb_text(e), identity["target"], ignore_case=True)]
            found.append(identity)
        pool = numeric[:MAX_NUMERIC_COLUMNS]
        if len(pool) >= INJECTABLE_MIN_COLUMNS:
            injectable.append({"table": table.name, "numeric_columns": pool,
                               "declared_keys": [c for c in pool if (table.name.lower(), c.lower()) in keys]})
        for column in table.columns:
            if (table.name.lower(), column.lower()) in keys:
                continue
            values = value_counts(table, column)
            if not MIN_CODES <= len(values) <= MAX_CODES:
                continue
            text = meaning_text(meanings.get((table.name.lower(), column.lower())))
            coded.append(coded_column(db, text, table, column, column in numeric, values))
            if column not in numeric:
                coverage.append({
                    "table": table.name,
                    "column": column,
                    "status_like": is_status_like(column, text),
                    "distinct": len(values),
                    "values": values,
                })
    return {
        "database": name,
        "tables": len(tables),
        "foreign_keys": len(db.foreign_keys),
        "same_named_foreign_keys": [
            f"{fk.table}.{fk.column} -> {fk.ref_table}.{fk.ref_column}"
            for fk in db.foreign_keys if fk.column.lower() == fk.ref_column.lower()
        ],
        "column_formula": {"identities": found, "injectable_tables": injectable},
        "value_meaning": sorted(coded, key=coded_order),
        # A status column's related tables are those of its table, listed once per table below.
        "coverage": sorted(coverage, key=lambda c: coverage_order(c, links[c["table"]])),
        "related_tables": {table: related for table, related in links.items() if related},
    }


def check_release(release_dir: Path, names: list[str]) -> dict:
    """The week-one report for these databases of a fetched release."""
    databases = {name: check_database(release_dir, name) for name in names}
    same_named_exists = any(d["same_named_foreign_keys"] for d in databases.values())
    best = {name: best_candidates(d, same_named_exists) for name, d in databases.items()}
    for name, d in databases.items():
        d["best_candidates"] = {kind: c and {k: v for k, v in c.items() if k != "quality"}
                                for kind, c in best[name].items()}
    ranking = rank(databases)
    pairs = qualifying_pairs([r["database"] for r in ranking], best)
    return {
        "thresholds": thresholds(),
        "databases": databases,
        "ranking": ranking,
        "pairs": pairs,
        "suggested_pair": pairs[0] if pairs else None,
    }


def thresholds() -> dict:
    return {
        "identity_min_share": IDENTITY_MIN_SHARE,
        "identity_tolerance": TOLERANCE,
        "identity_max_numeric_columns": MAX_NUMERIC_COLUMNS,
        "identity_terms": [2, 3],
        "injectable_min_numeric_columns": INJECTABLE_MIN_COLUMNS,
        "codes_min_distinct": MIN_CODES,
        "codes_max_distinct": MAX_CODES,
    }


# Ranking, pairs and the suggestion ---------------------------------------------------------------


def best_candidates(report: dict, same_named_exists: bool) -> dict[str, dict | None]:
    """The best candidate of each kind in one database, with a quality to compare it across databases.

    Each candidate records whether it meets the kind's preference for #32: a present identity, a coded
    column whose codes its column meaning lists, and a status-like column whose related tables include
    a same-named key (or, if the release has no same-named key at all, any related table).
    """
    out: dict[str, dict | None] = dict.fromkeys(KINDS)
    formula = report["column_formula"]
    if formula["identities"]:
        best = max(formula["identities"], key=lambda i: (i["share"], i["rows"], -len(i["components"])))
        out["column_formula"] = {
            "preferred": True, "quality": (2, best["share"], best["rows"], -len(best["components"])),
            "table": best["table"], "column": best["target"], "summary": describe_identity(best),
        }
    elif formula["injectable_tables"]:
        best = max(formula["injectable_tables"], key=lambda t: len(t["numeric_columns"]))
        out["column_formula"] = {
            "preferred": False, "quality": (1, len(best["numeric_columns"])), "table": best["table"], "column": None,
            "summary": f"{best['table']}: no identity present; a sum could be injected among its "
                       f"{len(best['numeric_columns'])} pool numeric columns",
        }
    if report["value_meaning"]:
        best = report["value_meaning"][0]
        out["value_meaning"] = {
            "preferred": best["documented"],
            "quality": (best["documented"], bool(best["kb_value_illustrations"]), len(best["kb_mentions_column"])),
            "table": best["table"], "column": best["column"],
            "summary": f"{best['table']}.{best['column']}: {describe_values(best['values'])}"
                       + ("; all codes listed in its column meaning" if best["documented"] else ""),
        }
    if report["coverage"]:
        best = report["coverage"][0]
        related = report["related_tables"].get(best["table"], [])
        same_named = any(r["same_named"] for r in related)
        out["coverage"] = {
            "preferred": best["status_like"] and (same_named if same_named_exists else bool(related)),
            "quality": (best["status_like"], same_named, len(related)),
            "table": best["table"], "column": best["column"],
            "summary": f"{best['table']}.{best['column']}: {describe_values(best['values'])}; related on "
                       f"{len(related)} declared foreign keys, "
                       + (f"same-named to {', '.join(r['related_table'] for r in related if r['same_named'])}"
                          if same_named else "none same-named"),
        }
    return out


def describe_identity(identity: dict) -> str:
    return (f"{identity['table']}: {identity['target']} = {' + '.join(identity['components'])} on "
            f"{identity['holds']} of {identity['rows']} rows with a non-zero target")


def describe_values(values: list[dict], limit: int = 6) -> str:
    shown = ", ".join(f"{v['value']} ({v['rows']})" for v in values[:limit])
    return shown + (f", and {len(values) - limit} more" if len(values) > limit else "")


def describe_related(related: list[dict]) -> str:
    return "; ".join(
        f"{r['related_table']} ({r['from']} -> {r['to']}, {'same-named' if r['same_named'] else 'names differ'})"
        for r in related
    ) or "none"


def offered(report: dict) -> dict[str, str | None]:
    formula = report["column_formula"]
    return {
        "column_formula": ("identity" if formula["identities"] else
                           "injectable" if formula["injectable_tables"] else None),
        "value_meaning": "coded column" if report["value_meaning"] else None,
        "coverage": "status column" if report["coverage"] else None,
    }


def score(report: dict) -> float:
    """Kinds offered; a present identity counts 1, an injectable table without one counts 0.5."""
    kinds = offered(report)
    return {"identity": 1.0, "injectable": 0.5, None: 0.0}[kinds["column_formula"]] + sum(
        kinds[k] is not None for k in ("value_meaning", "coverage")
    )


def rank(databases: dict[str, dict]) -> list[dict]:
    """Databases by score; ties by identities, documented coded columns, then status columns with related tables."""
    rows = []
    for name, report in databases.items():
        coverage = report["coverage"]
        rows.append({
            "database": name,
            "score": score(report),
            "kinds": offered(report),
            "identities": len(report["column_formula"]["identities"]),
            "injectable_tables": len(report["column_formula"]["injectable_tables"]),
            "coded_columns": len(report["value_meaning"]),
            "documented_coded_columns": sum(c["documented"] for c in report["value_meaning"]),
            "coverage_candidates": len(coverage),
            "status_like_with_related_tables": sum(
                c["status_like"] and c["table"] in report["related_tables"] for c in coverage
            ),
            "same_named_foreign_keys": len(report["same_named_foreign_keys"]),
        })
    return sorted(rows, key=lambda r: (-r["score"], -r["identities"], -r["documented_coded_columns"],
                                       -r["status_like_with_related_tables"], r["database"]))


def qualifying_pairs(order: list[str], best: dict[str, dict]) -> list[dict]:
    """Pairs whose three candidates, one per kind, can be placed with at least one in each database.

    For each pair the placement with the most preferences met is kept, then the best column formula,
    coverage and value-meaning candidates in that order. Pairs are returned best first, ties in the
    order of the databases given.
    """
    scored = []
    for a, b in combinations(order, 2):
        placements = []
        for placement in product((a, b), repeat=len(KINDS)):
            formula, value, coverage = (best[db][kind] for db, kind in zip(placement, KINDS))
            if len(set(placement)) < 2 or None in (formula, value, coverage):
                continue
            preferred = formula["preferred"] + value["preferred"] + coverage["preferred"]
            placements.append(((preferred, formula["quality"], coverage["quality"], value["quality"]), placement))
        if placements:
            key, placement = max(placements, key=lambda p: p[0])
            scored.append((key, {
                "databases": [a, b],
                "preferences_met": key[0],
                # Which database's best candidate (see best_candidates) each kind takes.
                "placement": dict(zip(KINDS, placement)),
            }))
    return [pair for _, pair in sorted(scored, key=lambda s: s[0], reverse=True)]


# Report ------------------------------------------------------------------------------------------


def cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict) -> str:
    """The human-readable week-one report."""
    databases, ranking, pairs = report["databases"], report["ranking"], report["pairs"]
    t = report["thresholds"]
    all_fks = sum(d["foreign_keys"] for d in databases.values())
    same_named = [(name, fk) for name, d in databases.items() for fk in d["same_named_foreign_keys"]]
    n_tables = sum(d["tables"] for d in databases.values())
    with_identity = [name for name, d in databases.items() if d["column_formula"]["identities"]]
    n_identities = sum(len(databases[name]["column_formula"]["identities"]) for name in with_identity)
    identity_pairs = [p for p in pairs if chosen(report, p, "column_formula")["preferred"]]
    spreads = [max(v["rows"] for v in c["values"]) / min(v["rows"] for v in c["values"])
               for d in databases.values() for c in d["value_meaning"] if not c["numeric"]]
    source = (f"the pinned release (`{report['dataset']}` at revision `{report['revision']}`)"
              if "dataset" in report else "the given release directory")
    out = [
        "# Week-one check of the candidate LiveSQLBench-Base-Lite databases",
        "",
        f"2026-10-11. Issue #59, for the database choice in #32. Generated by "
        f"`uv run python -m warrant.data.week_one` from {source}, with no model call and no battery run. "
        f"The full output, with every candidate, is in [{JSON_NAME}]({JSON_NAME}). Table and column names, "
        f"codes and column-meaning text quoted here come from LiveSQLBench-Base-Lite (CC BY-SA 4.0).",
        "",
        "## Summary",
        "",
        f"- {len(databases)} databases, {n_tables} tables. Column formula: {n_identities} identity within the "
        f"vendored search's reach, in {', '.join(with_identity) or 'no database'}; "
        f"{sum(1 for d in databases.values() if d['column_formula']['injectable_tables'])} databases have tables "
        f"where one could be injected. Value meaning: "
        f"{sum(1 for d in databases.values() if d['value_meaning'])} databases have coded value columns. Coverage: "
        f"{sum(1 for d in databases.values() if d['coverage'])} databases have status columns.",
    ]
    if pairs:
        suggested = report["suggested_pair"]
        out += [
            f"- {len(pairs)} database pairs offer a candidate of each kind; {len(identity_pairs)} of them with a "
            f"present identity.",
            f"- Suggested pair for #32: **{' + '.join(suggested['databases'])}** (a suggestion; the write-line lead "
            f"decides #32).",
        ]
    else:
        out += [
            "- **No pair of databases offers a candidate of each kind.** Per #59 the fallback is to check the BIRD "
            "dev databases the same way; this command does not do that.",
        ]
    out += [
        "",
        "## Caveats",
        "",
        "- **These databases may be more synthetic than BIRD's (ADR 0009).** In "
        f"{sum(s <= 1.25 for s in spreads)} of the {len(spreads)} coded text columns the most frequent code is at "
        "most 1.25 times as frequent as the least frequent one, an even spread real business data rarely shows, "
        "and relations that real data carries (such as totals of components) are mostly absent.",
        f"- **Identities are rare.** The vendored identity search finds {n_identities} in the {n_tables} tables, "
        "so a column-formula defect elsewhere would have to inject one as a data change.",
        f"- **The link detector sees almost none of the declared foreign keys.** {all_fks - len(same_named)} of "
        f"the {all_fks} declared foreign keys join columns with different names (for example "
        "`signals.telescref -> telescopes.telescregistry`). The vendored Gloss link detector pairs key columns by "
        "name only (`name_matched_pairs` in `gloss/detect/link.py`), so it sees only "
        + (", ".join(f"`{name}: {fk}`" for name, fk in same_named) or "none of them")
        + ". Each coverage candidate below marks which of its related keys are same-named.",
        "- **What the identity search mirrors.** `numeric_columns`, `_identities` and `_best_combo` of "
        "`gloss/detect/rule.py`, run in Python over SQLite with every value read as text, as the CSV export the "
        "battery reads would hold it. The battery's GRAIN detector also restricts the rows to top-level records "
        "on tables with a self-reference; this check does not. Like Gloss, the pool includes numeric key "
        "columns.",
        "",
        "## Thresholds",
        "",
        "| Check | Rule |",
        "|---|---|",
        f"| Numeric column | Every populated value (not NULL, not empty) parses as a number; in table column order |",
        f"| Identity pool | The first {t['identity_max_numeric_columns']} numeric columns of a table |",
        f"| Identity | A target equals the sum of {' or '.join(map(str, t['identity_terms']))} other pool columns "
        f"within an absolute tolerance of {t['identity_tolerance']}, on at least "
        f"{t['identity_min_share']:.0%} of the rows where the target parses and is non-zero; a NULL or "
        f"unparsable component counts as 0; best share per target, ties to fewer terms |",
        f"| Injectable table | At least {t['injectable_min_numeric_columns']} numeric columns in the pool |",
        f"| Coded value column | {t['codes_min_distinct']} to {t['codes_max_distinct']} distinct non-null values; "
        f"declared primary-key and foreign-key columns skipped |",
        "| Documented codes | Every code occurs in the column's meaning (whole word, any case) |",
        "| Knowledge-base mentions | Column name: whole word, any case, in an entry's knowledge, description or "
        "definition. Code: whole word, same case, codes with a letter only. `value_illustration` entry: an entry "
        "of that type whose title is the column name, alone or before a colon |",
        "| Status column | A coded value column whose values are not all numeric |",
        "| Status-like | The column name contains stat, stage, phase, type, categ, flag, level, lvl, class, tier "
        "or grade (or ends in lev), or its meaning, outside any `Data type:` clause, has the word status, state, "
        "stage, phase, type, category, flag, level, class, classification, tier or grade |",
        "",
        "## Ranking",
        "",
        "Score: one point per claim kind offered, except that a column formula offered only as an injectable "
        "table counts half. Ties go to more identities, then more documented coded columns, then more "
        "status-like columns with related tables.",
        "",
        "| Rank | Database | Score | Identities | Injectable tables | Coded columns (documented) | "
        "Status columns (status-like with related tables) | Same-named foreign keys |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranking, 1):
        out.append(
            f"| {i} | {r['database']} | {r['score']} | {r['identities']} | {r['injectable_tables']} | "
            f"{r['coded_columns']} ({r['documented_coded_columns']}) | {r['coverage_candidates']} "
            f"({r['status_like_with_related_tables']}) | {r['same_named_foreign_keys']} |"
        )
    out += ["", "## Pairs that offer a candidate of each kind", ""]
    if not pairs:
        out += ["No pair of databases offers a candidate of each kind.", ""]
    else:
        out += [
            "A pair qualifies when one candidate of each kind can be placed with at least one in each database. "
            "Each pair shows its best placement: the most preferences met (a present identity, a coded column "
            "whose codes its column meaning lists, a status-like column with a same-named related key), then "
            "the strongest column formula, coverage and value-meaning candidates.",
            "",
        ]
        shown = identity_pairs or pairs[:10]
        out += pair_table(report, shown)
        rest = [p for p in pairs if p not in shown]
        if rest:
            out += [
                "",
                f"The other {len(rest)} pairs offer the column formula only as an injectable table. The ten best:",
                "",
                *pair_table(report, rest[:10]),
            ]
        out += ["", *suggestion(report), ""]
    out += ["## Per database", "", "The ten best candidates per kind; every candidate is in the JSON.", ""]
    for r in ranking:
        out += database_section(databases[r["database"]])
    return "\n".join(out).rstrip() + "\n"


def chosen(report: dict, pair: dict, kind: str) -> dict:
    """The candidate a pair takes for one kind: the best of that kind in the database placed there."""
    database = pair["placement"][kind]
    return {"database": database, **report["databases"][database]["best_candidates"][kind]}


def id_list(values: list) -> str:
    return ", ".join(map(str, values)) or "none"


def pair_table(report: dict, pairs: list[dict]) -> list[str]:
    rows = ["| Pair | Preferences met | Column formula | Value meaning | Coverage |", "|---|---|---|---|---|"]
    for p in pairs:
        cells = [chosen(report, p, kind) for kind in KINDS]
        rows.append(f"| {' + '.join(p['databases'])} | {p['preferences_met']} of 3 | "
                    + " | ".join(cell(f"{c['database']}.{c['summary']}") for c in cells) + " |")
    return rows


def suggestion(report: dict) -> list[str]:
    pair = report["suggested_pair"]
    databases = report["databases"]
    out = [
        f"## Suggested pair for #32: {' + '.join(pair['databases'])}",
        "",
        "This is a suggestion from the week-one check. The write-line lead decides #32.",
        "",
    ]
    formula = chosen(report, pair, "column_formula")
    if formula["column"] is not None:
        identity = next(i for i in databases[formula["database"]]["column_formula"]["identities"]
                        if (i["table"], i["target"]) == (formula["table"], formula["column"]))
        positions = ", ".join(f"{col} {pos}" for col, pos in identity["positions"].items())
        out.append(
            f"- **Column formula: {formula['database']}.{describe_identity(identity)}.** A present identity at "
            f"numeric-column positions {positions}, within the first 12 the vendored identity search reads, so "
            f"the baseline battery can find it. Knowledge-base entries naming the target: "
            f"{id_list(identity['kb_mentions_target'])}."
        )
    else:
        out.append(f"- **Column formula: {formula['database']}.{formula['summary']}.** No identity is present in "
                   "this pair, so the defect would inject one within the first 12 numeric columns.")
    value = chosen(report, pair, "value_meaning")
    coded = next(c for c in databases[value["database"]]["value_meaning"]
                 if (c["table"], c["column"]) == (value["table"], value["column"]))
    listed = ("Its column meaning lists every code" if coded["documented"] else
              f"Its column meaning lists {len(coded['values_in_meaning'])} of the {coded['distinct']} codes")
    out.append(
        f"- **Value meaning: {value['database']}.{coded['table']}.{coded['column']}**, codes "
        f"{describe_values(coded['values'])}. {listed} (\"{cell(coded['meaning'])}\"). Knowledge-base "
        f"`value_illustration` entries for it: {id_list(coded['kb_value_illustrations'])}; entries naming the "
        f"column: {id_list(coded['kb_mentions_column'])}."
    )
    coverage = chosen(report, pair, "coverage")
    status = next(c for c in databases[coverage["database"]]["coverage"]
                  if (c["table"], c["column"]) == (coverage["table"], coverage["column"]))
    related = databases[coverage["database"]]["related_tables"].get(status["table"], [])
    visible = [r for r in related if r["same_named"]]
    out.append(
        f"- **Coverage: {coverage['database']}.{status['table']}.{status['column']}**, "
        f"{'a status-like column' if status['status_like'] else 'a low-cardinality text column'} splitting the "
        f"table into {describe_values(status['values'])}. Related tables on declared foreign keys: "
        f"{describe_related(related)}. "
        + (f"{len(visible)} of these keys is same-named, so the vendored link detector can see that join; it "
           "cannot see the others." if visible else
           "None of these keys is same-named, so the vendored link detector sees none of these joins.")
    )
    alternatives = [p for p in report["pairs"][1:4]]
    if alternatives:
        out += ["", "Next best pairs: " + "; ".join(
            f"{' + '.join(p['databases'])} ({p['preferences_met']} of 3 preferences)" for p in alternatives) + "."]
    return out


def database_section(d: dict, limit: int = 10) -> list[str]:
    formula = d["column_formula"]
    out = [f"### {d['database']}", "", f"{d['tables']} tables, {d['foreign_keys']} declared foreign keys "
           f"({len(d['same_named_foreign_keys'])} same-named).", ""]
    out.append(f"**Column formula.** Identities: "
               + ("; ".join(f"{describe_identity(i)} ({i['share']:.0%}; numeric-column positions "
                            f"{', '.join(str(p) for p in i['positions'].values())})" for i in formula["identities"])
                  or "none") + ".")
    out.append("")
    if formula["injectable_tables"]:
        out.append("Injectable tables (pool numeric columns; declared keys marked with *): "
                   + "; ".join(f"`{t['table']}` ("
                               + ", ".join(c + ("*" if c in t["declared_keys"] else "") for c in t["numeric_columns"])
                               + ")" for t in formula["injectable_tables"]) + ".")
        out.append("")
    coded = d["value_meaning"]
    out += [f"**Value meaning.** {len(coded)} coded columns, {sum(c['documented'] for c in coded)} with every code "
            f"in their column meaning.", ""]
    if coded:
        out += ["| Column | Codes (rows) | Documented | KB `value_illustration` entries | "
                "KB entries naming the column |",
                "|---|---|---|---|---|"]
        for c in coded[:limit]:
            documented = "yes" if c["documented"] else f"{len(c['values_in_meaning'])} of {c['distinct']}"
            out.append(f"| {c['table']}.{c['column']} | {cell(describe_values(c['values']))} | {documented} | "
                       f"{', '.join(map(str, c['kb_value_illustrations'])) or '-'} | "
                       f"{', '.join(map(str, c['kb_mentions_column'])) or '-'} |")
        out.append("")
    coverage = d["coverage"]
    out += [f"**Coverage.** {len(coverage)} status columns, {sum(c['status_like'] for c in coverage)} status-like.",
            ""]
    if coverage:
        out += ["| Column | Status-like | Values (rows) | Related tables on declared foreign keys |",
                "|---|---|---|---|"]
        for c in coverage[:limit]:
            related = d["related_tables"].get(c["table"], [])
            out.append(f"| {c['table']}.{c['column']} | {'yes' if c['status_like'] else 'no'} | "
                       f"{cell(describe_values(c['values']))} | {cell(describe_related(related))} |")
        out.append("")
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    release = Release.from_yaml(args.config)
    report = {
        "dataset": release.dataset,
        "revision": release.revision,
        "attribution": "Table and column names, codes, column meanings and knowledge-base ids come from "
                       "LiveSQLBench-Base-Lite (CC BY-SA 4.0).",
        **check_release(release.local_dir(), list(release.databases)),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / JSON_NAME).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    (args.out_dir / REPORT_NAME).write_text(render_markdown(report))
    print(f"Checked {len(release.databases)} databases; wrote {REPORT_NAME} and {JSON_NAME} to {args.out_dir}")


if __name__ == "__main__":
    main()
