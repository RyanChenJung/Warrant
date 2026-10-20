"""The write-line entry point: build the reading databases, predict, compute gold answers, compose
stores, ask the agent, score. With `stop_after_prediction` it returns before any agent call (#37).

The tracer bullet (#27) supports two allocation rules, the empty store and everything from a
person; #50 and #51 add the others.
"""

import argparse
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from warrant.agent.claude import ClaudeAgent
from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
from warrant.config import data_dir
from warrant.data.sqlite import query, query_with_columns, schema
from warrant.defects.audit import Audit
from warrant.defects.build import Built, build
from warrant.defects.inject import Defect
from warrant.scoring.classify import (
    TOLERANCE,
    Bucket,
    RefusalCheck,
    ResponseClass,
    Result,
    Score,
    accuracy,
    execute,
    flips,
    results_match,
    rule_based_refusal_check,
    score,
)
from warrant.store.claims import Claim, KnowledgeStore, Source, Toulmin, WarrantKind
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.config import Config, Question, load_config
from warrant.write_line.predict import BatterySettings, Predictions, predict


@dataclass(frozen=True)
class GoldAnswer:
    question_id: str
    sql: str
    columns: tuple[str, ...]
    rows: list[tuple]


@dataclass(frozen=True)
class ResultRow:
    question_id: str
    rule: str
    run: int
    response_class: str
    final_sql: str | None
    executed: list[tuple] | None
    usage: Usage
    failure: str = ""
    bucket: Bucket | None = None
    executed_columns: tuple[str, ...] | None = None
    # What the response said, beside its final SQL: the stated value; the answer's self-reported
    # confidence, not the slot confidence the confidence rule ranks by (#51); for a refusal, what it
    # says is missing and what it offers instead; and a clarification request's question. None or
    # empty for a failed call.
    value: Any = None
    confidence: float | None = None
    missing: str = ""
    alternative: str = ""
    clarification: str = ""


@dataclass(frozen=True)
class WriteLineResult:
    rows: list[ResultRow]
    accuracy: dict[str, float | None]
    # Per rule, how many responses fell in each response class, clarification requests and
    # failures included.
    counts: dict[str, Counter[str]]
    # Per question and rule, whether its scored runs do not all share one response class; None
    # when fewer than two runs were scored.
    flips: dict[tuple[str, str], bool | None]
    gold: dict[str, GoldAnswer]
    stores: dict[str, KnowledgeStore]
    injected: dict[str, Path]
    # Per defect, what its transformation did to the injected copy (#35).
    audits: dict[str, Audit]
    # The predicted outcomes (#37), when a defect has a reading set.
    predictions: Predictions | None = None


def _person_claim(defect: Defect) -> Claim:
    # No battery runs yet, so the warrant kind is a placeholder until #50 computes it.
    return Claim(
        slot=defect.slot,
        statement=defect.reference_claim,
        source=Source.PERSON,
        warrant=WarrantKind.NONE,
        toulmin=Toulmin(backing="the person"),
    )


def compose(rule: str, defects: tuple[Defect, ...]) -> KnowledgeStore:
    if rule == "empty":
        return KnowledgeStore()
    if rule == "all_person":
        return KnowledgeStore(tuple(_person_claim(d) for d in defects))
    raise ValueError(f"unknown allocation rule: {rule!r}")


def _record(row: ResultRow) -> dict:
    return {
        "question_id": row.question_id,
        "rule": row.rule,
        "run": row.run,
        "response_class": row.response_class,
        "bucket": row.bucket,
        "final_sql": row.final_sql,
        # The executed result is stored with its score, so each answer's value can be audited, and its
        # score recomputed from the gold answer, without re-executing its final SQL (#49).
        "executed": row.executed,
        "executed_columns": row.executed_columns,
        "value": row.value,
        "confidence": row.confidence,
        "missing": row.missing,
        "alternative": row.alternative,
        "clarification": row.clarification,
        "input_tokens": row.usage.input_tokens,
        "output_tokens": row.usage.output_tokens,
        "failure": row.failure,
    }


# A probe's answers under the readings it separates differ from its gold answer by more than this
# share, or are different sets (#34, round 2).
SEPARATION = 0.02


def _unseparated(q: Question, defect: Defect | None, injected: Path, gold: GoldAnswer) -> list[str]:
    """Why a probe of a defect with a reading set does not separate the readings it names."""
    if defect is None or not defect.readings:
        return []
    if not q.separates:
        return [f"{q.id} (a probe of {defect.id}, which has a reading set, names no reading it separates)"]
    readings = {r["id"]: r for r in defect.readings}
    expected = Result(gold.columns, gold.rows)
    found = []
    for reading, sql in q.separates:
        if reading not in readings:
            found.append(f"{q.id} ({reading!r} is not a reading of {defect.id})")
        elif readings[reading].get("is_true"):
            found.append(f"{q.id} ({reading!r} is the true reading)")
        else:
            try:
                answer = Result(*query_with_columns(injected, sql))
            except sqlite3.Error as error:
                found.append(f"{q.id} (its SQL for reading {reading!r} fails: {error})")
                continue
            if results_match(answer, expected, key=q.key, tolerance=SEPARATION):
                found.append(f"{q.id} (its answer is within 2 percent of the gold answer under reading {reading!r})")
    return found


