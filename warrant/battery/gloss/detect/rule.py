"""Type 6 RULE - how a business concept is computed.

SPEC 3 notes this type is rarely derivable from data alone, and v1 excludes SQL
assets, dbt models, and pull requests. Two sources remain, and the second turned
out to be the one that works.

**Documentation.** Gloss can prove the dictionary *says* a field is computed a
certain way; it cannot prove this organisation follows that definition - a
priority field documented one way and used another is proof that vendor
documentation and local practice diverge. So the assertion states what is
provable and the question asks the rest. In practice this source can return
nothing: the computation-shaped REMARKS in a dictionary often reference columns
the export does not carry.

**Measured identities.** A total column can turn out to equal the sum of other
columns *exactly*, on every row where the total is non-zero. That is a business
rule recovered from data alone with re-runnable SQL, and often nobody documented
it - the recovered formula may include a component nobody expected, which is
the kind of thing an agent must know and no schema reveals. Discovering it is
arithmetic, so P1 holds.
"""
from __future__ import annotations

from collections.abc import Callable
from itertools import combinations

from warrant.battery.gloss.detect import Context, quote
from warrant.battery.gloss.dictionary import Dictionary
from warrant.battery.gloss.evidence import make_evidence
from warrant.battery.gloss.model import (
    Assertion, AssertionType, Finding, Question, QuoteEvidence, Tier,
)

_IDENTITY_MIN_SHARE = 0.80
_MAX_NUMERIC_COLUMNS = 12   # keeps the pair search bounded
_TOLERANCE = 0.005


def dictionary_resolver(dictionary: Dictionary) -> Callable[[str, str], str | None]:
    """Resolves a locator of the form OBJECT.ATTRIBUTE.REMARKS to its text, so a
    quote can be checked against the actual source."""
    def resolve(source: str, locator: str) -> str | None:
        parts = locator.split(".")
        if len(parts) != 3 or parts[2] != "REMARKS":
            return None
        _, attribute, _ = parts
        declared = dictionary.get(attribute)
        return declared.remarks if declared else None
    return resolve


def numeric_columns(ctx: Context) -> list[str]:
    """Columns whose populated values all parse as numbers. Necessary because
    everything is stored as VARCHAR by design."""
    out: list[str] = []
    for column in ctx.columns:
        col = quote(column)
        row = ctx.conn.sql(f"""
            SELECT COUNT(*), COUNT(TRY_CAST({col} AS DOUBLE))
            FROM {quote(ctx.table)} WHERE {col} IS NOT NULL AND {col} <> ''
        """).fetchone()
        if row[0] and row[0] == row[1]:
            out.append(column)
    return out


