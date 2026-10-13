"""Validate the drift tasks a configuration lists: `python -m warrant.maintenance.validate --config <file>`.

A task is valid when each of its gold SQL statements is a read-only query, its two gold results
differ, and its post-drift result is not empty. Each of its knowledge-base views must also hold
exactly its entries. The run checks the same before any agent call.
"""

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from warrant.data.release import read_knowledge_base
from warrant.data.sqlite import query_with_columns
from warrant.maintenance.config import DriftType, State, Task, load_config
from warrant.scoring.classify import TOLERANCE, Result, results_match


def _structure(task: Task, knowledge_base: list[dict[str, Any]]) -> list[str]:
    """Why the task's views cannot show its entries as the full knowledge base needs them.

    The full knowledge base takes each of the task's entries from the state's view and every other
    entry from the release, so a view that leaves out one of the task's entries would show its
    release text, and an entry outside the task in one of their slots would keep its old text
    beside the new one.
    """
    found = []
    if task.drift_type == DriftType.UNDOCUMENTED:
        found.append(
            "undocumented drift is not supported yet: a knowledge-base view cannot mark an entry removed "
            "or under revision"
        )
    ids = sorted(entry.id for entry in task.entries)
    for state in State:
        listed = sorted(e["id"] for e in task.states[state].knowledge_base)
        if listed != ids:
            found.append(f"its {state} knowledge-base view lists entries {listed}, not its entries {ids}")
    released = {e["id"]: e for e in knowledge_base}
    slots = {}
    for i in ids:
        if i in released:
            slots[(released[i]["type"], released[i]["knowledge"])] = i
        else:
            found.append(f"entry {i} is not in the {task.database} knowledge base")
    for e in knowledge_base:
        slot = (e["type"], e["knowledge"])
        if e["id"] not in ids and slot in slots:
            found.append(
                f"knowledge-base entry {e['id']} is in the slot of entry {slots[slot]} but is not one of its entries"
            )
    return found


def _empty(result: Result) -> bool:
    """No rows, or a column NULL in every row, such as a sum over no rows, per group or not."""
    rows = result.rows
    return not rows or any(all(row[i] is None for row in rows) for i in range(len(result.columns)))


def problems(
    task: Task, database: Path, knowledge_base: list[dict[str, Any]], tolerance: float = TOLERANCE
) -> list[str]:
    """Why a task is not valid; empty when it is. `knowledge_base` is the database's as released.

    Each gold SQL runs on a read-only connection, so one that writes fails instead of changing the
    database. The two gold results are equal when they match as the scorer compares results (sets
    of rows within the tolerance): a stale answer would then be scored correct after drift.
    """
    found = _structure(task, knowledge_base)
    gold = {}
    for state in State:
        try:
            columns, rows = query_with_columns(database, task.states[state].gold_sql)
        except sqlite3.Error as error:
            found.append(f"the {state} gold SQL is not a read-only query: {error}")
            continue
        if not columns:  # a statement that returns no result, such as creating a temporary table
            found.append(f"the {state} gold SQL is not a read-only query: it returns no result")
            continue
        gold[state] = Result(columns, rows)
    if len(gold) == len(State) and results_match(gold[State.PRE_DRIFT], gold[State.POST_DRIFT], tolerance=tolerance):
        found.append("its two gold results are equal")
    if State.POST_DRIFT in gold and _empty(gold[State.POST_DRIFT]):
        found.append("its post-drift result is empty")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check that every drift task a configuration lists is valid.")
    parser.add_argument("--config", required=True, type=Path)
    # The run's tolerance, so that the command and the run judge "equal gold results" alike.
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ValueError as error:
        parser.error(str(error))
    valid = 0
    for task in config.tasks:
        knowledge_base = read_knowledge_base(config.knowledge_bases[task.database])
        found = problems(task, config.databases[task.database], knowledge_base, args.tolerance)
        for problem in found:
            print(f"{task.id}: {problem}")
        valid += not found
    print(f"{valid} of {len(config.tasks)} tasks valid")
    return 0 if valid == len(config.tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
