"""The maintenance-line configuration and its drift task files, read from YAML.

See `tests/fixtures/maintenance/` for a configuration and a documented task file. Task files are
team-written and committed in this repo under CC BY-SA 4.0.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class State(StrEnum):
    """A drift task's two states: before drift, its no-drift control, and after drift."""

    PRE_DRIFT = "pre_drift"
    POST_DRIFT = "post_drift"


class DriftType(StrEnum):
    """All of part (1)'s drift is convention drift: documented when the knowledge-base entry gets a
    new version, undocumented when it is removed or marked under revision (#44)."""

    DOCUMENTED = "documented"
    UNDOCUMENTED = "undocumented"


@dataclass(frozen=True)
class TaskEntry:
    """A knowledge-base entry a task depends on, by its id in the database's knowledge base."""

    id: int
    # The oracle person's current definition of the entry: what it answers when asked after drift.
    oracle_definition: str
    # The pre-drift value copied from the old entry, without its source or version. Supplied by the
    # task file until #45 builds stored answers.
    stored_answer: str | None = None


@dataclass(frozen=True)
class TaskState:
    # The task's entries as this state's knowledge base has them: the release's fields plus the
    # entry's version.
    knowledge_base: tuple[dict[str, Any], ...]
    gold_sql: str


@dataclass(frozen=True)
class Task:
    id: str
    database: str
    question: str
    drift_type: DriftType
    entries: tuple[TaskEntry, ...]
    states: dict[State, TaskState]


def load_task(path: Path) -> Task:
    raw = yaml.safe_load(Path(path).read_text())
    return Task(
        id=raw["id"],
        database=raw["database"],
        question=raw["question"],
        drift_type=DriftType(raw["drift_type"]),
        entries=tuple(TaskEntry(e["id"], e["oracle_definition"], e.get("stored_answer")) for e in raw["entries"]),
        states={
            state: TaskState(tuple(raw[state]["knowledge_base"]), raw[state]["gold_sql"]) for state in State
        },
    )


@dataclass(frozen=True)
class Config:
    databases: dict[str, Path]
    # Each database's knowledge base as released (`<db>_kb.jsonl`).
    knowledge_bases: dict[str, Path]
    tasks: tuple[Task, ...]
    conditions: tuple[str, ...]
    runs: int


def load_config(path: Path) -> Config:
    """Read a configuration and the task files it lists; paths are relative to the configuration.

    A task is known by its id, so two task files with one id are refused.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text())

    def resolve(relative: str) -> Path:
        return (path.parent / relative).resolve()

    tasks = tuple(load_task(resolve(task)) for task in raw["tasks"])
    ids = [task.id for task in tasks]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ValueError(f"{path}: task ids used more than once: {', '.join(repeated)}")
    return Config(
        databases={name: resolve(db) for name, db in raw["databases"].items()},
        knowledge_bases={name: resolve(kb) for name, kb in raw["knowledge_bases"].items()},
        tasks=tasks,
        conditions=tuple(raw["conditions"]),
        runs=int(raw["runs"]),
    )
