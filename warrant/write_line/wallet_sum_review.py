"""The wallet-sum per-question review (#54, asked on PR #122 on 2026-10-24).

Under the true reading walletsum = availsum + frozensum + margsum, so an answer that sums the balance
columns instead of reading walletsum can reach the gold answer. This review classes every answer to
a wallet-sum probe by the balance columns that decide it:

- the answer expression: the outermost SELECT's one projection, or, when there are several, the one
  left after dropping bare column references; an alias is followed to its definition in a subquery
  or CTE;
- the comparison predicates: balance columns in any WHERE, HAVING or JOIN condition.

An answer whose deciding columns include walletsum is `reads_walletsum`; one with components only is
`components_only`; one with no single answer expression, no balance column or SQL that does not
parse is `unclear`; one with no final SQL is `no_sql`. A hand-checked category in the overrides file
replaces the computed one for every answer with that normalized SQL.

Separately, `answer_column_equals_gold` says whether the answer expression's column of the executed
result equals the gold value within the scoring tolerance: it tells a wrong answer that only carries
extra columns from one whose answer is wrong. It is `undetermined` without a single answer
expression, and it does not change the category.

    uv run python -m warrant.write_line.wallet_sum_review --config configs/write_line_thin.yaml --freeze freeze/write_line.yaml --results results/thin/2026-10-24-66a86cb.jsonl --out-dir results/thin/wallet_sum_review

The gold values are read from the injected copies, which are built, not changed. No model is called.
"""

import argparse
import csv
import json
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import sqlglot
import yaml
from sqlglot import exp

from warrant.data.sqlite import query
from warrant.defects.build import build
from warrant.scoring.classify import TOLERANCE, _close
from warrant.write_line.config import Config, Question, load_config

DEFECT = "wallet-sum"
DIALECT = "sqlite"
READS_WALLETSUM = "reads_walletsum"
COMPONENTS_ONLY = "components_only"
UNCLEAR = "unclear"
NO_SQL = "no_sql"
CATEGORIES = (READS_WALLETSUM, COMPONENTS_ONLY, UNCLEAR, NO_SQL)
# The review list puts the answers that most need a look first.
REVIEW_ORDER = (UNCLEAR, COMPONENTS_ONLY, READS_WALLETSUM)
UNDETERMINED = "undetermined"
ANSWER_FIELDS = ("question", "rule", "run", "response_class", "category", "answer_column_equals_gold",
                 "answer_expression", "deciding_columns", "final_sql", "note")
SUMMARY_FIELDS = ("view", "question", "rule", "category", "correct", "wrong", "other", "total")
REVIEW_FIELDS = ("category", "answer_expression", "deciding_columns", "count", "example_rule",
                 "example_run", "example_response_class", "normalized_sql", "note")
OVERRIDE_FIELDS = ("normalized_sql", "category", "reason")


@dataclass(frozen=True)
class Balance:
    """The column the defect rewrote and the columns its readings compute it from."""

    target: str
    components: frozenset[str]

    @property
    def columns(self) -> frozenset[str]:
        return self.components | {self.target}


@dataclass(frozen=True)
class Classification:
    category: str
    answer_expression: str = ""
    deciding_columns: tuple[str, ...] = ()
    note: str = ""
    # The answer expression's position in the outermost SELECT, when the result's columns map onto
    # its projections one to one (no star).
    answer_index: int | None = None


def balance_columns(freeze: Mapping, defect: str = DEFECT) -> Balance:
    """The defect's relation target and every other column its readings' transformations assign it
    from, read from the freeze."""
    d = next(d for d in freeze["defects"] if d["id"] == defect)
    target = d["relation"]["target"].lower()
    statements = list(d.get("transformation", []))
    for reading in d.get("readings", []):
        statements += reading.get("transformation", [])
    components = set()
    for statement in statements:
        for eq in sqlglot.parse_one(statement, read=DIALECT).expressions:
            if eq.this.name.lower() == target:
                components |= {c.name.lower() for c in eq.expression.find_all(exp.Column)}
    return Balance(target, frozenset(components - {target}))


def wallet_sum_questions(config: Config, defect: str = DEFECT) -> list[Question]:
    return [q for q in config.questions if q.defect == defect]


def _parse(sql: str) -> exp.Expression | None:
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except sqlglot.errors.SqlglotError:
        return None
    return statements[0] if len(statements) == 1 else None


def normalize_sql(sql: str | None) -> str:
    """One spelling per query, so that answers and hand overrides with the same SQL meet: sqlglot's
    rendering, lowercased, or the whitespace-collapsed text when it does not parse."""
    if not sql or not sql.strip():
        return ""
    tree = _parse(sql)
    text = tree.sql(dialect=DIALECT) if tree is not None else " ".join(sql.split())
    return text.lower()


