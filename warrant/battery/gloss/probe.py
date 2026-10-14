"""Behavioural probes: turning a human-only question into a measurable one.

An ordinal column's direction looks like tribal knowledge. It is not. If the scale
governs anything operationally it leaves a trace, and the trace is measurable. This
probe searches pairs of date columns for a delay that varies with the ordinal level,
then reports the direction with a rank correlation, an effect size, and a sample size.

That phrasing matters. "Rank correlation +0.X, effect size Nx, n=..." is a claim
a reader can argue with; "confidence 0.9" is not.
"""
from __future__ import annotations

from itertools import combinations

from warrant.battery.gloss.detect import LOW_CARDINALITY_MAX, Context, quote
from warrant.battery.gloss.detect.scope import date_expression
from warrant.battery.gloss.evidence import make_evidence
from warrant.battery.gloss.model import Assertion, AssertionType, Finding, Tier

_MIN_LEVELS = 3
_MIN_EFFECT = 3.0
_MIN_ROWS_PER_LEVEL = 2
# Rank correlation, not strict monotonicity. Real ordinal delays are often clearly
# ordered but not monotone - an unmistakable signal with a few small wobbles - and
# requiring a monotone sequence would reject such a series outright.
_MIN_RANK_CORRELATION = 0.6
# A level carrying almost no rows should not swing the correlation, so levels
# holding less than this share of the population are left out.
_MIN_LEVEL_SHARE = 0.001


def _ranks(values: list[float]) -> list[float]:
    """Average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman's rho. Zero when either side has no variation to rank."""
    n = len(xs)
    if n < 2:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy) ** 0.5


def _ordinal_levels(ctx: Context, column: str) -> list[float] | None:
    col = quote(column)
    predicate = f"TRY_CAST({col} AS DOUBLE) IS NOT NULL"
    rows = ctx.conn.sql(f"""
        SELECT DISTINCT TRY_CAST({col} AS DOUBLE) AS v
        FROM {quote(ctx.table)}{ctx.where(predicate)}
        ORDER BY v
    """).fetchall()
    levels = [r[0] for r in rows]
    if not _MIN_LEVELS <= len(levels) <= LOW_CARDINALITY_MAX:
        return None
    return levels


def _date_columns(ctx: Context) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for column in ctx.columns:
        expr = date_expression(column, ctx.conn, ctx.table)
        if expr:
            out.append((column, expr))
    return out


def probe_ordinal_direction(
    ctx: Context,
    column: str,
    date_columns: list[tuple[str, str]] | None = None,
) -> Finding | None:
    if _ordinal_levels(ctx, column) is None:
        return None
    if date_columns is None:
        date_columns = _date_columns(ctx)
    col = quote(column)
    min_rows = max(_MIN_ROWS_PER_LEVEL,
                   int(ctx.population() * _MIN_LEVEL_SHARE))
    best: tuple[float, float, str, str, str] | None = None
    for (start, start_expr), (end, end_expr) in combinations(date_columns, 2):
        predicate = (f"{start_expr} IS NOT NULL AND {end_expr} IS NOT NULL "
                     f"AND TRY_CAST({col} AS DOUBLE) IS NOT NULL")
        sql = f"""
            SELECT TRY_CAST({col} AS DOUBLE) AS level,
                   MEDIAN(date_diff('day', {start_expr}, {end_expr})) AS delay_days,
                   COUNT(*) AS n
            FROM {quote(ctx.table)}{ctx.where(predicate)}
            GROUP BY 1 HAVING COUNT(*) >= {min_rows}
            ORDER BY 1
        """
        rows = ctx.conn.sql(sql).fetchall()
        if len(rows) < _MIN_LEVELS:
            continue
        levels = [float(r[0]) for r in rows]
        days = [float(r[1]) for r in rows]
        if any(d < 0 for d in days):
            continue  # not an elapsed-time pair
        rho = spearman(levels, days)
        if abs(rho) < _MIN_RANK_CORRELATION:
            continue
        effect = (max(days) + 1) / (min(days) + 1)
        if effect < _MIN_EFFECT:
            continue
        score = abs(rho) * effect
        if best is None or score > best[0]:
            best = (score, rho, sql, start, end)
    if best is None:
        return None
    return _finding(ctx, column, best)


def _finding(ctx: Context, column: str, best) -> Finding:
    _, rho, sql, start, end = best
    evidence = make_evidence(ctx.conn, sql, ctx.today)
    rows = evidence.expected
    days = [float(r[1]) for r in rows]
    n = sum(int(r[2]) for r in rows)
    effect = (max(days) + 1) / (min(days) + 1)
    rising = rho > 0
    words = ("lower numbers are acted on sooner, so lower means more urgent"
             if rising else
             "higher numbers are acted on sooner, so higher means more urgent")
    direction = "lower_is_more" if rising else "higher_is_more"
    detail = ", ".join(f"level {r[0]:g}: {float(r[1]):g} days" for r in rows)
    statement = (
        f"Direction established by behavioural probe: {words}. Median days from "
        f"{start} to {end} by level - {detail}. Rank correlation {rho:+.2f}, "
        f"effect size {effect:.0f}x, n={n:,}. No human was consulted."
    )
    declared = ctx.dictionary.get(column) if ctx.dictionary else None
    documented = declared.documented_direction() if declared else None
    if documented and documented != direction:
        statement += (
            f" This contradicts the official dictionary, which documents "
            f"{documented.replace('_', ' ')}. The documentation describes the "
            f"vendor's intent; the probe describes this organisation's practice."
        )
    return Finding(Assertion(
        type=AssertionType.FIELD, subject=ctx.subject(column),
        statement=statement, tier=Tier.MEASURED, evidence=(evidence,),
    ), impact=1.0)


class OrdinalDirectionProbe:
    type = AssertionType.FIELD

    def run(self, ctx: Context) -> list[Finding]:
        # Scanned once per table. Detecting date columns costs one query per
        # column per candidate format, so doing it inside the loop made the probe
        # by far the slowest thing in the run.
        date_columns = _date_columns(ctx)
        out: list[Finding] = []
        for column in ctx.columns:
            finding = probe_ordinal_direction(ctx, column, date_columns)
            if finding:
                out.append(finding)
        return out
