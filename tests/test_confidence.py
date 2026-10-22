"""The confidence rule's ranking (#51, `global.confidence_combination`, `global.matched_asks`): each
slot's confidence from the claim-writing samples, lexicographic (agreement with sample 1, then the
mean self-reported confidence, then the seeded permutation), and the k least confident slots sent to
a person, k being the settlement rule's ask count from the committed predictions. It reads the
records of #53's format and calls no model."""

import copy
import json
from fractions import Fraction
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


@pytest.mark.parametrize("change", ["keys", "order", "samples", "tie_break"])
def test_a_combination_rule_other_than_the_one_built_here_is_refused(change):
    raw = copy.deepcopy(yaml.safe_load(FREEZE.read_text())["global"])
    rule = raw["confidence_combination"]
    if change == "keys":
        rule["keys"][0], rule["keys"][1] = rule["keys"][1], rule["keys"][0]
    elif change == "order":
        rule["order"] = "weighted sum"
    elif change == "samples":
        rule["keys"][0]["agreement"] = rule["keys"][0]["agreement"].replace("samples 2 to 10", "samples 2 to 5")
    else:
        raw["matched_asks"]["tie_break"] = "defect id"
    with pytest.raises(ValueError, match="confidence combination|break ties"):
        CombinationRule.from_freeze(raw)


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


def test_a_sample_without_a_claim_on_the_slot_or_a_failed_sample_counts_as_disagreeing(config, rule):
    spec = {"wallet-sum": [(0.8, A)] * 5 + [None] * 5, "orders-cut": [(0.8, A)] * 10, "seeing-recode": [(0.8, A)] * 10}
    recs = []
    for r in records(spec):
        if r.get("database") == "crypto" and r.get("sample") == 10 and r["record"] == "sample":
            r = {**r, "claims": [], "failure": "timed out after retries"}
        elif r.get("record") == "judgement" and r["sample"] == 10 and r["defect"] != "seeing-recode":
            continue
        recs.append(r)
    found = scores(recs, config.defects, rule)
    assert found["wallet-sum"][0] == Fraction(4, 9)
    assert found["orders-cut"][0] == Fraction(8, 9)


def test_a_missing_sample_record_is_refused(config, rule):
    spec = {d: [(0.8, A)] * 10 for d in SLOTS}
    recs = [r for r in records(spec) if not (r.get("record") == "sample" and r["database"] == "alien" and r["sample"] == 7)]
    with pytest.raises(ValueError, match="no record of alien sample 7"):
        scores(recs, config.defects, rule)


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


@pytest.mark.parametrize("sample", [1, 6])
def test_a_claim_on_a_slot_the_judge_did_not_finish_is_refused_not_ranked(config, rule, sample):
    spec = {d: [(0.9, A)] * 10 for d in SLOTS}
    recs = records(spec)
    for r in recs:
        if r.get("record") == "judgement" and r["defect"] == "seeing-recode" and r["sample"] == sample:
            r["complete"] = False
    with pytest.raises(ValueError, match=f"seeing-recode: the claim of sample {sample} has no complete judgement"):
        scores(recs, config.defects, rule)


def test_the_first_complete_judgement_of_a_claim_is_the_one_used(config, rule):
    spec = {d: [(0.9, A)] * 10 for d in SLOTS}
    recs = records(spec) + [{"record": "judgement", "defect": "wallet-sum", "sample": n, "index": 0,
                              "complete": True, "labels": B} for n in (2, 3, 4)]
    assert scores(recs, config.defects, rule)["wallet-sum"][0] == 1


def test_records_of_two_runs_or_a_sample_recorded_twice_are_refused(config, rule):
    recs = records({d: [(0.9, A)] * 10 for d in SLOTS})
    with pytest.raises(ValueError, match="2 runs"):
        scores([{**r, "run_id": "r1"} for r in recs] + [{"record": "start", "run_id": "r2"}], config.defects, rule)
    with pytest.raises(ValueError, match="two records of crypto sample 1"):
        scores(recs + [next(r for r in recs if r.get("record") == "sample")], config.defects, rule)


@pytest.mark.parametrize("value", [1.5, -0.1, "0.9", True, None])
def test_a_confidence_that_is_not_a_number_from_0_to_1_is_refused(config, rule, value):
    recs = records({d: [(0.9, A)] * 10 for d in SLOTS})
    next(r for r in recs if r.get("record") == "sample" and r["database"] == "alien")["claims"][0]["confidence"] = value
    with pytest.raises(ValueError, match="is not a number from 0 to 1"):
        scores(recs, config.defects, rule)


def test_a_claim_of_the_slots_kind_on_another_subject_is_out_of_slot(config, rule):
    spec = {d: [(0.9, A)] * 10 for d in SLOTS}
    recs = records(spec)
    for r in recs:
        if r.get("record") == "sample" and r["database"] == "crypto":
            for c in r["claims"]:
                if c["slot"]["claim_kind"] == "coverage":
                    c["slot"]["subject"] = "orderexecutions"
                elif c["slot"]["claim_kind"] == "column_formula":
                    c["slot"]["subject"] = "Accountbalances.walletsum"
    found = scores(recs, config.defects, rule)
    assert found["orders-cut"] is None and found["wallet-sum"] is None
    assert with_sample_one_claim(recs, config.defects) == {"seeing-recode"}


def test_means_equal_as_written_are_a_tie_whatever_the_order_or_float_rounding(config, rule):
    rest = [(0.5, B)] * 7
    spec = {"wallet-sum": [(0.3, A), (0.1, A), (0.2, A)] + rest,
            "orders-cut": [(0.1, A), (0.2, A), (0.3, A)] + rest,
            "seeing-recode": [(0.85, A), (0.95, A)] + [(0.5, B)] * 8}
    found = scores(records(spec), config.defects, rule)
    assert found["wallet-sum"] == found["orders-cut"] == (Fraction(2, 9), Fraction(1, 5))
    other = scores(records({**spec, "seeing-recode": [(0.9, A), (0.9, A)] + [(0.5, B)] * 8}), config.defects, rule)
    assert found["seeing-recode"] == other["seeing-recode"] == (Fraction(1, 9), Fraction(9, 10))


def test_a_three_way_tie_follows_the_frozen_permutation_over_slots_not_defect_ids(config, rule):
    found = scores(records({d: [(0.9, A)] * 10 for d in SLOTS}), config.defects, rule)
    assert ranking(found, config.defects, rule) == ["wallet-sum", "seeing-recode", "orders-cut"]
    assert ranking({d: None for d in SLOTS}, config.defects, rule) == ["wallet-sum", "seeing-recode", "orders-cut"]


def test_the_ranking_refuses_a_subset_of_the_slots(config, rule):
    with pytest.raises(ValueError, match="pooled"):
        ranking({"wallet-sum": None, "orders-cut": None}, config.defects, rule)


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