def _aliases(tree: exp.Expression) -> dict[str, list[exp.Expression]]:
    """Every output alias in the query and its definitions. Scopes are not told apart: an alias
    defined twice resolves to both definitions."""
    found: dict[str, list[exp.Expression]] = {}
    for alias in tree.find_all(exp.Alias):
        if alias.alias:
            found.setdefault(alias.alias.lower(), []).append(alias.this)
    return found


def _columns(node: exp.Expression, aliases: Mapping[str, list[exp.Expression]], visiting=frozenset()) -> set[str]:
    """The base columns a node reads, following aliases to their definitions."""
    columns = set()
    for column in node.find_all(exp.Column):
        name = column.name.lower()
        if not name or name in visiting or name not in aliases:
            if name:
                columns.add(name)
            continue
        for definition in aliases[name]:
            columns |= _columns(definition, aliases, visiting | {name})
    return columns


def _bare(projection: exp.Expression, aliases: Mapping) -> bool:
    """A projection that only lists a stored column, as opposed to one computed here or in an inner
    query under that name."""
    inner = projection.this if isinstance(projection, exp.Alias) else projection
    return isinstance(inner, exp.Column) and inner.name.lower() not in aliases


def _join(*notes: str) -> str:
    return "; ".join(n for n in notes if n)


def classify(sql: str | None, balance: Balance) -> Classification:
    if not sql or not sql.strip():
        return Classification(NO_SQL)
    tree = _parse(sql)
    if tree is None:
        return Classification(UNCLEAR, note="does not parse")
    if not isinstance(tree, exp.Select):
        return Classification(UNCLEAR, note=f"outermost statement is {tree.key}, not a single SELECT")
    aliases = _aliases(tree)
    # Unscoped resolution merges the definitions of a repeated alias, so the manual check sees them.
    repeated = "; ".join(f"alias defined more than once: {name}"
                         for name, definitions in sorted(aliases.items()) if len(definitions) > 1)
    projections = tree.expressions
    if len(projections) > 1:
        projections = [p for p in projections if not _bare(p, aliases)]
    if len(projections) != 1:
        return Classification(UNCLEAR, note=_join(f"{len(projections)} candidate answer expressions", repeated))
    answer = projections[0]
    index = None
    if not any(isinstance(p, exp.Star) or isinstance(p, exp.Column) and isinstance(p.this, exp.Star)
               for p in tree.expressions):
        index = next(i for i, p in enumerate(tree.expressions) if p is answer)
    expression = answer.this if isinstance(answer, exp.Alias) else answer
    deciding = _columns(expression, aliases)
    for node in tree.find_all(exp.Where, exp.Having, exp.Join):
        condition = node.args.get("on") if isinstance(node, exp.Join) else node
        if condition is not None:
            deciding |= _columns(condition, aliases)
    deciding &= balance.columns
    text = expression.sql(dialect=DIALECT)
    if not deciding:
        return Classification(UNCLEAR, text, note=_join("no balance column decides the answer", repeated),
                              answer_index=index)
    category = READS_WALLETSUM if balance.target in deciding else COMPONENTS_ONLY
    return Classification(category, text, tuple(sorted(deciding)), repeated, index)


def answer_column_equals_gold(record: Mapping, c: Classification, gold, tolerance: float) -> bool | str:
    """Whether the answer expression's column holds the gold value: false when the result is not one
    row, undetermined when there is no single answer expression to read it from."""
    if c.answer_index is None or gold is None:
        return UNDETERMINED
    rows = record.get("executed") or []
    if len(rows) != 1:
        return False
    if len(rows[0]) <= c.answer_index:
        return UNDETERMINED
    return _close(rows[0][c.answer_index], gold, tolerance)


def read_overrides(path: Path) -> dict[str, tuple[str, str]]:
    """normalized SQL -> (category, reason), from the hand-checked overrides file."""
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    overrides = {}
    for row in rows:
        if row["category"] not in CATEGORIES:
            raise ValueError(f"unknown category {row['category']!r} in {path}")
        overrides[normalize_sql(row["normalized_sql"])] = (row["category"], row.get("reason", ""))
    return overrides


def review(records: Iterable[Mapping], questions: Iterable[str], gold: Mapping[str, object],
           balance: Balance, overrides: Mapping[str, tuple[str, str]], tolerance: float) -> list[dict]:
    """One row per answer to a wallet-sum question, in results order."""
    questions = set(questions)
    rows = []
    for r in records:
        if r.get("record") != "answer" or r.get("question_id") not in questions:
            continue
        sql = r.get("final_sql") or ""
        c = classify(sql, balance)
        normalized = normalize_sql(sql)
        category, note = c.category, c.note
        if normalized in overrides:
            category, reason = overrides[normalized]
            note = _join(f"override: {reason}", c.note)
        rows.append({
            "question": r["question_id"], "rule": r["rule"], "run": r["run"],
            "response_class": r["response_class"], "category": category,
            "answer_column_equals_gold": _flag(answer_column_equals_gold(r, c, gold.get(r["question_id"]), tolerance)),
            "answer_expression": c.answer_expression, "deciding_columns": " ".join(c.deciding_columns),
            "final_sql": sql, "note": note, "normalized_sql": normalized,
        })
    return rows


