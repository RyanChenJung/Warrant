"""The knowledge stores the allocation rules compose (#50), one per rule and database.

A question is given only its own database's store. A store lists its slots' claims in slot order
(database, claim kind, subject), then the agent's out-of-slot claims as sample 1 wrote them, so the same
claims read the same under every rule (#53, decided 2026-10-21). By rule:

- `empty`: nothing;
- `all_person`: every slot's reference claim, from the person;
- `all_agent`: sample 1's claim on each slot it wrote one on, and its out-of-slot claims;
- `settlement`: sample 1's claim on each settled slot (predicted agent alone), the reference claim on
  every other slot whatever the agent wrote there, and the out-of-slot claims. A settled slot with no
  agent claim stays empty, so the person asks stay at the frozen k (#50, 2026-10-21);
- `confidence`: the reference claim on the k slots the confidence ranking puts least confident,
  sample 1's claim on each other slot it wrote one on, and the out-of-slot claims (#51); the ranking
  and the allocation are `confidence.py`'s.

The `_abstain` rules are the same rules over the `abstain` variant's sample 1 (ADR 0012); `empty` and
`all_person` read no sample. A claim fills a slot when its kind and subject equal the slot's, as the
agent wrote them; the first such claim fills it, and a later one is out-of-slot. Each claim carries the
warrant kind and Toulmin record its source gets on that slot (`warrants.py`), and its slot's predicted
outcome. No model is called.
"""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass

from warrant.agent.write_claims import WrittenClaim, parse
from warrant.defects.inject import Defect
from warrant.store.claims import Claim, KnowledgeStore, PredictedOutcome, Source, Toulmin, WarrantKind
from warrant.write_line.confidence import slot_claim_index
from warrant.write_line.judging import slot_order
from warrant.write_line.warrants import PERSON_BACKING, SlotWarrant, claim_for, out_of_slot_claim

# Each rule id and the prompt variant whose samples it reads (ADR 0012), None for a rule that reads none.
RULES = {
    "empty": None,
    "all_person": None,
    "all_agent": "confident",
    "settlement": "confident",
    "confidence": "confident",
    "all_agent_abstain": "abstain",
    "settlement_abstain": "abstain",
    "confidence_abstain": "abstain",
}


def variant_of(rule: str) -> str | None:
    if rule not in RULES:
        raise ValueError(f"unknown allocation rule: {rule!r}")
    return RULES[rule]


@dataclass(frozen=True)
class ComposedStore:
    """One rule's store on one database: each of its slots' claim, or None for an empty slot, and the
    agent's out-of-slot claims."""

    slots: dict[str, Claim | None]
    out_of_slot: tuple[Claim, ...] = ()

    @property
    def store(self) -> KnowledgeStore:
        return KnowledgeStore(tuple(c for c in self.slots.values() if c is not None) + self.out_of_slot)


def written_claims(sample: Mapping) -> tuple[WrittenClaim, ...]:
    """A sample record's claims, with the battery findings they cite, which the record leaves to its
    output: its last output is the answer the claims were parsed from. A failed sample has none."""
    if sample.get("failure"):
        return ()
    claims = parse(sample["outputs"][-1])
    stored = [(c["slot"]["claim_kind"], c["slot"]["subject"], c["statement"], c["confidence"]) for c in sample["claims"]]
    if [(c.claim_kind, c.subject, c.statement, c.confidence) for c in claims] != stored:
        raise ValueError(f"{sample['database']} sample {sample['sample']}: the record's claims differ from its output")
    return claims


def _person_claim(defect: Defect, warrants: Mapping[str, SlotWarrant]) -> Claim:
    if defect.id in warrants:
        return claim_for(defect, warrants[defect.id], Source.PERSON, defect.reference_claim)
    # A defect without a reading set (a tracer-bullet fixture) has no prediction to give a warrant.
    return Claim(defect.slot, defect.reference_claim, Source.PERSON, WarrantKind.NONE, Toulmin(backing=PERSON_BACKING))


def compose(rule: str, database: str, defects: Iterable[Defect], warrants: Mapping[str, SlotWarrant],
            sample: Mapping | None = None, sources: Mapping[str, str | None] | None = None) -> ComposedStore:
    """The rule's store on the database, from `sample`, the sample-1 record of the rule's variant on it,
    and for the confidence rule `sources`, its allocation: each slot's source, `person`, `agent` or
    None (`confidence.allocation`)."""
    variant = variant_of(rule)
    base = rule.removesuffix("_abstain")
    mine = sorted((d for d in defects if d.database == database), key=slot_order)
    if base == "empty":
        return ComposedStore({d.id: None for d in mine})
    if base == "all_person":
        return ComposedStore({d.id: _person_claim(d, warrants) for d in mine})
    if base == "confidence" and sources is None:
        raise ValueError(f"the {rule} rule needs its allocation from the confidence ranking")
    if sample is None:
        raise ValueError(f"the {rule} rule needs sample 1 of the {variant} variant on {database}")
    if missing := [d.id for d in mine if d.id not in warrants]:
        raise ValueError(f"the {rule} rule needs every slot's predicted outcome; none for {', '.join(missing)}")
    claims = written_claims(sample)
    taken = {d.id: slot_claim_index(sample, d) for d in mine} if claims else {}
    slots: dict[str, Claim | None] = {}
    for d in mine:
        warrant, index = warrants[d.id], taken.get(d.id)
        to_person = (warrant.outcome != PredictedOutcome.AGENT_ALONE if base == "settlement"
                     else base == "confidence" and sources.get(d.id) == "person")
        if to_person:
            slots[d.id] = claim_for(d, warrant, Source.PERSON, d.reference_claim)
        elif index is not None:
            slots[d.id] = claim_for(d, warrant, Source.AGENT, claims[index].statement, claims[index].cites)
        else:
            slots[d.id] = None
    used = set(taken.values())
    out = tuple(out_of_slot_claim(c.claim_kind, c.subject, c.statement, c.cites)
                for i, c in enumerate(claims) if i not in used)
    return ComposedStore(slots, out)


def store_record(rule: str, composed: Mapping[str, ComposedStore], defects: Iterable[Defect],
                 scores: Mapping[str, tuple | None] | None = None, ranking: list[str] | None = None) -> dict:
    """The rule's `store` record (#53): every frozen slot's claim as its source, warrant kind and Toulmin
    record, its fields left out where empty, or None for an empty slot; and the person asks per claim
    kind, every kind of the freeze a key. The confidence rule's also carries each slot's score,
    (agreement, mean confidence) or None, and the ranking, least confident first."""
    defects = list(defects)
    slots, asks = {}, {d.slot.claim_kind.value: 0 for d in defects}
    for d in defects:
        store = composed.get(d.database)
        claim = None if store is None else store.slots.get(d.id)
        if claim is None:
            slots[d.id] = None
            continue
        slots[d.id] = {"source": claim.source.value, "warrant": claim.warrant.value,
                       "toulmin": {field: value for field, value in asdict(claim.toulmin).items() if value}}
        if claim.source == Source.PERSON:
            asks[d.slot.claim_kind.value] += 1
    record = {"record": "store", "rule": rule, "slots": slots, "person_asks": asks}
    if scores is not None:
        record["scores"] = {d: None if score is None else {"agreement": float(score[0]), "mean_confidence": float(score[1])}
                            for d, score in scores.items()}
        record["ranking"] = list(ranking)
    return record
