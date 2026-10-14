"""Type 4 VALUE - what codes, nulls, and sentinel values mean.

Three checks, and a rule about how to ask. The proposed answer for an opaque code
is *measured*, not guessed: it is the modal leading phrase of the descriptions
attached to rows carrying that code. If rows carrying a code XQ are overwhelmingly
described "QUARTERLY INSPECTION ...", the human is handed a proposal to confirm
rather than a blank field, and P1 is not violated because nothing was inferred -
a mode was computed.

Questions are batched one per column. assets.description alone can collapse into
many variant families; asking per family would exhaust the 15-question
budget on a single column.
"""
from __future__ import annotations

from warrant.battery.gloss.detect import LOW_CARDINALITY_MAX, Context, quote
from warrant.battery.gloss.evidence import make_evidence
from warrant.battery.gloss.model import Assertion, AssertionType, Finding, Question, Tier

_MIN_FAMILY_VARIANTS = 2
_MODAL_PREFIX_SHARE = 0.40
_MAX_LISTED = 8
# Above this many tokens on average a column is prose, not an identifier. Format
# analysis on prose reports that free text is heterogeneous, which is not news.
_PROSE_TOKEN_LIMIT = 3.0
# A code's values must recur at least this often on average. Otherwise the column
# identifies rows rather than classifying them. Same reasoning as the equivalence
# guard in detect/grain.py.
_MIN_VALUE_RECURRENCE = 3


def shape_signature(expr: str) -> str:
    """SQL mapping a value to a coarse format class.

    Deliberately coarse. A per-character mask (digits to 9, letters to A) splits
    a mixed LOCATION column into a great many classes and buries the finding; four
    buckets collapse it to the distinction that matters - some values carry digits
    and are building codes, others are alphabetic shop and crew names.
    """
    return (
        f"CASE WHEN regexp_matches({expr}, '^[0-9.]+$') THEN 'numeric' "
        f"WHEN regexp_matches({expr}, '[0-9]') THEN 'alphanumeric' "
        f"WHEN regexp_matches({expr}, '^[A-Za-z]+$') THEN 'word' "
        f"ELSE 'phrase' END"
    )


def _description_column(ctx: Context) -> str | None:
    for column in ctx.columns:
        if "DESC" in column.upper():
            return column
    return None


def _mean_tokens(ctx: Context, column: str) -> float:
    col = quote(column)
    value = ctx.conn.sql(
        f"SELECT AVG(len(str_split({col}, ' '))) FROM {quote(ctx.table)} "
        f"WHERE {col} IS NOT NULL AND {col} <> ''"
    ).fetchone()[0]
    return float(value) if value is not None else 0.0


