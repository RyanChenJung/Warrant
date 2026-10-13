"""The maintenance-line entry point: expand each drift task into its two states, ask the agent under
each condition, and score every answer against the gold result of its state.

A condition is the knowledge store and the tool set the agent receives, and nothing else: the
request record never names the condition or the state. The tracer bullet (#42) has the two
conditions that need no new tools, the full knowledge base in the prompt and the stored answer
without tools; #45 adds the others.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
from warrant.data.release import read_knowledge_base
from warrant.data.sqlite import query_with_columns, schema
from warrant.maintenance.config import Config, State, Task
from warrant.maintenance.validate import problems
from warrant.scoring.classify import (
    TOLERANCE,
    Bucket,
    ResponseClass,
    Result,
    Score,
    accuracy,
    execute,
    is_silent_error,
    is_stale_value,
    score,
)
from warrant.store.claims import Claim, ClaimKind, KnowledgeStore, Slot, Source, Toulmin, WarrantKind
from warrant.store.results import Provenance, append

FULL_KNOWLEDGE_BASE = "full_knowledge_base"
STORED_ANSWER_WITHOUT_TOOLS = "stored_answer_without_tools"

# Each condition's tool set; `compose` gives its knowledge store.
TOOLS = {
    FULL_KNOWLEDGE_BASE: (ReadOnlySQL.name,),
    # The agent writes SQL without running it; the pipeline runs it.
    STORED_ANSWER_WITHOUT_TOOLS: (),
}

# The claim kind whose slot each kind of entry in the release's knowledge bases fills.
CLAIM_KINDS = {
    "calculation_knowledge": ClaimKind.COLUMN_FORMULA,
    "domain_knowledge": ClaimKind.TERM_BOUNDARY,
    "value_illustration": ClaimKind.VALUE_MEANING,
}

Entry = dict[str, Any]


@dataclass(frozen=True)
class ResultRow:
    task: str
    condition: str
    state: State
    run: int
    response_class: str
    final_sql: str | None
    executed: list[tuple] | None
    usage: Usage
    stale_value: bool
    silent_error: bool
    failure: str = ""
    bucket: Bucket | None = None


@dataclass(frozen=True)
class MaintenanceResult:
    rows: list[ResultRow]
    # Per condition and state.
    accuracy: dict[tuple[str, State], float | None]
    # Per condition and state, the share of scored runs whose answer is a stale value, failed calls
    # left out; before drift no answer is one. None when no run was scored.
    stale_value_rate: dict[tuple[str, State], float | None]


def _slot(entry: Entry) -> Slot:
    return Slot(CLAIM_KINDS[entry["type"]], entry["knowledge"])


def _record_claim(entry: Entry) -> Claim:
    """A knowledge-base entry as a claim. The knowledge base is treated as the authoritative record,
    so the claim carries a record warrant tied to the entry's version."""
    return Claim(
        slot=_slot(entry),
        statement=" ".join(part for part in (entry.get("description"), entry["definition"]) if part),
        source=Source.PERSON,
        warrant=WarrantKind.RECORD,
        toulmin=Toulmin(backing=f"knowledge base entry {entry['id']}, version {entry['version']}"),
    )


def compose(condition: str, task: Task, state: State, released: list[Entry]) -> KnowledgeStore:
    """The knowledge store a condition shows in one state of a task.

    `released` is the database's knowledge base as released. In the full knowledge base, an entry
    the task depends on is the state's version of it; every other entry keeps its release text, as
    version 1.
    """
    if condition == FULL_KNOWLEDGE_BASE:
        current = {e["id"]: {**e, "version": 1} for e in released} | {
            e["id"]: e for e in task.states[state].knowledge_base
        }
        return KnowledgeStore(tuple(_record_claim(e) for e in current.values()))
    if condition == STORED_ANSWER_WITHOUT_TOOLS:
        # The same store in both states: the pre-drift value, with no warrant, source or version,
        # so nothing in it can tell when it becomes false.
        before = {e["id"]: e for e in task.states[State.PRE_DRIFT].knowledge_base}
        missing = [entry.id for entry in task.entries if entry.stored_answer is None]
        if missing:
            raise ValueError(f"task {task.id!r}: no stored answer for entries {missing}")
        return KnowledgeStore(
            tuple(
                Claim(_slot(before[entry.id]), entry.stored_answer, Source.AGENT, WarrantKind.NONE, Toulmin())
                for entry in task.entries
            )
        )
    raise ValueError(f"unknown condition: {condition!r}")


