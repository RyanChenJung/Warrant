"""The knowledge-store format shared by both lines.

Every claim carries its slot, its source, its warrant kind and its Toulmin record; a write-line
claim also carries its slot's predicted outcome. Terms follow CONTEXT.md.
"""

from dataclasses import dataclass
from enum import StrEnum


class ClaimKind(StrEnum):
    COVERAGE = "coverage"
    GRAIN = "grain"
    VALUE_MEANING = "value_meaning"
    COLUMN_FORMULA = "column_formula"
    TERM_BOUNDARY = "term_boundary"


class WarrantKind(StrEnum):
    DATA = "data"
    RECORD = "record"
    TESTIMONY = "testimony"
    DECLARATION = "declaration"
    NONE = "none"


class Source(StrEnum):
    AGENT = "agent"
    PERSON = "person"


class PredictedOutcome(StrEnum):
    AGENT_ALONE = "agent_alone"
    BOTH = "both"
    PERSON_ONLY = "person_only"


@dataclass(frozen=True)
class Slot:
    """Where a claim belongs: its claim kind and subject (a table, a column or a named quantity)."""

    claim_kind: ClaimKind
    subject: str


@dataclass(frozen=True)
class Toulmin:
    data: str = ""
    inference_rule: str = ""
    backing: str = ""
    qualifier: str = ""
    rebuttal: str = ""


@dataclass(frozen=True)
class Claim:
    slot: Slot
    statement: str
    source: Source
    warrant: WarrantKind
    toulmin: Toulmin
    predicted_outcome: PredictedOutcome | None = None


@dataclass(frozen=True)
class KnowledgeStore:
    claims: tuple[Claim, ...] = ()
