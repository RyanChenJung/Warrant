"""The warrant kind and Toulmin record of each claim a store holds (#50).

Computed from the committed predictions (#37: each reading's database, whether the battery tells it
from the true reading, and the slot's predicted outcome) and the freeze's declared reading kinds,
with no model call. The thin write line has no authoritative records, so no claim carries a record
warrant, and:

- a claim on a settled slot (predicted agent alone), the agent's or the reference claim, carries a
  data warrant, backed by the vendored battery and check; an agent claim's Toulmin data is the
  battery findings it cites;
- on a slot predicted person only, the reference claim carries a declaration warrant if some rival
  the battery cannot tell from the true reading, under which the claim fails, is a meaning-only
  reading the freeze declares a convention; otherwise a testimony warrant, every such rival either
  changing the database (a data part the battery missed) or being declared provenance;
- on a slot predicted both, the reference claim carries a testimony warrant;
- a testimony warrant's qualifier says what could settle the claim later, by those surviving
  rivals: a stronger battery for rivals that change the database, a record of how the data came to
  be for provenance rivals, both when both occur;
- any other agent claim carries none.

The person's claims are backed by the person. These are the decisions of 2026-10-21 on #50. A warrant
kind is what the rule grants a claim on that slot from that source, not a verdict on whether the
claim is true: whether an agent claim holds is the judge's to say (a wrong write, #51, #53).

Two cases the rule does not cover are refused rather than guessed: a slot predicted both with a
surviving convention rival, and a testimony warrant with nothing to say what could settle it. No
frozen slot is either; a second freeze (ADR 0011) settles them before it is injected.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from warrant.defects.inject import Defect
from warrant.store.claims import Claim, ClaimKind, PredictedOutcome, Slot, Source, Toulmin, WarrantKind

BATTERY_BACKING = "the vendored battery and check"
PERSON_BACKING = "the person"
STRONGER_BATTERY = "a stronger battery could settle it"
PROVENANCE_RECORD = "a record of how the data came to be could settle it"


@dataclass(frozen=True)
class SlotWarrant:
    """What a claim on one slot carries: by source, its warrant kind, and a testimony's qualifier."""

    outcome: PredictedOutcome
    agent: WarrantKind
    person: WarrantKind
    qualifier: str = ""


def _surviving_rivals(defect: Defect, readings: Mapping[str, Mapping]) -> tuple[list[dict], str]:
    """The rivals the battery cannot tell from the true reading and under which the reference claim
    fails, and the true reading's database."""
    for reading in defect.readings:
        committed = readings.get(reading["id"])
        if committed is None:
            raise ValueError(f"{defect.id}: reading {reading['id']!r} has no committed prediction")
        if committed["holds"] != reading["holds"]:
            raise ValueError(f"{defect.id}: reading {reading['id']!r}'s holds differs between the freeze and the predictions")
    true = next(r for r in defect.readings if r.get("is_true"))
    true_database = readings[true["id"]]["database"]
    rivals = [r for r in defect.readings
              if not r.get("is_true") and not readings[r["id"]]["differs"] and not r["holds"]]
    return rivals, true_database


def slot_warrants(defects: Iterable[Defect], predictions: Mapping) -> dict[str, SlotWarrant]:
    """Each slot's warrants, by defect id, for every defect with a reading set."""
    found = {}
    for defect in defects:
        if not defect.readings:
            continue
        committed = predictions["claims"].get(defect.id)
        if committed is None:
            raise ValueError(f"{defect.id}: no committed prediction for this slot")
        outcome = PredictedOutcome(committed["outcome"])
        if outcome == PredictedOutcome.AGENT_ALONE:
            found[defect.id] = SlotWarrant(outcome, WarrantKind.DATA, WarrantKind.DATA)
            continue
        rivals, true_database = _surviving_rivals(defect, committed["readings"])
        if not rivals:
            raise ValueError(f"{defect.id}: predicted {outcome.value}, but no rival survives under which the claim fails")
        convention = any(r.get("form") == "meaning_only" and r.get("kind") == "convention" for r in rivals)
        if outcome == PredictedOutcome.PERSON_ONLY and convention:
            found[defect.id] = SlotWarrant(outcome, WarrantKind.NONE, WarrantKind.DECLARATION)
            continue
        if convention:
            raise ValueError(f"{defect.id}: predicted both with a surviving convention rival, a case #50's rule does not cover")
        parts = []
        if any(committed["readings"][r["id"]]["database"] != true_database for r in rivals):
            parts.append(STRONGER_BATTERY)
        if any(r.get("kind") == "provenance" for r in rivals):
            parts.append(PROVENANCE_RECORD)
        if not parts:
            raise ValueError(f"{defect.id}: a testimony warrant whose surviving rivals neither change the database "
                             "nor are declared provenance, so nothing says what could settle it")
        found[defect.id] = SlotWarrant(outcome, WarrantKind.NONE, WarrantKind.TESTIMONY, "; ".join(parts))
    return found


def claim_for(defect: Defect, warrant: SlotWarrant, source: Source, statement: str,
              cites: Sequence[str] = ()) -> Claim:
    """A claim on the defect's slot, with the warrant kind and Toulmin record its source gives it."""
    kind = warrant.agent if source == Source.AGENT else warrant.person
    backing = {WarrantKind.DATA: BATTERY_BACKING, WarrantKind.TESTIMONY: PERSON_BACKING,
               WarrantKind.DECLARATION: PERSON_BACKING}.get(kind, "")
    toulmin = Toulmin(
        data="; ".join(cites) if source == Source.AGENT else "",
        backing=backing,
        qualifier=warrant.qualifier if kind == WarrantKind.TESTIMONY else "",
    )
    return Claim(defect.slot, statement.strip(), source, kind, toulmin, warrant.outcome)


def out_of_slot_claim(claim_kind: str, subject: str, statement: str, cites: Sequence[str] = ()) -> Claim:
    """An agent claim that fills no slot, kept as the agent wrote its kind and subject, a later claim
    on an already filled slot included: no warrant and no predicted outcome. A kind outside the five
    is kept as written too (#53), so it can never match a slot."""
    kind = ClaimKind(claim_kind) if claim_kind in {k.value for k in ClaimKind} else claim_kind
    return Claim(Slot(kind, subject), statement.strip(), Source.AGENT, WarrantKind.NONE,
                 Toulmin(data="; ".join(cites)), None)