def _rejected(config: Config, gold: dict[str, GoldAnswer], injected: dict[str, Path]) -> list[str]:
    """Each question the run could not score as configured, and why; checked before any agent call."""
    defects = {d.id: d for d in config.defects}
    rejected = []
    for q in config.questions:
        if q.id not in gold:  # its correct response is a refusal
            continue
        g = gold[q.id]
        if q.defect is None and Counter(query(config.databases[q.database], q.gold_sql)) != Counter(g.rows):
            rejected.append(f"{q.id} (a control question whose gold answer differs between clean and injected copy)")
        # A set answer is compared on its key values, so it needs a key its gold result has.
        if len(g.rows) > 1 and not q.key:
            rejected.append(f"{q.id} (a set answer with no key)")
        columns = {column.casefold() for column in g.columns}
        if any(column.casefold() not in columns for column in q.key):
            rejected.append(f"{q.id} (a key column its gold result does not have)")
        rejected += _unseparated(q, defects.get(q.defect), injected[q.database], g)
    return rejected


def _same_as_recorded(built: Built, record: dict) -> None:
    """Refuse databases that are not the recorded injection's: the builder is deterministic, so a
    rebuild on any machine gives the recorded content hashes, and a run on other databases is not a
    run on the injected copy (#49)."""
    differ = [
        f"the injected copy of {name!r}"
        for name in sorted(built.injected.keys() | record["injected"].keys())
        if built.injected.get(name) != record["injected"].get(name)
    ]
    readings = {(d, r) for d, rs in built.readings.items() for r in rs} | {
        (d, r) for d, rs in record["readings"].items() for r in rs
    }
    differ += [
        f"reading {r!r} of {d!r}"
        for d, r in sorted(readings)
        if built.readings.get(d, {}).get(r) != record["readings"].get(d, {}).get(r)
    ]
    if differ:
        raise ValueError("the databases built for this run are not the recorded injection's: " + ", ".join(differ))


def run(
    config: Config,
    agent: Agent,
    work_dir: Path,
    provenance: Provenance | None = None,
    results: Path | None = None,
    *,
    tolerance: float | None = None,
    refusal_check: RefusalCheck = rule_based_refusal_check,
    stop_after_prediction: bool = False,
) -> WriteLineResult:
    """Ask every question under every rule `config.runs` times and score the responses.

    Without a `tolerance`, answers are scored with the global part's numeric_tolerance when the
    configuration has one, else the scorer's default; the refusal check is the frozen rule's. When the
    configuration names an injection record, the databases built here must be that injection's, copy
    for copy by content hash, or the run stops before any agent call. When a defect has a reading
    set, the predicted outcomes are computed first, from the global part's battery settings, and with
    `stop_after_prediction` the run returns them before any agent call.
    """
    if tolerance is None:
        tolerance = (config.global_part or {}).get("numeric_tolerance", TOLERANCE)
    built = build(list(config.defects), config.databases, work_dir)
    if config.injection is not None:
        _same_as_recorded(built, config.injection)
    injected = {name: built.copy(content) for name, content in built.injected.items()}
    audits = {a.defect: a for a in built.audits}
    predictions = None
    if any(d.readings for d in config.defects):
        if config.global_part is None:
            raise ValueError("defects with reading sets need the global part's battery settings to predict")
        settings = BatterySettings.from_freeze({"global": config.global_part})
        predictions = predict(config.defects, built, config.databases, settings, work_dir / "battery")
    if stop_after_prediction:
        if predictions is None:
            raise ValueError("no defect has a reading set, so there is nothing to predict")
        return WriteLineResult([], {}, {}, {}, {}, {}, injected, audits, predictions)
    # A question whose correct response is a refusal has no gold answer.
    gold = {
        q.id: GoldAnswer(q.id, q.gold_sql, *query_with_columns(injected[q.database], q.gold_sql))
        for q in config.questions
        if q.gold_sql is not None
    }
    rejected = _rejected(config, gold, injected)
    if rejected:
        raise ValueError("questions the run cannot score: " + "; ".join(rejected))
    expected = {question_id: Result(g.columns, g.rows) for question_id, g in gold.items()}
    stores = {rule: compose(rule, config.defects) for rule in config.rules}

    rows = []
    for run_index in range(config.runs):
        for rule in config.rules:
            for q in config.questions:
                path = injected[q.database]
                request = AnswerRequest(
                    database=q.database,
                    question_id=q.id,
                    question=q.text,
                    run=run_index,
                    schema=schema(path),
                    store=stores[rule],
                    tools=(ReadOnlySQL.name,),
                )
                output = agent.answer(request, {ReadOnlySQL.name: ReadOnlySQL(path)})
                response = output.response
                executed = (
                    execute(path, response.final_sql)
                    if response is not None and response.kind == ResponseKind.ANSWER
                    else None
                )
                # A failed call is recorded, not scored: it is neither a correct nor a wrong
                # answer, and it stays out of the accuracy below.
                scored = (
                    Score(ResponseClass.FAILED)
                    if output.failure
                    else score(
                        response,
                        executed,
                        expected.get(q.id),
                        key=q.key,
                        missing_terms=q.missing_terms,
                        tolerance=tolerance,
                        refusal_check=refusal_check,
                    )
                )
                row = ResultRow(
                    question_id=q.id,
                    rule=rule,
                    run=run_index,
                    response_class=scored.response_class,
                    final_sql=None if response is None else response.final_sql,
                    executed=None if executed is None else executed.rows,
                    usage=output.usage,
                    failure=output.failure,
                    bucket=scored.bucket,
                    executed_columns=None if executed is None else executed.columns,
                    value=None if response is None else response.value,
                    confidence=None if response is None else response.confidence,
                    missing="" if response is None else response.missing,
                    alternative="" if response is None else response.alternative,
                    clarification="" if response is None else response.clarification,
                )
                rows.append(row)
                if results is not None and provenance is not None:
                    append(results, provenance, _record(row))

    by_rule = {rule: [r for r in rows if r.rule == rule] for rule in config.rules}
    return WriteLineResult(
        rows=rows,
        accuracy={rule: accuracy(r.response_class for r in by_rule[rule]) for rule in config.rules},
        counts={rule: Counter(r.response_class for r in by_rule[rule]) for rule in config.rules},
        flips={
            (q.id, rule): flips(r.response_class for r in by_rule[rule] if r.question_id == q.id)
            for q in config.questions
            for rule in config.rules
        },
        gold=gold,
        stores=stores,
        injected=injected,
        audits=audits,
        predictions=predictions,
    )


