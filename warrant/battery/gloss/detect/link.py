"""Type 5 LINK - join path, cardinality, fan-out risk, authority.

MUST-read before any join, because the failure mode is double counting and it is
silent. Two things are reported that a schema diagram cannot tell you: the actual
match rate (rarely exactly 100%), and the direction of cardinality, which
determines whether a sum inflates after the join.

Column pairing is by name, case-insensitively, because real exports disagree about
case: the work-order table has ASSETNUM and the asset master has assetnum.

Changed in Warrant (see VENDORING.md): columns are also paired on the declared
foreign keys given to `LinkDetector`, from child to parent only. What is checked on
each pair is as released.
"""
from __future__ import annotations

from warrant.battery.gloss.detect import Context, quote
from warrant.battery.gloss.evidence import make_evidence
from warrant.battery.gloss.model import Assertion, AssertionType, Finding, Question, Tier
from warrant.battery.gloss.source import columns as _columns

_MIN_MATCH_RATE = 50.0


def name_matched_pairs(conn, left_columns: list[str],
                       peer: str) -> list[tuple[str, str]]:
    """Column pairs joining `left_columns` to `peer`, matched by name.

    Case-insensitively, because real exports disagree: the work-order table has
    ASSETNUM and the asset master has assetnum. Usage-drift checking uses this to
    ask what join path Gloss would have endorsed for a pair of tables a logged
    query joined some other way.
    """
    peer_cols = {c.upper(): c for c in _columns(conn, peer)}
    return [(c, peer_cols[c.upper()]) for c in left_columns
            if c.upper() in peer_cols]


def declared_key_pairs(declared_keys, table: str,
                       peer: str) -> list[tuple[str, str]]:
    """Column pairs joining `table` to `peer` on declared foreign keys.

    `declared_keys` holds (child table, child column, parent table, parent column)
    tuples. A key is paired only in its declared direction, from the child that
    holds the reference to the parent it references: the parent is never paired
    back to its child. Table and column names are used as declared.
    """
    return [(column, ref_column)
            for child, column, parent, ref_column in declared_keys
            if child == table and parent == peer]


class LinkDetector:
    type = AssertionType.LINK

    def __init__(self, declared_keys=()):
        self.declared_keys = tuple(declared_keys)

    def run(self, ctx: Context) -> list[Finding]:
        findings: list[Finding] = []
        for peer in ctx.peers.values():
            if peer == ctx.table:
                continue
            for left, right in self._pairs(ctx, peer):
                findings += self._analyse(ctx, peer, left, right)
        return findings

    def _pairs(self, ctx: Context, peer: str) -> list[tuple[str, str]]:
        pairs = name_matched_pairs(ctx.conn, ctx.columns, peer)
        seen = {(left.upper(), right.upper()) for left, right in pairs}
        for left, right in declared_key_pairs(self.declared_keys, ctx.table, peer):
            if (left.upper(), right.upper()) not in seen:
                seen.add((left.upper(), right.upper()))
                pairs.append((left, right))
        return pairs

    def _analyse(self, ctx, peer, left, right) -> list[Finding]:
        lq, rq = quote(left), quote(right)
        sql = f"""
            SELECT COUNT(*) AS referencing,
                   ROUND(100.0 * SUM(CASE WHEN m.{rq} IS NOT NULL THEN 1 ELSE 0 END)
                         / COUNT(*), 2) AS pct_matched,
                   (SELECT COUNT(*) = COUNT(DISTINCT {rq}) FROM {quote(peer)})
                     AS peer_key_unique
            FROM {quote(ctx.table)} c
            LEFT JOIN (SELECT DISTINCT {rq} FROM {quote(peer)}) m
              ON c.{lq} = m.{rq}
            WHERE c.{lq} IS NOT NULL AND c.{lq} <> ''
        """
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        referencing, pct, peer_unique = evidence.expected
        if not referencing or pct is None or float(pct) < _MIN_MATCH_RATE:
            return []
        pct = float(pct)
        cardinality = "many-to-one" if peer_unique else "many-to-many"
        fan_out = ("so a join will not fan out and sums stay correct"
                   if peer_unique else
                   "so a join WILL fan out and any sum after it is inflated")
        assertion = Assertion(
            type=self.type, subject=ctx.subject(left),
            statement=(
                f"{left} joins to {peer}.{right} for {pct}% of the {referencing:,} "
                f"rows that populate it. The relationship is {cardinality}, "
                f"{fan_out}."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        out = [Finding(assertion)]
        if pct < 100.0:
            out.append(self._unmatched(ctx, peer, left, right, pct, referencing))
        out += self._reverse_coverage(ctx, peer, left, right)
        return out

    def _unmatched(self, ctx, peer, left, right, pct, referencing) -> Finding:
        lq, rq = quote(left), quote(right)
        sql = f"""
            SELECT COUNT(*), MIN(c.{lq}) FROM {quote(ctx.table)} c
            LEFT JOIN (SELECT DISTINCT {rq} FROM {quote(peer)}) m ON c.{lq} = m.{rq}
            WHERE c.{lq} IS NOT NULL AND c.{lq} <> '' AND m.{rq} IS NULL
        """
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        count, example = evidence.expected
        assertion = Assertion(
            type=self.type, subject=ctx.subject(left),
            statement=(
                f"{int(count):,} rows ({100 - pct:.2f}%) reference a "
                f"{peer}.{right} value that does not exist there, for example "
                f"{example!r}. An inner join silently drops them."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        question = Question(
            subject=ctx.subject(left),
            text=(f"{int(count):,} {left} values are missing from {peer} "
                  f"(for example {example!r}). What are they?"),
            proposed_answer=(f"Retired or historical records that {peer} no longer "
                             f"lists."),
            options=("retired or historical records",
                     "records from a system not present here",
                     "data-entry errors",
                     "unsure"),
            basis=assertion.id, cost_seconds=25,
        )
        return Finding(assertion, question,
                       impact=(100.0 - pct) / 100.0)

    def _reverse_coverage(self, ctx, peer, left, right) -> list[Finding]:
        """Entities in the master that this table never mentions. On a maintenance
        table this is the difference between "no failures" and "not monitored"."""
        lq, rq = quote(left), quote(right)
        sql = f"""
            SELECT COUNT(*), (SELECT COUNT(DISTINCT {rq}) FROM {quote(peer)})
            FROM (SELECT DISTINCT {rq} FROM {quote(peer)}) m
            WHERE m.{rq} NOT IN (SELECT {lq} FROM {quote(ctx.table)}
                                 WHERE {lq} IS NOT NULL AND {lq} <> '')
        """
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        missing, total = (int(v) for v in evidence.expected)
        if missing == 0:
            return []
        return [Finding(Assertion(
            type=self.type, subject=f"{peer}.{right}",
            statement=(
                f"{missing} of {total} {peer}.{right} values are never referenced by "
                f"{ctx.table}.{left}. Absence of rows for them means 'not recorded "
                f"here', not 'nothing happened'."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        ), impact=missing / total if total else 0.0)]
