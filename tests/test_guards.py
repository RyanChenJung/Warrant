"""The full run's guards (#54): the spending cap, the check after the first complete pass, and the two
checks the freeze asks for before the first claim-writing call. Nothing here calls a model."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from warrant.agent.judge import JudgeMethod
from warrant.write_line.guards import (
    LIST_PRICES,
    Prices,
    Spend,
    answer_estimate,
    mean_tokens,
    over_estimate,
    predictions_differ,
    validation_problems,
)

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "results" / "pilot" / "2026-10-20-e33ac97.jsonl"
VALIDATION = REPO / "results" / "judge_validation" / "2026-10-21-4af7c61.jsonl"
PREDICTIONS = REPO / "predictions" / "9cfd501f2182-write_line.json"
FREEZE = REPO / "freeze" / "write_line.yaml"
MODEL = "anthropic.claude-sonnet-5"


@pytest.fixture
def method():
    return JudgeMethod.from_freeze(yaml.safe_load(FREEZE.read_text())["global"]).record()


def test_a_calls_cost_is_its_tokens_at_the_prices_per_million():
    assert Prices(2.0, 10.0).cost(1_000_000, 100_000) == pytest.approx(3.0)
    assert LIST_PRICES == Prices(2.0, 10.0)


def test_the_spend_refuses_a_call_that_could_take_it_past_the_cap():
    spend = Spend(Prices(2.0, 10.0), cap=1.0)
    assert spend.allows_another_call()
    spend.add(200_000, 10_000)  # 0.50
    assert spend.total == pytest.approx(0.5) and spend.allows_another_call()
    spend.add(100_000, 5_000)  # 0.25, so 0.75 spent and the largest call cost 0.50
    assert not spend.allows_another_call()


def test_before_any_call_the_spend_uses_the_bound_it_is_given():
    spend = Spend(Prices(2.0, 10.0), cap=1.0)
    assert spend.allows_another_call(bound=1.0)
    assert not spend.allows_another_call(bound=1.01)


def test_a_resumed_runs_spend_starts_from_every_stored_call():
    records = [
        {"record": "start"},
        {"record": "sample", "input_tokens": 100_000, "output_tokens": 10_000},
        {"record": "judgement", "input_tokens": 50_000, "output_tokens": 5_000},
        {"record": "answer", "input_tokens": 50_000, "output_tokens": 5_000, "failure": "timed out"},
    ]
    spend = Spend.from_records(records, Prices(2.0, 10.0), cap=100.0)
    assert spend.total == pytest.approx(0.6)
    assert spend.largest_call == pytest.approx(0.3)


def test_the_pilots_mean_tokens_per_answer_come_from_its_records():
    mean_in, mean_out = mean_tokens(json.loads(line) for line in PILOT.read_text().splitlines())
    assert mean_in == pytest.approx(15_887.625) and mean_out == pytest.approx(870.3125)


def test_a_first_pass_costing_more_than_twice_its_estimate_pauses_the_run():
    estimate = answer_estimate(165, 15_887.625, 870.3125, LIST_PRICES)
    assert estimate == pytest.approx(165 * (15_887.625 * 2 + 870.3125 * 10) / 1_000_000)
    assert not over_estimate(actual=2 * estimate, estimate=estimate)
    assert over_estimate(actual=2 * estimate + 0.01, estimate=estimate)


def test_predictions_equal_to_the_committed_ones_differ_nowhere():
    committed = json.loads(PREDICTIONS.read_text())
    assert predictions_differ(copy.deepcopy(committed), committed) == []


def test_a_changed_outcome_output_or_bridge_is_reported():
    committed = json.loads(PREDICTIONS.read_text())
    computed = copy.deepcopy(committed)
    computed["claims"]["orders-cut"]["outcome"] = "person_only"
    computed["claims"]["seeing-recode"]["readings"]["three-is-best"]["output"] = "0" * 64
    computed["bridge"]["wallet-sum"]["battery_tells_apart"] = False
    problems = predictions_differ(computed, committed)
    assert len(problems) == 3
    assert any("orders-cut" in p and "outcome" in p for p in problems)
    assert any("seeing-recode" in p and "three-is-best" in p for p in problems)
    assert any("wallet-sum" in p and "bridge" in p for p in problems)


def test_a_missing_or_extra_slot_is_reported():
    committed = json.loads(PREDICTIONS.read_text())
    computed = copy.deepcopy(committed)
    del computed["claims"]["wallet-sum"]
    assert any("wallet-sum" in p for p in predictions_differ(computed, committed))


def test_the_committed_validation_clears_claim_writing(method):
    assert validation_problems(VALIDATION, method, MODEL) == []


def test_no_validation_file_or_no_complete_run_blocks_claim_writing(method, tmp_path):
    assert validation_problems(tmp_path / "none.jsonl", method, MODEL)
    partial = tmp_path / "partial.jsonl"
    lines = VALIDATION.read_text().splitlines()
    partial.write_text("\n".join(line for line in lines if json.loads(line)["record"] != "complete") + "\n")
    assert any("no complete" in p for p in validation_problems(partial, method, MODEL))


def test_a_validation_with_another_judge_method_or_model_blocks_claim_writing(method):
    other_rubric = {**method, "rubric_sha256": "0" * 64}
    assert any("method" in p for p in validation_problems(VALIDATION, other_rubric, MODEL))
    assert any("model" in p for p in validation_problems(VALIDATION, method, "anthropic.claude-other"))
