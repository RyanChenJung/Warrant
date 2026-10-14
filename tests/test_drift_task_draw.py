import pytest

from warrant.data.release import Release
from warrant.maintenance.draw import EXCLUDED, SEED, candidates, new_value

RELEASE = Release(dataset="example/release", revision="abc123", databases=("alien", "crypto", "robot", "solar"))


def entry(id, definition):
    return {"id": id, "knowledge": f"Entry {id}", "definition": definition}


KNOWLEDGE_BASES = {
    "alien": [entry(0, "A high LIF is above 0.5.")],
    "crypto": [entry(0, "A large order is above 1000.")],
    "robot": [entry(0, "An old robot is older than 3 years."), entry(1, "A robot is idle when it is not running.")],
    "solar": [entry(0, "A hot panel is above 80 degrees."), entry(1, "Output ratio = actual / rated.")],
}


def test_the_order_is_fixed_by_the_seed_and_holds_every_entry_stating_a_number_once():
    order = candidates(RELEASE, KNOWLEDGE_BASES)
    assert order == candidates(RELEASE, KNOWLEDGE_BASES, seed=SEED)
    assert sorted((c.database, c.entry) for c in order) == [("robot", 0), ("solar", 0)]
    assert {c.direction for c in order} <= {"up", "down"}


def test_the_write_line_databases_are_left_out():
    assert set(EXCLUDED) == {"crypto", "alien"}
    assert not [c for c in candidates(RELEASE, KNOWLEDGE_BASES) if c.database in EXCLUDED]


def test_another_seed_can_give_another_order():
    bases = {"robot": [entry(i, f"Threshold {i}0.") for i in range(10)]}
    release = Release("example/release", "abc123", ("robot",))
    assert candidates(release, bases) != candidates(release, bases, seed=SEED + 1)


@pytest.mark.parametrize(
    "old, direction, new",
    [
        ("0.5", "up", "0.6"),
        ("0.5", "down", "0.4"),
        ("80", "up", "96"),
        ("80", "down", "64"),
        ("3", "up", "4"),
        ("0.05", "down", "0.04"),
        ("1,000,000", "up", "1,200,000"),
        ("2.5", "down", "2.0"),
    ],
)
def test_the_new_value_moves_the_old_by_20_percent_rounded_to_its_decimal_places(old, direction, new):
    assert new_value(old, direction) == new
