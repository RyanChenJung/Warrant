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
#53's format; composing the store itself uses #50's claims and warrant kinds. No model is called.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from warrant.defects.inject import Defect
from warrant.store.claims import PredictedOutcome
from warrant.write_line.judging import slot_order
from warrant.write_line.selector import least_confident, seeded_permutation

Score = tuple[float, float] | None  # (agreement, mean confidence), or None: no sample-1 claim to rank


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
        if (keys != ["agreement", "mean_confidence", "seeded_permutation"]
                or not str(rule.get("order", "")).startswith("lexicographic")
                or "samples 2 to 10" not in agreement):
            raise ValueError(f"the freeze's confidence combination is not the one built here: {keys}")
        if global_part["matched_asks"].get("tie_break") != "seeded_permutation":
            raise ValueError("the freeze's matched asks break ties another way")
        return cls(seed=global_part["seeds"]["matched_asks_tie_break"])


def settlement_ask_count(predictions: Mapping) -> int:
    """k: the slots the settlement rule leaves to a person, those not predicted agent alone, in the
    committed predictions (`matched_asks.k`)."""
    return sum(claim["outcome"] != PredictedOutcome.AGENT_ALONE.value for claim in predictions["claims"].values())


def _slot_index(sample: Mapping, defect: Defect) -> int | None:
    """The index of the first claim in a sample that fills the defect's slot: kind and subject equal."""
    for index, claim in enumerate(sample.get("claims") or ()):
        slot = claim.get("slot") or {}
        if (slot.get("claim_kind"), slot.get("subject")) == (defect.slot.claim_kind, defect.slot.subject):
            return index
    return None


def scores(records: Sequence[Mapping], defects: Iterable[Defect], rule: CombinationRule) -> dict[str, Score]:
    """Each slot's (agreement, mean confidence), or None where sample 1 has no claim on it, or has one
    the judge did not finish judging."""
    samples = {(r["database"], r["sample"]): r for r in records if r.get("record") == "sample"}
    profiles = {(r["defect"], r["sample"], r["index"]): r["labels"]
                for r in records if r.get("record") == "judgement" and r.get("complete")}
    found: dict[str, Score] = {}
    for defect in defects:
        if not defect.readings:
            continue
        claims = {}
        for number in range(1, rule.samples + 1):
            sample = samples.get((defect.database, number))
            index = None if sample is None or sample.get("failure") else _slot_index(sample, defect)
            if index is not None:
                claims[number] = (sample["claims"][index]["confidence"], profiles.get((defect.id, number, index)))
        first = claims.get(1)
        if first is None or first[1] is None:
            found[defect.id] = None
            continue
        agreeing = [confidence for number, (confidence, profile) in claims.items()
                    if number > 1 and profile is not None and profile == first[1]]
        found[defect.id] = (len(agreeing) / (rule.samples - 1), (first[0] + sum(agreeing)) / (1 + len(agreeing)))
    return found


def ranking(found: Mapping[str, Score], defects: Iterable[Defect], rule: CombinationRule) -> list[str]:
    """The defect ids, least confident first: slots without a sample-1 claim first, then by agreement
    and mean confidence, ties broken by the seeded permutation, a later slot being less confident."""
    by_slot = {slot_order(d): d.id for d in defects if d.id in found}
    permutation = [by_slot[slot] for slot in seeded_permutation(by_slot, rule.seed)]
    keyed = {defect: (0, 0.0, 0.0) if score is None else (1, *score) for defect, score in found.items()}
    return list(least_confident(keyed, len(keyed), permutation))


def with_sample_one_claim(records: Sequence[Mapping], defects: Iterable[Defect]) -> set[str]:
    """The slots sample 1 wrote a claim on, judged or not."""
    first = {r["database"]: r for r in records if r.get("record") == "sample" and r["sample"] == 1}
    return {d.id for d in defects
            if d.database in first and not first[d.database].get("failure") and _slot_index(first[d.database], d) is not None}


def allocation(order: Sequence[str], k: int, claimed: set[str]) -> dict[str, str | None]:
    """Each slot's source under the confidence rule: `person` for its k least confident slots,
    `agent` for the rest that sample 1 wrote a claim on, None (empty) for the rest."""
    return {defect: "person" if position < k else ("agent" if defect in claimed else None)
            for position, defect in enumerate(order)}
