"""The confidence rule's ranking (#51): which slots the confidence rule sends to a person.

Each slot's confidence comes from the claim-writing samples, by the freeze's combination rule
(`global.confidence_combination`), lexicographic and higher being more confident:

1. agreement: the share of samples 2 to 10 whose claim on the slot agrees with sample 1's, two claims
   agreeing when the judge gives them the same profile (`judge.same_profile_agrees`); a sample with no
   claim on the slot counts as disagreeing, and a slot where sample 1 has no claim ranks least
   confident;
2. mean confidence: the mean self-reported confidence of sample 1 and the samples agreeing with it;
3. the seeded permutation of the slots in (database, claim kind, subject) order, earlier being more
   confident (#120's selector).

The confidence rule gives a person its k least confident slots, k being the settlement rule's ask
count fixed when the predictions were committed (`global.matched_asks`), and leaves the rest to the
agent's claim from sample 1. A slot left to the agent with no sample-1 claim stays empty, as under
the settlement rule (#50, 2026-10-21). These functions read the sample and judgement records of
#53's format, of one run (the caller selects it); judging is done before the stores are composed
(#53), so a claim on a slot without a complete judgement is refused rather than ranked. Means are
exact (fractions of the confidences as written), so only real ties reach the permutation. Composing
the store itself uses #50's claims and warrant kinds. No model is called.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from numbers import Real

from warrant.defects.inject import Defect
from warrant.store.claims import PredictedOutcome
from warrant.write_line.judging import slot_order
from warrant.write_line.selector import least_confident, seeded_permutation

Score = tuple[Fraction, Fraction] | None  # (agreement, mean confidence), or None: no sample-1 claim


@dataclass(frozen=True)
class CombinationRule:
    """The freeze's confidence combination and the tie-break seed of its matched asks."""

    seed: int
    samples: int = 10

    @classmethod
    def from_freeze(cls, global_part: Mapping) -> "CombinationRule":
        """Read the rule from the freeze's global part, refusing one other than the rule built here:
        agreement over samples 2 to 10, then mean confidence, then the seeded permutation."""
        rule = global_part["confidence_combination"]
        keys = [next(iter(key)) for key in rule["keys"]]
        agreement = rule["keys"][0].get("agreement", "") if keys else ""
        if keys != ["agreement", "mean_confidence", "seeded_permutation"]:
            raise ValueError(f"the freeze's confidence combination is not the one built here: keys {keys}")
        if not str(rule.get("order", "")).startswith("lexicographic"):
            raise ValueError("the freeze's confidence combination is not the one built here: not lexicographic")
        if "samples 2 to 10" not in agreement:
            raise ValueError("the freeze's confidence combination is not the one built here: not samples 2 to 10")
        if global_part["matched_asks"].get("tie_break") != "seeded_permutation":
            raise ValueError("the freeze's matched asks break ties another way")
        return cls(seed=global_part["seeds"]["matched_asks_tie_break"])


def settlement_ask_count(predictions: Mapping) -> int:
    """k: the slots the settlement rule leaves to a person, those not predicted agent alone, in the
    committed predictions (`matched_asks.k`)."""
    return sum(claim["outcome"] != PredictedOutcome.AGENT_ALONE.value for claim in predictions["claims"].values())


def slot_claim_index(sample: Mapping, defect: Defect) -> int | None:
    """The index of the first claim in a sample that fills the defect's slot: kind and subject equal,
    as the agent wrote them (#53). A later claim on the same slot, or one in another shape, is
    out-of-slot."""
    for index, claim in enumerate(sample.get("claims") or ()):
        slot = claim.get("slot") if isinstance(claim, Mapping) else None
        if not isinstance(slot, Mapping):
            continue
        if (slot.get("claim_kind"), slot.get("subject")) == (defect.slot.claim_kind, defect.slot.subject):
            return index
    return None


def _confidence(sample: Mapping, index: int) -> Fraction:
    value = sample["claims"][index].get("confidence")
    if isinstance(value, bool) or not isinstance(value, Real) or not 0 <= value <= 1:
        raise ValueError(f"{sample['database']} sample {sample['sample']} claim {index}: "
                         f"confidence {value!r} is not a number from 0 to 1")
    return Fraction(str(value))


