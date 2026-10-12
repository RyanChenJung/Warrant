"""The write-line entry point: inject, compute gold answers, compose stores, ask the agent, score.

The tracer bullet (#27) supports two allocation rules, the empty store and everything from a
person; #50 and #51 add the others.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from warrant.agent.claude import ClaudeAgent
from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
from warrant.config import data_dir
from warrant.data.sqlite import query, schema
from warrant.defects.inject import Defect, inject
from warrant.scoring.classify import classify
from warrant.store.claims import Claim, KnowledgeStore, Source, Toulmin, WarrantKind
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.config import Config, load_config

FAILED = "failed"


@dataclass(frozen=True)
class GoldAnswer:
    question_id: str
    sql: str
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


@dataclass(frozen=True)
class WriteLineResult:
    rows: list[ResultRow]
    accuracy: dict[str, float | None]
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


def _accuracy(rows: list[ResultRow]) -> float | None:
    """Correct answers over the rows that were scored. None when every call failed."""
    scored = [r for r in rows if r.response_class != FAILED]
    if not scored:
        return None
    return sum(r.response_class == "correct" for r in scored) / len(scored)


def _record(row: ResultRow) -> dict:
    return {
        "question_id": row.question_id,
        "rule": row.rule,
        "run": row.run,
        "response_class": row.response_class,
        "final_sql": row.final_sql,
        "input_tokens": row.usage.input_tokens,
        "output_tokens": row.usage.output_tokens,
        "failure": row.failure,
    }


def _execute(path: Path, sql: str | None) -> list[tuple] | None:
    if sql is None:
        return None
    try:
        return query(path, sql)
    except sqlite3.Error:
        return None


def run(
    config: Config,
    agent: Agent,
    work_dir: Path,
    provenance: Provenance | None = None,
    results: Path | None = None,
) -> WriteLineResult:
    injected = {
        name: inject(clean, work_dir / f"{name}.sqlite", [d for d in config.defects if d.database == name])
        for name, clean in config.databases.items()
    }
    gold = {q.id: GoldAnswer(q.id, q.gold_sql, query(injected[q.database], q.gold_sql)) for q in config.questions}
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
                row = ResultRow(
                    question_id=q.id,
                    rule=rule,
                    run=run_index,
                    # A failed call is recorded, not scored: it is neither a correct nor a wrong
                    # answer, and it stays out of the accuracy below.
                    response_class=FAILED if output.failure else classify(response, executed, gold[q.id].rows),
                    final_sql=None if response is None else response.final_sql,
                    executed=executed,
                    usage=output.usage,
                    failure=output.failure,
                )
                rows.append(row)
                if results is not None and provenance is not None:
                    append(results, provenance, _record(row))

    accuracy = {rule: _accuracy([r for r in rows if r.rule == rule]) for rule in config.rules}
    return WriteLineResult(rows=rows, accuracy=accuracy, gold=gold, stores=stores, injected=injected)


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
    failed = sum(row.response_class == FAILED for row in result.rows)
    print(f"{len(result.rows)} results, {failed} failed calls, written to {args.results}")
    for rule, accuracy in result.accuracy.items():
        print(f"  {rule}: {'no scored call' if accuracy is None else f'{accuracy:.3f}'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