class RuleDetector:
    type = AssertionType.RULE

    def run(self, ctx: Context) -> list[Finding]:
        out: list[Finding] = []
        if ctx.dictionary is not None:
            present = {c.upper(): c for c in ctx.columns}
            for declared in ctx.dictionary.computed_fields():
                column = present.get(declared.attribute)
                if column is not None:
                    out.append(self._documented(ctx, column, declared))
        out += self._identities(ctx)
        return out

    def _documented(self, ctx, column, declared) -> Finding:
        col = quote(column)
        sql = (f"SELECT COUNT(*) FROM {quote(ctx.table)} "
               f"WHERE {col} IS NOT NULL AND {col} <> ''")
        sql_evidence = make_evidence(ctx.conn, sql, ctx.today)
        quote_evidence = QuoteEvidence(
            quote=declared.remarks.strip(),
            source=ctx.dictionary.object_name.lower() + "_dictionary",
            locator=f"{declared.object_name}.{declared.attribute}.REMARKS",
        )
        assertion = Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(
                f"The official dictionary states this is a computed field: "
                f'"{declared.remarks.strip()}" Whether this organisation computes '
                f"it that way is unconfirmed - vendor documentation and local "
                f"practice are known to diverge on this system."
            ),
            tier=Tier.MEASURED,
            evidence=(sql_evidence, quote_evidence),
        )
        question = Question(
            subject=ctx.subject(column),
            text=f"Is {column} computed as documented in this organisation?",
            proposed_answer="Yes - computed as the dictionary describes.",
            options=("yes", "no", "partly", "unsure"),
            basis=assertion.id, cost_seconds=25,
        )
        return Finding(assertion, question)

    def _identities(self, ctx: Context) -> list[Finding]:
        """Find target = sum(other columns) among numeric columns.

        Two things here were learned the hard way against real data.

        **Only rows where the target is non-zero count.** When most rows have
        every cost column at zero, "target = a + b" appears to hold on most rows
        for arbitrary a and b - it is really measuring 0 = 0 + 0. Restricted to
        non-zero targets, those spurious matches score 0% and the real rule
        scores 100%.

        **Subsets of two and three.** A true rule can need three terms, holding
        exactly on every non-zero row. Stopping at pairs finds only a weak partial
        match and misses it entirely.

        All candidate subsets for one target are counted in a single query, so the
        search costs one pass per target rather than one per subset.
        """
        pool = numeric_columns(ctx)[:_MAX_NUMERIC_COLUMNS]
        out: list[Finding] = []
        for target in pool:
            others = [c for c in pool if c != target]
            combos = [*combinations(others, 2), *combinations(others, 3)]
            if not combos:
                continue
            best = self._best_combo(ctx, target, combos)
            if best is not None:
                out.append(self._identity_finding(ctx, target, best))
        return out

    def _best_combo(self, ctx, target, combos) -> tuple[str, ...] | None:
        """Highest-scoring subset for this target, or None if none clears the bar."""
        t = quote(target)
        parts = []
        for i, combo in enumerate(combos):
            total = " + ".join(f"COALESCE(TRY_CAST({quote(c)} AS DOUBLE), 0)"
                               for c in combo)
            parts.append(
                f"SUM(CASE WHEN abs(TRY_CAST({t} AS DOUBLE) - ({total})) "
                f"< {_TOLERANCE} THEN 1 ELSE 0 END) AS c{i}"
            )
        predicate = f"TRY_CAST({t} AS DOUBLE) IS NOT NULL AND TRY_CAST({t} AS DOUBLE) <> 0"
        sql = (f"SELECT COUNT(*), {', '.join(parts)} FROM {quote(ctx.table)}"
               f"{ctx.where(predicate)}")
        row = ctx.conn.sql(sql).fetchall()[0]
        n = row[0]
        if not n:
            return None
        scored = [(int(row[i + 1] or 0) / n, len(combo), combo)
                  for i, combo in enumerate(combos)]
        # Highest share first; on a tie prefer the simpler explanation.
        share, _, combo = max(scored, key=lambda s: (s[0], -s[1]))
        return combo if share >= _IDENTITY_MIN_SHARE else None

    def _identity_finding(self, ctx, target, combo: tuple[str, ...]) -> Finding:
        t = quote(target)
        total = " + ".join(f"COALESCE(TRY_CAST({quote(c)} AS DOUBLE), 0)"
                           for c in combo)
        predicate = f"TRY_CAST({t} AS DOUBLE) IS NOT NULL AND TRY_CAST({t} AS DOUBLE) <> 0"
        sql = f"""
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN abs(TRY_CAST({t} AS DOUBLE) - ({total}))
                       < {_TOLERANCE} THEN 1 ELSE 0 END) AS holds,
                   SUM(CASE WHEN TRY_CAST({t} AS DOUBLE) < ({total}) - {_TOLERANCE}
                       THEN 1 ELSE 0 END) AS below
            FROM {quote(ctx.table)}
            {ctx.where(predicate)}
        """
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        n, holds, below = (int(v or 0) for v in evidence.expected)
        pct = round(100.0 * holds / n, 1)
        formula = " + ".join(combo)
        if holds == n:
            assertion = Assertion(
                type=self.type, subject=ctx.subject(target),
                statement=(
                    f"{target} equals {formula} for all {n:,} rows where it is "
                    f"non-zero ({pct}%). It is a derived column, so summing it "
                    f"alongside its components double counts."
                ),
                tier=Tier.MEASURED, evidence=(evidence,),
            )
            question = Question(
                subject=ctx.subject(target),
                text=(f"{target} is exactly {formula}. Is that the intended "
                      f"definition?"),
                proposed_answer=f"Yes - {target} is defined as {formula}.",
                options=("yes", "no", "partly", "unsure"),
                basis=assertion.id, cost_seconds=20,
            )
            return Finding(assertion, question, impact=1.0)
        direction = "falls short of" if below > (n - holds) / 2 else "exceeds"
        assertion = Assertion(
            type=self.type, subject=ctx.subject(target),
            statement=(
                f"{target} equals {formula} for {pct}% of the {n:,} rows where it is "
                f"non-zero. On the remaining {n - holds:,} it {direction} the sum, so "
                f"at least one further component contributes to {target} and is not "
                f"present in this data. Any breakdown built from {formula} alone is "
                f"incomplete for those rows."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        question = Question(
            subject=ctx.subject(target),
            text=(f"{target} is usually {formula}, but not on {n - holds:,} rows. "
                  f"What is the missing component?"),
            proposed_answer=("A further component - such as services, tools, or "
                             "overhead - that is not exported here."),
            options=("a further category not exported here",
                     "a markup or overhead rate",
                     "a data-entry inconsistency",
                     "unsure"),
            basis=assertion.id, cost_seconds=30,
        )
        return Finding(assertion, question, impact=(n - holds) / n)

