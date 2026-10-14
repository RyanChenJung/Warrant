"""Measuring and re-proving.

`verify` re-runs a stored statement and compares the result to what we recorded.
That single operation serves two purposes: it is the P2 promise that a customer
can check any claim we make, and it is the data-drift detector of SPEC 7 - an
assertion whose evidence no longer returns the recorded answer is precisely an
assertion the data has outgrown.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import duckdb

from warrant.battery.gloss.model import Assertion, QuoteEvidence, SqlEvidence


def _jsonable(value: Any) -> Any:
    """YAML round-trips need plain types. DuckDB hands back Decimal and date
    objects that would not survive a save/load cycle intact."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def measure(conn: duckdb.DuckDBPyConnection, sql: str) -> Any:
    """Shape the result to the smallest faithful form: scalar, flat row, or rows."""
    rows = conn.sql(sql).fetchall()
    if len(rows) == 1 and len(rows[0]) == 1:
        return _jsonable(rows[0][0])
    if len(rows) == 1:
        return [_jsonable(v) for v in rows[0]]
    return [[_jsonable(v) for v in row] for row in rows]


def make_evidence(
    conn: duckdb.DuckDBPyConnection, sql: str, today: str
) -> SqlEvidence:
    return SqlEvidence(sql=sql, expected=measure(conn, sql), measured_at=today)


@dataclass(frozen=True)
class VerifyResult:
    evidence: SqlEvidence | QuoteEvidence
    status: Literal["PASS", "DRIFT", "ERROR"]
    actual: Any
    message: str


def verify(conn: duckdb.DuckDBPyConnection, evidence: SqlEvidence) -> VerifyResult:
    try:
        actual = measure(conn, evidence.sql)
    except Exception as exc:  # noqa: BLE001 - any failure is a failed proof
        return VerifyResult(evidence, "ERROR", None,
                            f"evidence would not run: {exc}")
    if actual == evidence.expected:
        return VerifyResult(evidence, "PASS", actual, "re-ran and matched")
    return VerifyResult(
        evidence, "DRIFT", actual,
        f"recorded {evidence.expected!r} but the data now returns {actual!r}",
    )


def verify_all(
    conn: duckdb.DuckDBPyConnection, assertions: list[Assertion]
) -> list[tuple[Assertion, VerifyResult]]:
    out: list[tuple[Assertion, VerifyResult]] = []
    for assertion in assertions:
        for ev in assertion.evidence:
            if isinstance(ev, SqlEvidence):
                out.append((assertion, verify(conn, ev)))
    return out


def verify_quote(
    evidence: QuoteEvidence,
    resolve: Callable[[str, str], str | None],
) -> VerifyResult:
    """P2: confirm the quoted string really is at the cited location.

    This is `in` on two strings. No model is consulted, which is the whole point -
    a fabricated citation is caught by arithmetic rather than by asking another
    model whether it looks right.
    """
    text = resolve(evidence.source, evidence.locator)
    if text is None:
        return VerifyResult(evidence, "ERROR", None,
                            f"cited location does not exist: {evidence.source}"
                            f"#{evidence.locator}")
    if evidence.quote in text:
        return VerifyResult(evidence, "PASS", evidence.quote,
                            "quote found at the cited location")
    return VerifyResult(evidence, "DRIFT", text,
                        f"quoted text is not present at {evidence.source}"
                        f"#{evidence.locator}")