def _share(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _record(row: ResultRow) -> dict:
    return {
        "task": row.task,
        "condition": row.condition,
        "state": row.state,
        "run": row.run,
        "response_class": row.response_class,
        "bucket": row.bucket,
        "final_sql": row.final_sql,
        "stale_value": row.stale_value,
        "silent_error": row.silent_error,
        # The statistics (#41) read each run's escalation calls; none until #39 adds the tool.
        "escalations": 0,
        "input_tokens": row.usage.input_tokens,
        "output_tokens": row.usage.output_tokens,
        "failure": row.failure,
    }


def run(
    config: Config,
    agent: Agent,
    provenance: Provenance | None = None,
    results: Path | None = None,
    *,
    tolerance: float = TOLERANCE,
) -> MaintenanceResult:
    """Ask every task in both states under every condition `config.runs` times and score the answers.

    The tolerance belongs to the global part of the freeze (#33); until it is wired in, the default
    is the spec's.
    """
    rejected = [
        f"{task.id} ({problem})"
        for task in config.tasks
        for problem in problems(task, config.databases[task.database], tolerance)
    ]
    if rejected:
        raise ValueError("tasks the run cannot score: " + "; ".join(rejected))
    released = {name: read_knowledge_base(path) for name, path in config.knowledge_bases.items()}
    stores = {
        (task.id, condition, state): compose(condition, task, state, released[task.database])
        for task in config.tasks
        for condition in config.conditions
        for state in State
    }
    gold = {
        (task.id, state): Result(*query_with_columns(config.databases[task.database], task.states[state].gold_sql))
        for task in config.tasks
        for state in State
    }

    rows = []
    for run_index in range(config.runs):
        for condition in config.conditions:
            for task in config.tasks:
                path = config.databases[task.database]
                bound = {ReadOnlySQL.name: ReadOnlySQL(path)}
                for state in State:
                    request = AnswerRequest(
                        database=task.database,
                        question_id=task.id,
                        question=task.question,
                        run=run_index,
                        schema=schema(path),
                        store=stores[(task.id, condition, state)],
                        tools=TOOLS[condition],
                    )
                    output = agent.answer(request, {name: bound[name] for name in request.tools})
                    response = output.response
                    executed = (
                        execute(path, response.final_sql)
                        if response is not None and response.kind == ResponseKind.ANSWER
                        else None
                    )
                    expected = gold[(task.id, state)]
                    # A failed call is recorded, not scored.
                    scored = (
                        Score(ResponseClass.FAILED)
                        if output.failure
                        else score(response, executed, expected, tolerance=tolerance)
                    )
                    row = ResultRow(
                        task=task.id,
                        condition=condition,
                        state=state,
                        run=run_index,
                        response_class=scored.response_class,
                        final_sql=None if response is None else response.final_sql,
                        executed=None if executed is None else executed.rows,
                        usage=output.usage,
                        stale_value=state == State.POST_DRIFT
                        and is_stale_value(executed, gold[(task.id, State.PRE_DRIFT)], expected, tolerance),
                        # No escalation tool is offered until #39, so no run has an escalation.
                        silent_error=is_silent_error(scored, executed, escalations=0),
                        failure=output.failure,
                        bucket=scored.bucket,
                    )
                    rows.append(row)
                    if results is not None and provenance is not None:
                        append(results, provenance, _record(row))

    cells = {(condition, state): [] for condition in config.conditions for state in State}
    for row in rows:
        cells[(row.condition, row.state)].append(row)
    return MaintenanceResult(
        rows=rows,
        accuracy={cell: accuracy(r.response_class for r in in_cell) for cell, in_cell in cells.items()},
        stale_value_rate={
            cell: _share([r.stale_value for r in in_cell if r.response_class != ResponseClass.FAILED])
            for cell, in_cell in cells.items()
        },
    )
