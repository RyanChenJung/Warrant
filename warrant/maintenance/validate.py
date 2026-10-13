"""Validate the drift tasks a configuration lists: `python -m warrant.maintenance.validate --config <file>`.

A task is valid when each of its gold SQL statements is a read-only query, its two gold results
differ, and its post-drift result is not empty. The run checks the same before any agent call.
"""

import argparse
import sqlite3
from pathlib import Path

from warrant.data.sqlite import query_with_columns
from warrant.maintenance.config import State, Task, load_config
from warrant.scoring.classify import TOLERANCE, Result, results_match


def problems(task: Task, database: Path, tolerance: float = TOLERANCE) -> list[str]:
    """Why a task is not valid; empty when it is.

    Each gold SQL runs on a read-only connection, so one that writes fails instead of changing the
    database. The two gold results are equal when they match as the scorer compares results (sets
    of rows within the tolerance): a stale answer would then be scored correct after drift. A
    result whose every value is NULL, such as a sum over no rows, is empty.
    """
    found = []
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
    post_drift = gold.get(State.POST_DRIFT)
    if post_drift is not None and all(value is None for row in post_drift.rows for value in row):
        found.append("its post-drift result is empty")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check that every drift task a configuration lists is valid.")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    valid = 0
    for task in config.tasks:
        found = problems(task, config.databases[task.database])
        for problem in found:
            print(f"{task.id}: {problem}")
        valid += not found
    print(f"{valid} of {len(config.tasks)} tasks valid")
    return 0 if valid == len(config.tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