def _flag(value: bool | str) -> str:
    return value if isinstance(value, str) else str(value).lower()


def _outcome(response_class: str) -> str:
    return {"correct_answer": "correct", "wrong_answer": "wrong"}.get(response_class, "other")


def summary_rows(rows: Sequence[Mapping]) -> list[dict]:
    """Correct, wrong and other counts per question and category (every category, zeros included),
    then per question, rule and category (only those that occur), then per question and value of the
    answer-column check (in the category column)."""
    counts = Counter()
    for r in rows:
        outcome = _outcome(r["response_class"])
        counts[("question_category", r["question"], "", r["category"], outcome)] += 1
        counts[("question_rule", r["question"], r["rule"], r["category"], outcome)] += 1
        counts[("question_answer_column", r["question"], "", r["answer_column_equals_gold"], outcome)] += 1
    questions = list(dict.fromkeys(r["question"] for r in rows))
    rules = list(dict.fromkeys(r["rule"] for r in rows))
    keys = [("question_category", q, "", c) for q in questions for c in CATEGORIES]
    keys += [("question_rule", q, rule, c) for q in questions for rule in rules for c in CATEGORIES
             if any(counts[("question_rule", q, rule, c, o)] for o in ("correct", "wrong", "other"))]
    keys += [("question_answer_column", q, "", v) for q in questions for v in ("true", "false", UNDETERMINED)]
    out = []
    for view, question, rule, category in keys:
        n = {o: counts[(view, question, rule, category, o)] for o in ("correct", "wrong", "other")}
        out.append({"view": view, "question": question, "rule": rule, "category": category, **n,
                    "total": sum(n.values())})
    return out


def review_list(rows: Sequence[Mapping]) -> list[dict]:
    """Each distinct normalized SQL once, unclear first, then components only, then walletsum; most
    frequent first within a category. Answers with no SQL are left out."""
    groups: dict[str, list[Mapping]] = {}
    for r in rows:
        if r["category"] != NO_SQL:
            groups.setdefault(r["normalized_sql"], []).append(r)
    entries = []
    for normalized, members in groups.items():
        first = members[0]
        entries.append({
            "category": first["category"], "answer_expression": first["answer_expression"],
            "deciding_columns": first["deciding_columns"], "count": len(members),
            "example_rule": first["rule"], "example_run": first["run"],
            "example_response_class": first["response_class"], "normalized_sql": normalized,
            "note": first["note"],
        })
    return sorted(entries, key=lambda e: (REVIEW_ORDER.index(e["category"]), -e["count"]))


def gold_values(config: Config, questions: Sequence[Question], work_dir: Path) -> dict[str, object]:
    """Each question's gold value on the injected copy, when its gold result is a single value."""
    built = build(list(config.defects), config.databases, work_dir)
    injected = {name: built.copy(content) for name, content in built.injected.items()}
    gold = {}
    for q in questions:
        rows = query(injected[q.database], q.gold_sql)
        if len(rows) == 1 and len(rows[0]) == 1:
            gold[q.id] = rows[0][0]
    return gold


def _write(path: Path, fields: Sequence[str], rows: Iterable[Mapping]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, help="default: manual_overrides.csv in --out-dir")
    parser.add_argument("--work-dir", type=Path, help="where the injected copies are built; default: a temporary directory")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    freeze = yaml.safe_load(args.freeze.read_text())
    balance = balance_columns(freeze)
    tolerance = freeze.get("global", {}).get("numeric_tolerance", TOLERANCE)
    questions = wallet_sum_questions(config)
    with tempfile.TemporaryDirectory() as tmp:
        gold = gold_values(config, questions, args.work_dir or Path(tmp))
    records = [json.loads(line) for line in args.results.read_text().splitlines() if line.strip()]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    overrides_path = args.overrides or args.out_dir / "manual_overrides.csv"
    if not overrides_path.exists():
        _write(overrides_path, OVERRIDE_FIELDS, [])
    rows = review(records, [q.id for q in questions], gold, balance, read_overrides(overrides_path), tolerance)

    _write(args.out_dir / "answers.csv", ANSWER_FIELDS, rows)
    _write(args.out_dir / "summary.csv", SUMMARY_FIELDS, summary_rows(rows))
    _write(args.out_dir / "review_list.csv", REVIEW_FIELDS, review_list(rows))
    per_question = Counter(r["question"] for r in rows)
    print(f"{len(rows)} answers: " + ", ".join(f"{q} {n}" for q, n in per_question.items()))
    print("categories: " + ", ".join(f"{c} {n}" for c, n in Counter(r["category"] for r in rows).most_common()))
    print("answer_column_equals_gold: " + ", ".join(
        f"{v} {n}" for v, n in Counter(r["answer_column_equals_gold"] for r in rows).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
