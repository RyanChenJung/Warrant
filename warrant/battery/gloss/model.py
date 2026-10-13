"""Core records. The product principles in docs/SPEC.md 2 are enforced here as
constructor invariants, so they cannot be violated by a contributor who has not
read the spec."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

# A path-shaped literal in evidence SQL means the statement is not portable and
# leaks our filesystem layout. Evidence must reference logical table names.
_PATH_LIKE = re.compile(r"""['"]\s*(/|[A-Za-z]:\\|\./|\.\./)""")


class AssertionType(str, Enum):
    """The seven types of docs/SPEC.md 3. Fixed for every customer."""

    SCOPE = "SCOPE"    # 1 - which population
    GRAIN = "GRAIN"    # 2 - what one row is
    FIELD = "FIELD"    # 3 - meaning, unit, precision, direction
    VALUE = "VALUE"    # 4 - codes, nulls, sentinels
    LINK = "LINK"      # 5 - join path, cardinality, authority
    RULE = "RULE"      # 6 - how a business concept is computed
    LIMIT = "LIMIT"    # 7 - prohibitions, absences, coverage


class Tier(str, Enum):
    """P3: a source tier, never a 0-1 score."""

    MEASURED = "MEASURED"
    CONFIRMED = "CONFIRMED"
    GUESSED = "GUESSED"


@dataclass(frozen=True)
class SqlEvidence:
    """P2: a statement a third party can re-run, plus what it returned for us."""

    sql: str
    expected: Any
    measured_at: str

    def __post_init__(self) -> None:
        if not self.sql.strip():
            raise ValueError("evidence SQL may not be empty")
        if _PATH_LIKE.search(self.sql):
            raise ValueError(
                "evidence SQL must reference a logical table name, not a filesystem "
                f"path: {self.sql[:80]!r}"
            )


@dataclass(frozen=True)
class QuoteEvidence:
    """Document evidence. v1 does not read documents, but the dictionary's own
    REMARKS text is quoted, so this type is used by the RULE detector for
    dictionary quotes and by growth events for snapshot citations."""

    quote: str
    source: str
    locator: str

    def __post_init__(self) -> None:
        if not self.quote.strip():
            raise ValueError("quote evidence may not be empty")


Evidence = SqlEvidence | QuoteEvidence


@dataclass(frozen=True)
class Assertion:
    type: AssertionType
    subject: str
    statement: str
    tier: Tier
    evidence: tuple[Evidence, ...] = ()
    valid_from: str | None = None
    valid_to: str | None = None
    author: str = "gloss"
    conflicts_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("an assertion must state something")
        if self.tier is Tier.MEASURED:
            # v1 is structured-data only, so "re-runnable" means SQL specifically.
            # When unstructured sources land this widens to any Evidence member.
            has_sql = any(isinstance(e, SqlEvidence) for e in self.evidence)
            # One narrow exemption. A statement about change *over time* cannot be
            # proved by any query against today's data; its evidence is a pair of
            # snapshots, cited by date. Ordinary quote evidence does not qualify.
            from_snapshot = any(
                isinstance(e, QuoteEvidence) and e.source.startswith("snapshot:")
                for e in self.evidence
            )
            if not (has_sql or from_snapshot):
                raise ValueError(
                    "P2: a MEASURED assertion must carry re-runnable SQL evidence"
                )
        if self.tier is Tier.GUESSED and self.evidence:
            raise ValueError(
                "P1: a GUESSED assertion may not carry evidence - evidence would "
                "make it MEASURED. A guess is a candidate question, not a fact."
            )
        if self.tier is Tier.CONFIRMED and self.author == "gloss":
            raise ValueError(
                "P1: a CONFIRMED assertion requires a named human author"
            )

    @property
    def id(self) -> str:
        """Stable across runs so YAML diffs stay reviewable."""
        payload = json.dumps(
            [self.type.value, self.subject, self.statement], sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Question:
    """P4: never a blank field. The human corrects a proposal; they do not author."""

    subject: str
    text: str
    proposed_answer: str
    options: tuple[str, ...]
    basis: str
    cost_seconds: int
    priority: float = 0.0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a question must ask something")
        if not self.proposed_answer.strip():
            raise ValueError(
                "P4: every question must ship with a proposed answer, so the human "
                "is correcting rather than authoring"
            )
        if len(self.options) < 2:
            raise ValueError(
                "P4: a question must be option-shaped (at least two options); an "
                "open prose prompt costs minutes and will not be answered"
            )


@dataclass(frozen=True)
class Finding:
    """What a detector returns: a fact, and optionally the one thing a human must
    settle before the fact is actionable.

    `impact` is the fraction of rows the anomaly touches, where a detector can say.
    Ranking uses it to break ties inside a type; detectors that cannot measure it
    leave it at 0.0 and get the baseline.
    """

    assertion: Assertion
    question: Question | None = None
    impact: float = 0.0
