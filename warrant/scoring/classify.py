"""Response classes. The tracer bullet's minimum: correct or wrong; #40 adds refusals and buckets."""

import math

from warrant.agent.interface import Response, ResponseKind


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def _row_key(row: tuple) -> tuple:
    return tuple((v is None, str(v)) for v in row)


def results_match(executed: list[tuple], gold: list[tuple]) -> bool:
    """Same rows regardless of order, numbers compared up to floating-point noise."""
    if len(executed) != len(gold):
        return False
    return all(
        len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
        for a, b in zip(sorted(executed, key=_row_key), sorted(gold, key=_row_key))
    )


def classify(response: Response, executed: list[tuple] | None, gold: list[tuple]) -> str:
    if response.kind == ResponseKind.ANSWER and executed is not None and results_match(executed, gold):
        return "correct"
    return "wrong"
