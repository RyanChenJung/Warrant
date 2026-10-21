"""What the judge (#120) is given on a write-line slot: the claim and the slot's reading statements,
in the slot's reading order.

The order follows the freeze (global.judge.reading_order): for each slot in order of (database,
claim kind, subject), the slot's reading ids in declared order shuffled by one random.Random(judge
seed). It is drawn once per slot and shared by every claim on it and by all three calls, so splits
across calls measure repeat instability, not order effects.
"""

import random
from typing import Iterable

from warrant.agent.judge import JudgeRequest
from warrant.defects.inject import Defect


def slot_order(defect: Defect) -> tuple[str, str, str]:
    return (defect.database, defect.slot.claim_kind, defect.slot.subject)


def reading_orders(defects: Iterable[Defect], seed: int) -> dict[str, tuple[str, ...]]:
    """Each defect's reading ids in its slot's reading order, by defect id."""
    rng = random.Random(seed)
    orders = {}
    for defect in sorted((d for d in defects if d.readings), key=slot_order):
        ids = [reading["id"] for reading in defect.readings]
        rng.shuffle(ids)
        orders[defect.id] = tuple(ids)
    return orders


def judge_request(defect: Defect, claim: str, order: tuple[str, ...]) -> JudgeRequest:
    statements = {reading["id"]: reading["statement"].strip() for reading in defect.readings}
    return JudgeRequest(defect.slot, claim.strip(), tuple((reading, statements[reading]) for reading in order))
