"""The scorer both lines share (#40): a response class for every response, a bucket for a wrong one.

The numeric tolerance and the refusal check belong to the global part of the freeze (#33). Until it
is wired in they are parameters, with the spec's values as defaults.
"""

import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from warrant.agent.interface import Response, ResponseKind
from warrant.data.sqlite import query_with_columns

# A numeric answer is correct when its relative error is below this.
TOLERANCE = 0.05
# Numbers closer than this are equal: two formulations of the same value differ by floating-point
# noise, which around zero no relative tolerance absorbs.
FLOAT_NOISE = 1e-9


class ResponseClass(StrEnum):
    CORRECT_ANSWER = "correct_answer"
    CORRECT_REFUSAL = "correct_refusal"
    CLARIFICATION_REQUEST = "clarification_request"
    WRONG_ANSWER = "wrong_answer"
    OVER_REFUSAL = "over_refusal"
    # A failed call is recorded, not scored: neither right nor wrong, and left out of accuracy.
    FAILED = "failed"


class Bucket(StrEnum):
    """What kind of wrong answer it is: how far off a single number is, or what went wrong with a
    question whose correct response is a refusal. Any other wrong answer has no bucket."""

    # Outside the tolerance but within 5 percent: at the default tolerance, only exactly 5 percent.
    WITHIN_5_PERCENT = "within_5_percent"
    WITHIN_FACTOR_2 = "within_factor_2"
    BEYOND_FACTOR_2 = "beyond_factor_2"
    SIGN_OR_ZERO_MISMATCH = "sign_or_zero_mismatch"
    INADEQUATE_REFUSAL = "inadequate_refusal"
    ANSWERED_UNANSWERABLE = "answered_unanswerable"


@dataclass(frozen=True)
class Result:
    """An executed or gold result: its column names and its rows."""

    columns: tuple[str, ...]
    rows: list[tuple]


def execute(path: Path, sql: str | None) -> Result | None:
    """The result of re-executing an answer's final SQL on the database it named, read-only; None
    when there is no SQL, it fails, or it is not a query (it returns no result, as a comment or a
    temporary table does)."""
    if sql is None:
        return None
    try:
        columns, rows = query_with_columns(path, sql)
    except sqlite3.Error:
        return None
    return Result(columns, rows) if columns else None


@dataclass(frozen=True)
class Score:
    response_class: ResponseClass
    bucket: Bucket | None = None


RefusalCheck = Callable[[Response, tuple[str, ...]], bool]


def rule_based_refusal_check(response: Response, missing_terms: tuple[str, ...]) -> bool:
    """The missing-piece field contains at least one recorded term, and the alternative is not empty.

    A term counts where a word starts: "rates" names "rate", "generate" does not.
    """
    missing = response.missing.casefold()
    named = any(re.search(rf"\b{re.escape(term.casefold())}", missing) for term in missing_terms)
    return named and bool(response.alternative.strip())


