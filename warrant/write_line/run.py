"""The write-line entry point: inject, compute gold answers, compose stores, ask the agent, score.

The tracer bullet (#27) supports two allocation rules, the empty store and everything from a
person; #50 and #51 add the others.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
from warrant.data.sqlite import query, schema
from warrant.defects.inject import Defect, inject
from warrant.scoring.classify import classify
from warrant.store.claims import Claim, KnowledgeStore, Source, Toulmin, WarrantKind
from warrant.write_line.config import Config


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


@dataclass(frozen=True)
class WriteLineResult:
    rows: list[ResultRow]
    accuracy: dict[str, float]
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


def _execute(path: Path, sql: str | None) -> list[tuple] | None:
    if sql is None:
        return None
    try:
        return query(path, sql)
    except sqlite3.Error:
        return None


def run(config: Config, agent: Agent, work_dir: Path) -> WriteLineResult:
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
                executed = _execute(path, response.final_sql) if response.kind == ResponseKind.ANSWER else None
                rows.append(
                    ResultRow(
                        question_id=q.id,
                        rule=rule,
                        run=run_index,
                        response_class=classify(response, executed, gold[q.id].rows),
                        final_sql=response.final_sql,
                        executed=executed,
                        usage=output.usage,
                    )
                )

    accuracy = {
        rule: sum(r.response_class == "correct" for r in rows if r.rule == rule) / sum(r.rule == rule for r in rows)
        for rule in config.rules
    }
    return WriteLineResult(rows=rows, accuracy=accuracy, gold=gold, stores=stores, injected=injected)
