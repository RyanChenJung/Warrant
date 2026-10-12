"""The write-line entry point: inject, compute gold answers, compose stores, ask the agent, score.

The tracer bullet (#27) supports two allocation rules, the empty store and everything from a
person; #50 and #51 add the others.
"""

import argparse
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from warrant.agent.claude import ClaudeAgent
from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
from warrant.config import data_dir
from warrant.data.sqlite import query, query_with_columns, schema
from warrant.defects.inject import Defect, inject
from warrant.scoring.classify import (
    TOLERANCE,
    Bucket,
    RefusalCheck,
    ResponseClass,
    Result,
    Score,
    accuracy,
    flips,
    rule_based_refusal_check,
    score,
)
from warrant.store.claims import Claim, KnowledgeStore, Source, Toulmin, WarrantKind
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.config import Config, load_config


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
        "input_tokens": row.usage.input_tokens,
        "output_tokens": row.usage.output_tokens,
        "failure": row.failure,
    }


def _rejected(config: Config, gold: dict[str, GoldAnswer]) -> list[str]:
    """Each question the run could not score as configured, and why; checked before any agent call."""
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
    return rejected


def _execute(path: Path, sql: str | None) -> Result | None:
    if sql is None:
        return None
    try:
        return Result(*query_with_columns(path, sql))
    except sqlite3.Error:
        return None


def run(
    config: Config,
    agent: Agent,
    work_dir: Path,
    provenance: Provenance | None = None,
    results: Path | None = None,
    *,
    tolerance: float = TOLERANCE,
    refusal_check: RefusalCheck = rule_based_refusal_check,
) -> WriteLineResult:
    """Ask every question under every rule `config.runs` times and score the responses.

    The tolerance and the refusal check belong to the global part of the freeze (#33), which will
    supply them; until then the defaults are the spec's.
    """
    injected = {
        name: inject(clean, work_dir / f"{name}.sqlite", [d for d in config.defects if d.database == name])
        for name, clean in config.databases.items()
    }
    # A question whose correct response is a refusal has no gold answer.
    gold = {
        q.id: GoldAnswer(q.id, q.gold_sql, *query_with_columns(injected[q.database], q.gold_sql))
        for q in config.questions
        if q.gold_sql is not None
    }
    rejected = _rejected(config, gold)
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
                    _execute(path, response.final_sql)
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
    )


def main(argv=None) -> int:
    """Run one configuration against the configured model: `python -m warrant.write_line.run`."""
    parser = argparse.ArgumentParser(description="Run the write line against the configured model.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path, default=data_dir() / "write_line")
    parser.add_argument("--results", type=Path, default=data_dir() / "results.jsonl")
    args = parser.parse_args(argv)

    config = load_config(args.config)
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