def _one_run(records: Sequence[Mapping]) -> None:
    runs = {r["run_id"] for r in records if "run_id" in r}
    if len(runs) > 1:
        raise ValueError(f"records of {len(runs)} runs; pass one run's records (#53 uses the first complete run)")


def scores(records: Sequence[Mapping], defects: Iterable[Defect], rule: CombinationRule) -> dict[str, Score]:
    """Each slot's (agreement, mean confidence), or None where sample 1 has no claim on it (a failed
    sample 1 included). Every sample of every database must have a record (a failed one is a record
    too), and every claim on a slot a complete judgement; otherwise the run is not ready for its
    stores and this refuses."""
    _one_run(records)
    samples: dict[tuple[str, int], Mapping] = {}
    for r in records:
        if r.get("record") == "sample":
            if (r["database"], r["sample"]) in samples:
                raise ValueError(f"two records of {r['database']} sample {r['sample']}")
            samples[(r["database"], r["sample"])] = r
    profiles: dict[tuple[str, int, int], Mapping] = {}
    for r in records:
        if r.get("record") == "judgement" and r.get("complete"):
            profiles.setdefault((r["defect"], r["sample"], r["index"]), r["labels"])  # the first complete one
    found: dict[str, Score] = {}
    for defect in defects:
        if not defect.readings:
            continue
        claims = {}
        for number in range(1, rule.samples + 1):
            sample = samples.get((defect.database, number))
            if sample is None:
                raise ValueError(f"no record of {defect.database} sample {number}")
            index = None if sample.get("failure") else slot_claim_index(sample, defect)
            if index is None:
                continue
            profile = profiles.get((defect.id, number, index))
            if profile is None:
                raise ValueError(f"{defect.id}: the claim of sample {number} has no complete judgement")
            claims[number] = (_confidence(sample, index), profile)
        if 1 not in claims:
            found[defect.id] = None
            continue
        first_confidence, first_profile = claims[1]
        agreeing = [c for number, (c, profile) in claims.items() if number > 1 and profile == first_profile]
        found[defect.id] = (Fraction(len(agreeing), rule.samples - 1),
                            (first_confidence + sum(agreeing)) / (1 + len(agreeing)))
    return found


def ranking(found: Mapping[str, Score], defects: Iterable[Defect], rule: CombinationRule) -> list[str]:
    """The defect ids, least confident first: slots without a sample-1 claim first, then by agreement
    and mean confidence, ties broken by the seeded permutation, a later slot being less confident. The
    permutation is drawn over every slot of the freeze, pooled across databases (`matched_asks.scope`),
    so `found` must score every defect with a reading set."""
    by_slot = {slot_order(d): d.id for d in defects if d.readings}
    if set(by_slot.values()) != set(found):
        raise ValueError("the ranking is pooled over every slot of the freeze; score them all")
    permutation = [by_slot[slot] for slot in seeded_permutation(by_slot, rule.seed)]
    keyed = {defect: (0, Fraction(0), Fraction(0)) if score is None else (1, *score) for defect, score in found.items()}
    return list(least_confident(keyed, len(keyed), permutation))


def with_sample_one_claim(records: Sequence[Mapping], defects: Iterable[Defect]) -> set[str]:
    """The slots sample 1 wrote a claim on, judged or not."""
    first = {r["database"]: r for r in records if r.get("record") == "sample" and r["sample"] == 1}
    return {d.id for d in defects
            if d.database in first and not first[d.database].get("failure")
            and slot_claim_index(first[d.database], d) is not None}


def allocation(order: Sequence[str], k: int, claimed: set[str]) -> dict[str, str | None]:
    """Each slot's source under the confidence rule: `person` for its k least confident slots,
    `agent` for the rest that sample 1 wrote a claim on, None (empty) for the rest."""
    return {defect: "person" if position < k else ("agent" if defect in claimed else None)
            for position, defect in enumerate(order)}