def _close(a, g, tolerance: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(g, (int, float)):
        return a == g or abs(a - g) < max(tolerance * abs(g), FLOAT_NOISE)
    return a == g


def _rows_close(a: tuple, b: tuple, tolerance: float) -> bool:
    return len(a) == len(b) and all(_close(x, y, tolerance) for x, y in zip(a, b))


def _key_positions(result: Result, key: tuple[str, ...]) -> list[int]:
    """Where the key columns are; ValueError when the result has no column of that name."""
    names = [column.casefold() for column in result.columns]
    return [names.index(column.casefold()) for column in key]


def _key_values(rows: list[tuple], positions: list[int]) -> set[tuple]:
    return {tuple(row[i] for i in positions) for row in rows}


def _pair_off(executed: set[tuple], gold: set[tuple], tolerance: float) -> bool:
    """Whether each row pairs with a gold row of its own within tolerance (a perfect bipartite
    matching, found by augmenting paths), so the outcome does not depend on the order rows are tried.

    Equal rows start out paired, so identical results need no search; a path can still re-pair them.
    """
    if len(executed) != len(gold):
        return False
    partner = {row: row for row in executed & gold}  # gold row -> the executed row paired with it

    def augment(row: tuple, seen: set[tuple]) -> bool:
        for g in gold:
            if g not in seen and _rows_close(row, g, tolerance):
                seen.add(g)
                if g not in partner or augment(partner[g], seen):
                    partner[g] = row
                    return True
        return False

    return all(augment(row, set()) for row in executed - gold)


def results_match(executed: Result, gold: Result, key: tuple[str, ...] = (), tolerance: float = TOLERANCE) -> bool:
    """The same set of key values when a key is given, otherwise the same set of rows within tolerance.

    Row order and repeated rows never matter. Key values are compared exactly, since they identify.
    Key columns are found by name; an answer that renamed one, with as many columns as the gold
    result, is read at the gold result's positions.
    """
    if key:
        gold_positions = _key_positions(gold, key)
        try:
            positions = _key_positions(executed, key)
        except ValueError:  # the answer does not name a key column
            if len(executed.columns) != len(gold.columns):
                return False
            positions = gold_positions
        return _key_values(executed.rows, positions) == _key_values(gold.rows, gold_positions)
    return _pair_off(set(executed.rows), set(gold.rows), tolerance)


def _single_number(result: Result):
    rows = result.rows
    if len(rows) == 1 and len(rows[0]) == 1 and isinstance(rows[0][0], (int, float)):
        return rows[0][0]
    return None


def _size_bucket(executed: Result, gold: Result) -> Bucket | None:
    """How far off a wrong single-number answer is."""
    a, g = _single_number(executed), _single_number(gold)
    if a is None or g is None:
        return None
    if abs(g) < FLOAT_NOISE or abs(a) < FLOAT_NOISE or a * g < 0:  # a zero on either side, or opposite signs
        return Bucket.SIGN_OR_ZERO_MISMATCH
    if abs(a - g) <= 0.05 * abs(g):
        return Bucket.WITHIN_5_PERCENT
    if max(a / g, g / a) <= 2:
        return Bucket.WITHIN_FACTOR_2
    return Bucket.BEYOND_FACTOR_2


def score(
    response: Response,
    executed: Result | None,
    gold: Result | None,
    *,
    key: tuple[str, ...] = (),
    missing_terms: tuple[str, ...] = (),
    tolerance: float = TOLERANCE,
    refusal_check: RefusalCheck = rule_based_refusal_check,
) -> Score:
    """Score one response.

    `executed` is the result of re-running an answer's final SQL, None when there is none or it
    failed. `gold` is None for a question whose correct response is a refusal, whose recorded
    missing-piece terms are then `missing_terms`. A non-empty `key` marks a set answer.
    """
    if response.kind == ResponseKind.CLARIFICATION:
        return Score(ResponseClass.CLARIFICATION_REQUEST)
    if gold is None:
        if response.kind == ResponseKind.ANSWER:
            return Score(ResponseClass.WRONG_ANSWER, Bucket.ANSWERED_UNANSWERABLE)
        if refusal_check(response, missing_terms):
            return Score(ResponseClass.CORRECT_REFUSAL)
        return Score(ResponseClass.WRONG_ANSWER, Bucket.INADEQUATE_REFUSAL)
    if response.kind == ResponseKind.REFUSAL:
        return Score(ResponseClass.OVER_REFUSAL)
    if executed is None:
        return Score(ResponseClass.WRONG_ANSWER)
    if results_match(executed, gold, key, tolerance):
        return Score(ResponseClass.CORRECT_ANSWER)
    return Score(ResponseClass.WRONG_ANSWER, None if key else _size_bucket(executed, gold))


def accuracy(classes: Iterable[str]) -> float | None:
    """(Correct answers + correct refusals) / every response except clarification requests and
    failures. None when nothing is left to count."""
    counted = [c for c in classes if c not in (ResponseClass.CLARIFICATION_REQUEST, ResponseClass.FAILED)]
    if not counted:
        return None
    return sum(c in (ResponseClass.CORRECT_ANSWER, ResponseClass.CORRECT_REFUSAL) for c in counted) / len(counted)


def flips(classes: Iterable[str]) -> bool | None:
    """Whether a question's scored runs in one condition do not all share one response class; None
    when fewer than two runs were scored, so there is nothing to compare."""
    scored = [c for c in classes if c != ResponseClass.FAILED]
    if len(scored) < 2:
        return None
    return len(set(scored)) > 1


def is_stale_value(
    executed: Result | None, pre_drift_gold: Result, post_drift_gold: Result, tolerance: float = TOLERANCE
) -> bool:
    """Whether a post-drift answer's result matches the pre-drift gold result and not the post-drift
    one: a drift smaller than the tolerance leaves the right answer matching both."""
    return (
        executed is not None
        and results_match(executed, pre_drift_gold, tolerance=tolerance)
        and not results_match(executed, post_drift_gold, tolerance=tolerance)
    )


def is_silent_error(scored: Score, executed: Result | None, escalations: int) -> bool:
    """A wrong answer given without an error, a refusal, a clarification request or an escalation.

    Only an answer whose final SQL ran has an executed result: a refusal, an inadequate one
    included, has none, and an answer whose SQL failed came with an error. `escalations` is the
    number of escalation calls in the run, each of them one question to a person.
    """
    return scored.response_class == ResponseClass.WRONG_ANSWER and executed is not None and escalations == 0
