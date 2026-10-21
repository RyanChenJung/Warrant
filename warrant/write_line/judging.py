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
from warrant.write_line.config import Config


def slot_order(defect: Defect) -> tuple[str, str, str]:
    return (defect.database, defect.slot.claim_kind, defect.slot.subject)


def reading_orders(freeze_defects: Iterable[Defect], seed: int) -> dict[str, tuple[str, ...]]:
    """Each defect's reading ids in its slot's reading order, by defect id.

    `freeze_defects` must be every defect of the freeze, of every database: one generator runs over
    all the slots in order, so a subset, such as one database's defects for a claim-writing run on
    that database, draws other orders. `reading_orders_for` takes them from a configuration.
    """
    rng = random.Random(seed)
    orders = {}
    for defect in sorted((d for d in freeze_defects if d.readings), key=slot_order):
        ids = [reading["id"] for reading in defect.readings]
        rng.shuffle(ids)
        orders[defect.id] = tuple(ids)
    return orders


def reading_orders_for(config: Config) -> dict[str, tuple[str, ...]]:
    """The reading orders of a configuration on a freeze: drawn over all its defects, which are the
    freeze's, with the freeze's judge seed. For the judge's validation and for claim writing (#51)."""
    if config.global_part is None:
        raise ValueError("the reading orders need the global part's judge seed")
    return reading_orders(config.defects, config.global_part["seeds"]["judge_reading_order"])


def judge_request(defect: Defect, claim: str, order: tuple[str, ...]) -> JudgeRequest:
    statements = {reading["id"]: reading["statement"].strip() for reading in defect.readings}
    return JudgeRequest(defect.slot, claim.strip(), tuple((reading, statements[reading]) for reading in order))
