"""Type 1 SCOPE - which population does this data cover?

The agent contract is MUST-read before any aggregate, because a wrong population
makes every denominator wrong. A common and costly pattern: a status column dominated
by one terminal value such as CLOSE, which usually means the extract was filtered to
completed work. An agent asked "how many open work orders are there?" would answer
"almost none" and be confidently wrong.

Extreme skew cannot prove a filter was applied - it is equally consistent with a
process that closes everything - so this detector states the measurement and asks.
"""
from __future__ import annotations

import duckdb

from warrant.battery.gloss.detect import LOW_CARDINALITY_MAX, SKEW_THRESHOLD, Context, quote
from warrant.battery.gloss.evidence import make_evidence
from warrant.battery.gloss.model import Assertion, AssertionType, Finding, Question, Tier

# Ordered by specificity. try_strptime returns NULL rather than raising on a miss.
_DATE_FORMATS = ("%d-%b-%y", "%Y-%m-%d", "%d-%b-%Y", "%m/%d/%Y")
_DATE_NAME_HINTS = ("DATE", "START", "FINISH", "REPORT", "ARRIVE")


def date_expression(
    column: str,
    conn: duckdb.DuckDBPyConnection | None = None,
    table: str | None = None,
) -> str | None:
    """SQL that parses `column` as a date, or None if it does not parse.

    Without a connection this returns the expression for the first candidate
    format, which is the Oracle DD-MON-YY layout a typical legacy export uses.
    With a connection it verifies that every populated value parses before
    committing.
    """
    if conn is None or table is None:
        return f"try_strptime({quote(column)}, '{_DATE_FORMATS[0]}')"
    col = quote(column)
    for fmt in _DATE_FORMATS:
        row = conn.sql(f"""
            SELECT COUNT(*), COUNT(try_strptime({col}, '{fmt}'))
            FROM {quote(table)} WHERE {col} IS NOT NULL AND {col} <> ''
        """).fetchone()
        if row[0] and row[0] == row[1]:
            return f"try_strptime({col}, '{fmt}')"
    return None


class ScopeDetector:
    type = AssertionType.SCOPE

    def run(self, ctx: Context) -> list[Finding]:
        findings: list[Finding] = []
        for column in ctx.columns:
            if any(h in column.upper() for h in _DATE_NAME_HINTS):
                findings += self._period(ctx, column)
            findings += self._skew(ctx, column)
        return findings

    def _period(self, ctx: Context, column: str) -> list[Finding]:
        expr = date_expression(column, ctx.conn, ctx.table)
        if expr is None:
            return []
        sql = (f"SELECT CAST(MIN({expr}) AS DATE), CAST(MAX({expr}) AS DATE), "
               f"COUNT(DISTINCT date_trunc('month', {expr})) "
               f"FROM {quote(ctx.table)}{ctx.where()}")
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        lo, hi, months = evidence.expected
        return [Finding(Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(
                f"Data covers {lo} to {hi}, spanning {months} distinct month(s). "
                f"Anything outside that window is absent rather than zero, and a "
                f"trend that ends at {hi} is an artefact of the extract, not a "
                f"real decline."
            ),
            tier=Tier.MEASURED, evidence=(evidence,), valid_from=str(lo),
            valid_to=str(hi),
        ))]

    def _skew(self, ctx: Context, column: str) -> list[Finding]:
        col = quote(column)
        distinct = ctx.conn.sql(
            f"SELECT COUNT(DISTINCT {col}) FROM {quote(ctx.table)}").fetchone()[0]
        if not 2 <= distinct <= LOW_CARDINALITY_MAX:
            return []
        # Measured over the WHOLE table, deliberately ignoring the grain filter.
        # "Is this extract pre-filtered?" is a question about the extract, and
        # applying our own filter first manufactures the answer: restricted to
        # parent rows, ISTASK is trivially all '0' and WOCLASS trivially all
        # 'WORKORDER', which produced two confidently misleading questions.
        #
        # arg_max, not mode: inside this subquery every distinct value appears
        # exactly once, so mode() would pick arbitrarily and return a different
        # answer on re-run. The verify loop caught that as DRIFT.
        sql = f"""
            SELECT arg_max({col}, n), ROUND(100.0 * MAX(n) / SUM(n), 1)
            FROM (SELECT {col}, COUNT(*) AS n FROM {quote(ctx.table)}
                  GROUP BY 1)
        """
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        value, share = evidence.expected
        if share is None or float(share) < SKEW_THRESHOLD * 100:
            return []
        assertion = Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(
                f"{share}% of rows carry the single value {value!r}, so this extract "
                f"may be pre-filtered to {value!r} rather than representing the full "
                f"population. Any question about the other values is unanswerable "
                f"from this data."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        question = Question(
            subject=ctx.subject(column),
            text=f"Does this extract contain only rows where {column} = {value!r}?",
            proposed_answer=f"Yes - the extract is filtered to {value!r}.",
            options=("yes", "no", "unsure"),
            basis=assertion.id, cost_seconds=10,
        )
        return [Finding(assertion, question, impact=float(share) / 100.0)]
