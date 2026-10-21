"""The matched-asks selector (#120): the k least confident items, for a person.

Confidence is lexicographic and higher is more confident (freeze, global.confidence_combination);
its last key is the seeded permutation: the items in sorted order, for slots (database, claim kind,
subject), shuffled by random.Random(seed), earlier being more confident. The confidence rule (#51)
gives a person its k least confident slots; the maintenance line's escalation conditions (#46, future
work) would pick tasks the same way.
"""

import random
from typing import Hashable, Iterable, Mapping, Sequence


def seeded_permutation(items: Iterable[Hashable], seed: int) -> list:
    """The items in sorted order, shuffled by one random.Random(seed): the tie-break order."""
    ordered = sorted(items)
    random.Random(seed).shuffle(ordered)
    return ordered


def least_confident(scores: Mapping[Hashable, tuple], k: int, permutation: Sequence[Hashable]) -> tuple:
    """Exactly k items, least confident first: by their score tuples, then later in the permutation
    as less confident."""
    if set(permutation) != set(scores) or len(permutation) != len(scores):
        raise ValueError("the permutation must order exactly the scored items")
    if not 0 <= k <= len(scores):
        raise ValueError(f"k must be between 0 and {len(scores)}, not {k}")
    position = {item: index for index, item in enumerate(permutation)}
    ranked = sorted(scores, key=lambda item: (scores[item], -position[item]))
    return tuple(ranked[:k])
