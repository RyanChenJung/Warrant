"""The matched-asks selector (#120): exactly k items, the least confident, ties broken by the slots'
seeded permutation (freeze, global.confidence_combination and global.matched_asks)."""

import random

import pytest

from warrant.write_line.selector import least_confident, seeded_permutation

SEED = 20261012  # the freeze's seeds.matched_asks_tie_break
SLOTS = [
    ("crypto", "coverage", "orders"),
    ("alien", "value_meaning", "observatories.seeingprofile"),
    ("crypto", "column_formula", "accountbalances.walletsum"),
]


def test_the_tie_break_order_is_the_slots_in_database_claim_kind_subject_order_shuffled_by_the_seed():
    ordered = sorted(SLOTS)
    random.Random(SEED).shuffle(ordered)
    assert seeded_permutation(SLOTS, SEED) == ordered
    assert seeded_permutation(list(reversed(SLOTS)), SEED) == ordered  # whatever order they come in


@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_the_selector_returns_exactly_k_items_the_least_confident_first(k):
    scores = {SLOTS[0]: (0.2, 0.9), SLOTS[1]: (0.1, 0.5), SLOTS[2]: (0.8, 0.4)}
    chosen = least_confident(scores, k, seeded_permutation(SLOTS, SEED))
    assert chosen == (SLOTS[1], SLOTS[0], SLOTS[2])[:k]


def test_ties_are_broken_by_the_seeded_permutation_where_earlier_is_more_confident():
    permutation = seeded_permutation(SLOTS, SEED)
    scores = dict.fromkeys(SLOTS, (0.5, 0.5))
    assert least_confident(scores, 2, permutation) == (permutation[2], permutation[1])
    # The same seed gives the same choice every time.
    assert least_confident(scores, 2, seeded_permutation(SLOTS, SEED)) == least_confident(scores, 2, permutation)


def test_a_tie_on_the_first_key_is_broken_by_the_next_key_before_the_permutation():
    permutation = seeded_permutation(SLOTS, SEED)
    scores = {SLOTS[0]: (0.5, 0.9), SLOTS[1]: (0.5, 0.1), SLOTS[2]: (0.9, 0.0)}
    assert least_confident(scores, 1, permutation) == (SLOTS[1],)


@pytest.mark.parametrize("k", [-1, 4])
def test_a_k_outside_zero_to_the_number_of_items_is_refused(k):
    with pytest.raises(ValueError, match="k"):
        least_confident(dict.fromkeys(SLOTS, (0.5,)), k, seeded_permutation(SLOTS, SEED))


def test_scores_and_permutation_must_name_the_same_items():
    with pytest.raises(ValueError, match="permutation"):
        least_confident(dict.fromkeys(SLOTS, (0.5,)), 1, seeded_permutation(SLOTS[:2], SEED))
