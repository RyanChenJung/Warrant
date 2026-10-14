"""Type 7 LIMIT - what must not be used, what is absent, how much is covered.

The agent contract is MUST-read: an agent that ignores a LIMIT assertion answers
confidently and wrongly, which is the worst failure mode available to it.
"""
from __future__ import annotations

from warrant.battery.gloss.detect import HIGH_NULL_THRESHOLD, Context, quote
from warrant.battery.gloss.evidence import make_evidence
from warrant.battery.gloss.model import Assertion, AssertionType, Finding, Question, Tier

# A column whose emptiness plausibly means "this fact was never recorded" rather
# than "not applicable" - worth one question to a human.
_KEY_SHAPED_SUFFIXES = ("NUM", "ID", "CODE", "NO")


class LimitDetector:
    type = AssertionType.LIMIT

    def run(self, ctx: Context) -> list[Finding]:
        findings: list[Finding] = []
        findings += self._empty_and_sparse(ctx)
        findings += self._undocumented(ctx)
        return findings

    def _empty_and_sparse(self, ctx: Context) -> list[Finding]:
        population = ctx.population()
        if population == 0:
            return []
        out: list[Finding] = []
        for column in ctx.columns:
            col = quote(column)
            sql = (
                f"SELECT ROUND(100.0 * SUM(CASE WHEN {col} IS NULL OR {col} = '' "
                f"THEN 1 ELSE 0 END) / COUNT(*), 1) "
                f"FROM {quote(ctx.table)}{ctx.where()}"
            )
            evidence = make_evidence(ctx.conn, sql, ctx.today)
            pct = float(evidence.expected)
            if pct >= 100.0:
                out.append(Finding(Assertion(
                    type=self.type, subject=ctx.subject(column),
                    statement=(
                        f"Column is entirely empty across all {population:,} rows "
                        f"in scope. It carries no information and must not be used."
                    ),
                    tier=Tier.MEASURED, evidence=(evidence,),
                ), impact=1.0))
            elif pct >= HIGH_NULL_THRESHOLD * 100:
                out.append(self._sparse_finding(ctx, column, pct, population,
                                                evidence))
        return out

    def _sparse_finding(self, ctx, column, pct, population, evidence) -> Finding:
        assertion = Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(
                f"Empty in {pct}% of the {population:,} rows in scope. Any average, "
                f"rate, or join over this column silently excludes those rows."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        question = None
        if column.upper().endswith(_KEY_SHAPED_SUFFIXES):
            question = Question(
                subject=ctx.subject(column),
                text=(f"{column} is empty on {pct}% of rows. Is populating it "
                      f"expected for this kind of record?"),
                proposed_answer=(
                    f"Not expected - the {pct}% is legitimate, and analyses should "
                    f"treat the column as optional."
                ),
                options=("not expected - legitimately optional",
                         "expected - the gap is a data-quality problem",
                         "expected for some record types only",
                         "unsure"),
                basis=assertion.id, cost_seconds=20,
            )
        return Finding(assertion, question, impact=pct / 100.0)

    def _undocumented(self, ctx: Context) -> list[Finding]:
        """A column with no dictionary entry has no authority behind any reading of
        it. Pure set difference - no inference involved."""
        if ctx.dictionary is None:
            return []
        documented = ctx.dictionary.attributes()
        out: list[Finding] = []
        for column in ctx.columns:
            if column.upper() in documented:
                continue
            sql = (f"SELECT COUNT(DISTINCT {quote(column)}) "
                   f"FROM {quote(ctx.table)}{ctx.where()}")
            out.append(Finding(Assertion(
                type=self.type, subject=ctx.subject(column),
                statement=(
                    f"Column has no entry in the official dictionary "
                    f"({ctx.dictionary.object_name}), so no documented meaning "
                    f"exists for it."
                ),
                tier=Tier.MEASURED,
                evidence=(make_evidence(ctx.conn, sql, ctx.today),),
            )))
        return out
