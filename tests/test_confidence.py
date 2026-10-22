"""The confidence rule's ranking (#51, `global.confidence_combination`, `global.matched_asks`): each
slot's confidence from the claim-writing samples, lexicographic (agreement with sample 1, then the
mean self-reported confidence, then the seeded permutation), and the k least confident slots sent to
a person, k being the settlement rule's ask count from the committed predictions. It reads the
records of #53's format and calls no model."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from warrant.write_line.confidence import (
    CombinationRule,
    allocation,
    ranking,
    scores,
    settlement_ask_count,
    with_sample_one_claim,
)
from warrant.write_line.config import load_config

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "configs" / "write_line_pilot.yaml"
FREEZE = REPO / "freeze" / "write_line.yaml"
PREDICTIONS = REPO / "predictions" / "9cfd501f2182-write_line.json"
SLOTS = {
    "wallet-sum": ("column_formula", "accountbalances.walletsum"),
    "orders-cut": ("coverage", "orders"),
    "seeing-recode": ("value_meaning", "observatories.seeingprofile"),
}
DATABASE = {"wallet-sum": "crypto", "orders-cut": "crypto", "seeing-recode": "alien"}
A = {"r1": "holds", "r2": "fails"}  # one profile
B = {"r1": "fails", "r2": "holds"}  # another


@pytest.fixture
def config():
    return load_config(CONFIG)


@pytest.fixture
def rule():
    return CombinationRule.from_freeze(yaml.safe_load(FREEZE.read_text())["global"])


def claim(defect, confidence, statement="a claim"):
    kind, subject = SLOTS[defect]
    return {"slot": {"claim_kind": kind, "subject": subject}, "statement": statement, "confidence": confidence}


def records(spec):
    """Sample and judgement records from {defect: [(confidence, profile) or None for samples 1..10]}."""
    out = []
    for database in ("crypto", "alien"):
        for sample in range(1, 11):
            claims, judged = [], []
            for defect, per_sample in spec.items():
                if DATABASE[defect] != database or per_sample[sample - 1] is None:
                    continue
                confidence, profile = per_sample[sample - 1]
                judged.append({"record": "judgement", "defect": defect, "sample": sample, "index": len(claims),
                               "complete": True, "labels": profile})
                claims.append(claim(defect, confidence))
            out.append({"record": "sample", "database": database, "sample": sample, "claims": claims, "failure": ""})
            out.extend(judged)
    return out


def test_the_combination_rule_is_read_from_the_freezes_global_part(rule):
    raw = yaml.safe_load(FREEZE.read_text())["global"]
    assert rule.seed == raw["seeds"]["matched_asks_tie_break"] == 20261012
    assert rule.samples == 10


def test_a_combination_rule_other_than_the_one_built_here_is_refused():
    raw = yaml.safe_load(FREEZE.read_text())["global"]
    swapped = copy.deepcopy(raw)
    keys = swapped["confidence_combination"]["keys"]
    keys[0], keys[1] = keys[1], keys[0]
    with pytest.raises(ValueError, match="confidence combination"):
        CombinationRule.from_freeze(swapped)


def test_k_is_the_settlement_rules_ask_count_from_the_committed_predictions():
    assert settlement_ask_count(json.loads(PREDICTIONS.read_text())) == 2


def test_ten_agreeing_confident_samples_rank_above_disagreeing_ones(config, rule):
    spec = {
        "wallet-sum": [(0.9, A)] * 10,
        "orders-cut": [(0.9, A)] + [(0.9, B)] * 9,
        "seeing-recode": [(0.9, A)] * 10,
    }
    found = scores(records(spec), config.defects, rule)
    assert found["wallet-sum"] == (1.0, pytest.approx(0.9))
    assert found["orders-cut"] == (0.0, pytest.approx(0.9))
    assert ranking(found, config.defects, rule)[0] == "orders-cut"


def test_a_slot_where_sample_1_has_no_claim_ranks_least_confident(config, rule):
    spec = {
        "wallet-sum": [(0.1, A)] + [(0.1, B)] * 9,  # sample 1 alone, very unsure
        "orders-cut": [None] + [(0.99, A)] * 9,  # sample 1 wrote nothing here
        "seeing-recode": [(0.9, A)] * 10,
    }
    found = scores(records(spec), config.defects, rule)
    assert found["orders-cut"] is None
    assert ranking(found, config.defects, rule)[:2] == ["orders-cut", "wallet-sum"]


def test_a_missing_or_failed_sample_counts_as_disagreeing(config, rule):
    spec = {"wallet-sum": [(0.8, A)] * 5 + [None] * 5, "orders-cut": [(0.8, A)] * 10, "seeing-recode": [(0.8, A)] * 10}
    recs = records(spec)
    recs = [r for r in recs if not (r.get("record") == "sample" and r["database"] == "crypto" and r["sample"] == 10)]
    found = scores(recs, config.defects, rule)
    assert found["wallet-sum"][0] == pytest.approx(4 / 9)
    assert found["orders-cut"][0] == pytest.approx(8 / 9)


def test_mean_confidence_is_over_sample_1_and_the_samples_agreeing_with_it(config, rule):
    spec = {"wallet-sum": [(0.6, A), (0.8, A), (0.1, B)] + [None] * 7, "orders-cut": [(0.5, A)] * 10, "seeing-recode": [(0.5, A)] * 10}
    found = scores(records(spec), config.defects, rule)
    assert found["wallet-sum"] == (pytest.approx(1 / 9), pytest.approx(0.7))


def test_equal_agreement_is_broken_by_mean_confidence_then_by_the_seeded_permutation(config, rule):
    spec = {"wallet-sum": [(0.7, A)] * 10, "orders-cut": [(0.9, A)] * 10, "seeing-recode": [(0.9, A)] * 10}
    found = scores(records(spec), config.defects, rule)
    order = ranking(found, config.defects, rule)
    assert order[0] == "wallet-sum"
    # orders-cut and seeing-recode tie on both keys: the later in the permutation is less confident.
    from warrant.write_line.selector import seeded_permutation
    slots = {(DATABASE[d], *SLOTS[d]): d for d in SLOTS}
    permutation = [slots[s] for s in seeded_permutation(slots, rule.seed)]
    tied = [d for d in permutation if d != "wallet-sum"]
    assert order[1:] == list(reversed(tied))


def test_only_the_first_claim_written_on_a_slot_fills_it(config, rule):
    spec = {"wallet-sum": [(0.9, A)] * 10, "orders-cut": [(0.9, A)] * 10, "seeing-recode": [(0.9, A)] * 10}
    recs = records(spec)
    for r in recs:
        if r.get("record") == "sample" and r["database"] == "crypto" and r["sample"] == 1:
            r["claims"].append(claim("wallet-sum", 0.1, "a second claim on the slot"))
    found = scores(recs, config.defects, rule)
    assert found["wallet-sum"] == (1.0, pytest.approx(0.9))


def test_a_sample_1_claim_the_judge_did_not_finish_ranks_least_confident(config, rule):
    spec = {"wallet-sum": [(0.9, A)] * 10, "orders-cut": [(0.9, A)] * 10, "seeing-recode": [(0.9, A)] * 10}
    recs = records(spec)
    for r in recs:
        if r.get("record") == "judgement" and r["defect"] == "seeing-recode" and r["sample"] == 1:
            r["complete"] = False
    assert scores(recs, config.defects, rule)["seeing-recode"] is None


def test_the_confidence_rule_sends_exactly_its_k_least_confident_slots_to_a_person(config, rule):
    spec = {
        "wallet-sum": [(0.2, A)] + [(0.2, B)] * 9,
        "orders-cut": [(0.9, A)] * 10,
        "seeing-recode": [None] * 10,
    }
    recs = records(spec)
    found = scores(recs, config.defects, rule)
    k = settlement_ask_count(json.loads(PREDICTIONS.read_text()))
    sources = allocation(ranking(found, config.defects, rule), k, with_sample_one_claim(recs, config.defects))
    assert sources == {"seeing-recode": "person", "wallet-sum": "person", "orders-cut": "agent"}
    assert sum(source == "person" for source in sources.values()) == k


def test_a_slot_left_to_the_agent_without_a_sample_1_claim_stays_empty(config, rule):
    found = {"wallet-sum": None, "orders-cut": None, "seeing-recode": None}
    order = ranking(found, config.defects, rule)
    sources = allocation(order, 2, set())
    assert (sources[order[0]], sources[order[1]], sources[order[2]]) == ("person", "person", None)


def test_an_unjudged_sample_1_claim_left_to_the_agent_is_still_the_agents(config, rule):
    spec = {"wallet-sum": [(0.9, A)] * 10, "orders-cut": [(0.9, A)] * 10, "seeing-recode": [(0.9, A)] * 10}
    recs = [r for r in records(spec) if not (r.get("record") == "judgement" and r["sample"] == 1)]
    found = scores(recs, config.defects, rule)
    assert set(found.values()) == {None}
    order = ranking(found, config.defects, rule)
    assert allocation(order, 2, with_sample_one_claim(recs, config.defects))[order[2]] == "agent"