class ValueDetector:
    type = AssertionType.VALUE

    def run(self, ctx: Context) -> list[Finding]:
        findings: list[Finding] = []
        for column in ctx.columns:
            distinct = ctx.conn.sql(
                f"SELECT COUNT(DISTINCT {quote(column)}) FROM {quote(ctx.table)}"
            ).fetchone()[0]
            if distinct < 2:
                continue
            if (distinct <= LOW_CARDINALITY_MAX
                    and self._is_code_column(ctx, column, distinct)):
                findings += self._codes(ctx, column)
            # Families and format classes are checked at ANY cardinality.
            #
            # Families: the variant-family question is the same question whether the
            # column holds a few descriptions or many - gating it on cardinality would
            # be arbitrary. The check is self-limiting, since values with no stem
            # structure yield families of one and are discarded.
            #
            # Formats: the coarse signature collapses many distinct LOCATION values
            # into a few classes, and that is what surfaces building codes
            # mixed with shop and crew codes.
            findings += self._families(ctx, column)
            findings += self._formats(ctx, column)
        return findings

    def _is_code_column(self, ctx: Context, column: str, distinct: int) -> bool:
        """Is this a column of opaque codes, or something else that merely has few
        distinct values?

        Three exclusions, all learned from running against a second, unseen table,
        where this check asked what every value of a free-text DESCRIPTION column
        meant, and the same for a work-order number:

        - Values must recur. If there are as many distinct values as rows, the
          column identifies rows rather than classifying them, and no gloss exists
          to be written.
        - Not prose. A sentence is not a code.
        - Not numeric. A number's meaning is its scale and direction, which is
          type 3 FIELD's job and the behavioural probe's; asking a human "what does
          the value 5 mean?" wastes the question.
        """
        if distinct * _MIN_VALUE_RECURRENCE > ctx.row_count:
            return False
        if _mean_tokens(ctx, column) > _PROSE_TOKEN_LIMIT:
            return False
        col = quote(column)
        row = ctx.conn.sql(f"""
            SELECT COUNT(*), COUNT(TRY_CAST({col} AS DOUBLE))
            FROM {quote(ctx.table)} WHERE {col} IS NOT NULL AND {col} <> ''
        """).fetchone()
        populated, numeric = row[0], row[1] or 0
        return not (populated and numeric == populated)

    def _codes(self, ctx: Context, column: str) -> list[Finding]:
        col = quote(column)
        sql = (f"SELECT {col}, COUNT(*) FROM {quote(ctx.table)}{ctx.where()} "
               f"GROUP BY 1 ORDER BY 2 DESC, 1")
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        rows = evidence.expected
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
            return []
        listed = ", ".join(f"{v} ({int(n):,})" for v, n in rows[:_MAX_LISTED])
        assertion = Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(f"Holds {len(rows)} distinct values: {listed}"
                       f"{' ...' if len(rows) > _MAX_LISTED else ''}."),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        unglossed = self._unglossed(ctx, column,
                                   [str(v) for v, _ in rows if v is not None])
        if not unglossed:
            return [Finding(assertion)]
        proposal = self._propose(ctx, column, unglossed)
        question = Question(
            subject=ctx.subject(column),
            text=(f"{len(unglossed)} of the {len(rows)} values in {column} have no "
                  f"definition in any available documentation: "
                  f"{', '.join(unglossed[:_MAX_LISTED])}. What do they mean?"),
            proposed_answer=proposal,
            options=("the proposal is correct",
                     "the proposal is partly correct",
                     "the proposal is wrong",
                     "unsure"),
            basis=assertion.id, cost_seconds=30,
        )
        return [Finding(assertion, question,
                        impact=len(unglossed) / max(len(rows), 1))]

    def _unglossed(self, ctx: Context, column: str, values: list[str]) -> list[str]:
        """A value is glossed if it appears literally in the dictionary's own
        remarks for this column. Pure substring test - no inference."""
        if ctx.dictionary is None:
            return values
        declared = ctx.dictionary.get(column)
        remarks = (declared.remarks if declared else "") or ""
        return [v for v in values if v and v not in remarks]

    def _propose(self, ctx: Context, column: str, unglossed: list[str]) -> str:
        """Modal leading phrase of the descriptions attached to each code."""
        desc = _description_column(ctx)
        if desc is None:
            return ("No description column is available to infer a meaning from; "
                    "these are likely internal codes needing a human definition.")
        parts: list[str] = []
        for value in unglossed[:_MAX_LISTED]:
            row = ctx.conn.execute(f"""
                SELECT phrase, n, SUM(n) OVER () FROM (
                  SELECT array_to_string(
                           list_slice(str_split(upper({quote(desc)}), ' '), 1, 2),
                           ' ') AS phrase, COUNT(*) AS n
                  FROM {quote(ctx.table)} WHERE {quote(column)} = ?
                  GROUP BY 1 ORDER BY 2 DESC LIMIT 1)
            """, [value]).fetchone()
            if row and row[2] and row[1] / row[2] >= _MODAL_PREFIX_SHARE:
                parts.append(f'{value}: descriptions are mostly "{row[0]} ..."')
            else:
                parts.append(f"{value}: descriptions show no consistent pattern")
        return "; ".join(parts)

    def _formats(self, ctx: Context, column: str) -> list[Finding]:
        """Values in more than one format class mean the column holds more than one
        kind of thing. A LOCATION column, for example, can mix building codes with
        shop and crew codes."""
        if _mean_tokens(ctx, column) > _PROSE_TOKEN_LIMIT:
            return []
        col = quote(column)
        sig = shape_signature(col)
        sql = (f"SELECT {sig} AS shape, COUNT(*) AS rows, "
               f"MIN({col}) AS example FROM {quote(ctx.table)} "
               f"WHERE {col} IS NOT NULL AND {col} <> '' "
               f"GROUP BY 1 ORDER BY 2 DESC, 1")
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        rows = evidence.expected
        if not isinstance(rows, list) or len(rows) < 2 or not isinstance(rows[0], list):
            return []
        dominant = rows[0]
        others = rows[1:]
        other_rows = sum(int(r[1]) for r in others)
        total_rows = sum(int(r[1]) for r in rows)
        examples = ", ".join(str(r[2]) for r in others[:_MAX_LISTED])
        assertion = Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(
                f"Values fall into {len(rows)} distinct format classes. The dominant "
                f"class is {dominant[0]} (example {dominant[2]}, {int(dominant[1]):,} "
                f"rows); {other_rows:,} rows use a different format, for example: "
                f"{examples}. The column therefore holds more than one kind of "
                f"identifier, and filtering as if it held one will silently drop rows."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        question = Question(
            subject=ctx.subject(column),
            text=(f"{column} holds {len(rows)} different value formats. What are the "
                  f"non-dominant ones ({examples})?"),
            proposed_answer=(f"A second kind of identifier stored in the same column "
                             f"as the dominant {dominant[0]} format."),
            options=("a second kind of identifier",
                     "invalid or legacy values",
                     "the same kind of thing, formatted differently",
                     "unsure"),
            basis=assertion.id, cost_seconds=30,
        )
        return [Finding(assertion, question,
                        impact=other_rows / total_rows if total_rows else 0.0)]

    def _families(self, ctx: Context, column: str) -> list[Finding]:
        """Near-duplicate value families in a free-text column. The question "are
        these variant descriptions one category?" is exactly this check, and a
        free-text column usually holds more variants than anyone would list."""
        col = quote(column)
        stem = (f"CASE WHEN strpos({col}, ',') > 0 "
                f"THEN trim(split_part({col}, ',', 1)) ELSE trim({col}) END")
        sql = f"""
            SELECT stem, COUNT(*) AS variants FROM (
              SELECT DISTINCT {stem} AS stem, {col} AS full_value
              FROM {quote(ctx.table)} WHERE {col} IS NOT NULL AND {col} <> ''
            ) GROUP BY 1 HAVING COUNT(*) >= {_MIN_FAMILY_VARIANTS}
            ORDER BY 2 DESC, 1
        """
        evidence = make_evidence(ctx.conn, sql, ctx.today)
        rows = evidence.expected
        if not isinstance(rows, list) or not rows:
            return []
        if not isinstance(rows[0], list):
            rows = [rows]
        listed = ", ".join(f"{s} ({int(n)} variants)" for s, n in rows[:_MAX_LISTED])
        assertion = Assertion(
            type=self.type, subject=ctx.subject(column),
            statement=(
                f"{len(rows)} value families have more than one variant spelling: "
                f"{listed}{' ...' if len(rows) > _MAX_LISTED else ''}. Grouping on "
                f"the raw value splits each family into separate categories."
            ),
            tier=Tier.MEASURED, evidence=(evidence,),
        )
        question = Question(
            subject=ctx.subject(column),
            text=(f"{column} contains {len(rows)} families of near-duplicate values "
                  f"(for example {rows[0][0]}, with {int(rows[0][1])} variants). "
                  f"Should variants within a family count as one category?"),
            proposed_answer=("Yes - variants are sub-types and should roll up to the "
                             "family for counting."),
            options=("yes - roll up to the family",
                     "no - each variant is its own category",
                     "depends on the family",
                     "unsure"),
            basis=assertion.id, cost_seconds=25,
        )
        return [Finding(assertion, question)]