def check(config: Config, work_dir: Path) -> int:
    """Print each question's gold answer, a control's gold answer on the clean copy too, and each
    probe's answers under the readings it separates, then every problem the run would stop on; no
    agent is called."""
    built = build(list(config.defects), config.databases, work_dir)
    if config.injection is not None:
        _same_as_recorded(built, config.injection)
    injected = {name: built.copy(content) for name, content in built.injected.items()}
    gold = {}
    for q in config.questions:
        if q.gold_sql is None:
            print(f"{q.id}: a refusal question")
            continue
        gold[q.id] = GoldAnswer(q.id, q.gold_sql, *query_with_columns(injected[q.database], q.gold_sql))
        print(f"{q.id}: gold: {gold[q.id].rows}")
        if q.defect is None:  # a control's gold answer must be the same on the clean copy
            print(f"  clean copy: {query(config.databases[q.database], q.gold_sql)}")
        for reading, sql in q.separates:
            try:
                print(f"  {reading}: {query_with_columns(injected[q.database], sql)[1]}")
            except sqlite3.Error as error:
                print(f"  {reading}: fails ({error})")
    problems = _rejected(config, gold, injected)
    for problem in problems:
        print(f"problem: {problem}")
    print(f"{len(problems)} problems")
    return 1 if problems else 0


def main(argv=None) -> int:
    """Run one configuration against the configured model: `python -m warrant.write_line.run`."""
    parser = argparse.ArgumentParser(description="Run the write line against the configured model.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path, default=data_dir() / "write_line")
    parser.add_argument("--results", type=Path, default=data_dir() / "results.jsonl")
    parser.add_argument("--check", action="store_true",
                        help="check the questions and print their answers, with no agent call")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.check:
        return check(config, args.work_dir)
    if config.model is None:
        parser.error(f"{args.config} names no model block")
    try:
        agent = ClaudeAgent(config.model)
    except ValueError as error:
        parser.error(f"{args.config}: {error}")  # a misconfiguration, before any question is asked
    result = run(
        config,
        agent,
        args.work_dir,
        provenance_for(args.config, config.model),
        args.results,
    )
    failed = sum(row.response_class == ResponseClass.FAILED for row in result.rows)
    print(f"{len(result.rows)} results, {failed} failed calls, written to {args.results}")
    for rule, rule_accuracy in result.accuracy.items():
        counts = result.counts[rule]
        print(
            f"  {rule}: {'no counted response' if rule_accuracy is None else f'{rule_accuracy:.3f}'}, "
            f"{counts[ResponseClass.CLARIFICATION_REQUEST]} clarification requests, "
            f"{counts[ResponseClass.FAILED]} failed calls"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
