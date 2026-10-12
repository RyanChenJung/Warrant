"""The scorer both lines share (#40): a response class for every response, a bucket for a wrong one.

The numeric tolerance and the refusal check belong to the global part of the freeze (#33). Until it
is wired in they are parameters, with the spec's values as defaults.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from warrant.agent.interface import Response, ResponseKind

# A numeric answer is correct when its relative error is below this.
TOLERANCE = 0.05


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


@dataclass(frozen=True)
class Score:
    response_class: ResponseClass
    bucket: Bucket | None = None


RefusalCheck = Callable[[Response, tuple[str, ...]], bool]


def rule_based_refusal_check(response: Response, missing_terms: tuple[str, ...]) -> bool:
    """The missing-piece field contains at least one recorded term, and the alternative is not empty."""
    missing = response.missing.casefold()
    return any(term.casefold() in missing for term in missing_terms) and bool(response.alternative.strip())


def _close(a, g, tolerance: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(g, (int, float)):
        return a == g or abs(a - g) < tolerance * abs(g)
    return a == g


def _rows_close(a: tuple, b: tuple, tolerance: float) -> bool:
    return len(a) == len(b) and all(_close(x, y, tolerance) for x, y in zip(a, b))


def _key_values(result: Result, key: tuple[str, ...]) -> set[tuple]:
    """The set of key-value tuples; ValueError when the result has no column of that name."""
    names = [column.casefold() for column in result.columns]
    positions = [names.index(column.casefold()) for column in key]
    return {tuple(row[i] for i in positions) for row in result.rows}


def results_match(executed: Result, gold: Result, key: tuple[str, ...] = (), tolerance: float = TOLERANCE) -> bool:
    """The same set of key values when a key is given, otherwise the same set of rows within tolerance.

    Row order and repeated rows never matter. Key values are compared exactly, since they identify.
    """
    if key:
        gold_keys = _key_values(gold, key)
        try:
            return _key_values(executed, key) == gold_keys
        except ValueError:  # the answer does not name a key column
            return False
    executed_rows, unmatched = set(executed.rows), list(set(gold.rows))
    if len(executed_rows) != len(unmatched):
        return False
    for row in executed_rows:
        match = next((g for g in unmatched if _rows_close(row, g, tolerance)), None)
        if match is None:
            return False
        unmatched.remove(match)
    return True


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
    if g == 0 or a * g <= 0:  # a zero gold answer, a zero answer, or opposite signs
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


def flips(classes: Iterable[str]) -> bool:
    """Whether a question's scored runs in one condition do not all share one response class."""
    return len({c for c in classes if c != ResponseClass.FAILED}) > 1


def is_stale_value(executed: Result | None, pre_drift_gold: Result, tolerance: float = TOLERANCE) -> bool:
    """Whether a post-drift answer's result matches the pre-drift gold result."""
    return executed is not None and results_match(executed, pre_drift_gold, tolerance=tolerance)


def is_silent_error(scored: Score, executed: Result | None, escalations: int) -> bool:
    """A wrong answer given without an error, a refusal, a clarification request or an escalation.

    Only an answer whose final SQL ran has an executed result: a refusal, an inadequate one
    included, has none, and an answer whose SQL failed came with an error. `escalations` is the
    number of escalation calls in the run, each of them one question to a person.
    """
    return scored.response_class == ResponseClass.WRONG_ANSWER and executed is not None and escalations == 0
