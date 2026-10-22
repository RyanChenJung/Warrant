"""The full run's skeleton (#54): every record carries its run id and type, a run opens with a start
record and closes with a complete one, a stopped run is resumed under its run id and makes only the
calls still missing, and the run stops before the $100 cap and pauses after a first pass that cost
more than twice its estimate. No test calls a model."""

import dataclasses
import json
from pathlib import Path

import pytest

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import AgentOutput, Response, ResponseKind, Usage
from warrant.store.results import Provenance
from warrant.write_line.config import load_config
from warrant.write_line.guards import Prices, Spend
from warrant.write_line import run as run_module
from warrant.write_line.run import RunStopped, committed_predictions_for, main, run

REPO = Path(__file__).resolve().parents[1]
PROVENANCE = Provenance(config_hash="0" * 64, repo_commit="abc1234", model="anthropic.claude-model-placeholder", prompt_version="1")
PRICES = Prices(2.0, 10.0)


@pytest.fixture
def config(write_line_config):
    return load_config(write_line_config)


def answers(request, tools):
    return Response(ResponseKind.ANSWER, final_sql="SELECT 1", value=1, confidence=0.5)


class Costly:
    """A scripted agent whose every answer costs `input_tokens`, and that raises after `stop_after` calls."""

    def __init__(self, input_tokens=0, stop_after=None):
        self.input_tokens, self.stop_after, self.calls = input_tokens, stop_after, 0

    def answer(self, request, tools):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise KeyboardInterrupt
        self.calls += 1
        return AgentOutput(answers(request, tools), Usage(self.input_tokens, 0))


class PaidThenInterrupted:
    """An agent interrupted after paying for an answer, the tokens carried on the error as ClaudeAgent does."""

    def answer(self, request, tools):
        error = KeyboardInterrupt()
        error.usage = Usage(100_000, 0)
        raise error


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main_args(write_line_config, tmp_path, *extra):
    return ["--config", str(write_line_config), "--work-dir", str(tmp_path / "work"),
            "--results", str(tmp_path / "results.jsonl"),
            "--judge-validation", str(tmp_path / "judge_validation.jsonl"), *extra]


def test_a_run_opens_with_a_start_record_closes_with_a_complete_one_and_types_every_record(config, tmp_path):
    results = tmp_path / "results.jsonl"
    result = run(config, ScriptedAgent(answers), tmp_path / "work", PROVENANCE, results)
    stored = records(results)
    assert [r["record"] for r in stored] == ["start"] + ["answer"] * len(result.rows) + ["complete"]
    assert len({r["run_id"] for r in stored}) == 1 and stored[0]["run_id"] == result.run_id
    assert stored[0]["rules"] == list(config.rules) and stored[0]["runs"] == config.runs


def test_a_stopped_run_is_resumed_under_its_run_id_and_makes_only_the_missing_calls(config, tmp_path):
    results = tmp_path / "results.jsonl"
    with pytest.raises(KeyboardInterrupt):
        run(config, Costly(stop_after=2), tmp_path / "work", PROVENANCE, results)
    first = records(results)
    run_id = first[0]["run_id"]
    assert [r["record"] for r in first] == ["start", "answer", "answer"]
    agent = Costly()
    run(config, agent, tmp_path / "work", PROVENANCE, results, run_id=run_id)
    stored = records(results)
    total = len(config.questions) * len(config.rules) * config.runs
    assert agent.calls == total - 2
    answered = [(r["question_id"], r["rule"], r["run"]) for r in stored if r["record"] == "answer"]
    assert len(answered) == len(set(answered)) == total
    assert [r["record"] for r in stored].count("start") == 2 and stored[-1]["record"] == "complete"
    assert {r["run_id"] for r in stored} == {run_id}


def test_a_resume_with_another_configuration_or_an_unknown_run_id_is_refused(config, tmp_path):
    results = tmp_path / "results.jsonl"
    with pytest.raises(KeyboardInterrupt):
        run(config, Costly(stop_after=1), tmp_path / "work", PROVENANCE, results)
    run_id = records(results)[0]["run_id"]
    other = Provenance("1" * 64, PROVENANCE.repo_commit, PROVENANCE.model, PROVENANCE.prompt_version)
    with pytest.raises(ValueError, match="another configuration"):
        run(config, Costly(), tmp_path / "work", other, results, run_id=run_id)
    with pytest.raises(ValueError, match="no run"):
        run(config, Costly(), tmp_path / "work", PROVENANCE, results, run_id="f" * 32)


def test_the_run_stops_before_a_call_that_could_take_its_spend_past_the_cap(config, tmp_path):
    results = tmp_path / "results.jsonl"
    # Each answer costs $0.20, so with a $0.50 cap a third answer could pass it.
    with pytest.raises(RunStopped, match="cap"):
        run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results, spend=Spend(PRICES, cap=0.5))
    assert [r["record"] for r in records(results)] == ["start", "answer", "answer"]


def test_a_resumed_run_counts_what_was_spent_before(config, tmp_path):
    results = tmp_path / "results.jsonl"
    with pytest.raises(RunStopped):
        run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results, spend=Spend(PRICES, cap=0.5))
    run_id = records(results)[0]["run_id"]
    agent = Costly(input_tokens=100_000)
    with pytest.raises(RunStopped, match="cap"):
        run(config, agent, tmp_path / "work", PROVENANCE, results, run_id=run_id,
            spend=Spend.from_records(records(results), PRICES, cap=0.5))
    assert agent.calls == 0


def test_a_call_paid_for_but_stopped_before_its_answer_is_stored_is_recorded_as_spent_and_asked_again(config, tmp_path):
    results = tmp_path / "results.jsonl"
    with pytest.raises(KeyboardInterrupt) as caught:
        run(config, PaidThenInterrupted(), tmp_path / "work", PROVENANCE, results, spend=Spend(PRICES))
    first = records(results)
    run_id = first[0]["run_id"]
    assert [r["record"] for r in first] == ["start", "spent"]
    assert (first[1]["operation"], first[1]["input_tokens"], first[1]["run_id"]) == ("answer", 100_000, run_id)
    assert Spend.from_records(first, PRICES).total == pytest.approx(0.2)
    assert any(f"--run-id {run_id}" in note for note in caught.value.__notes__)
    agent = Costly()
    run(config, agent, tmp_path / "work", PROVENANCE, results, run_id=run_id)
    assert agent.calls == len(config.questions) * len(config.rules) * config.runs


def test_an_answer_stopped_while_it_is_scored_is_recorded_as_spent(config, tmp_path, monkeypatch):
    def interrupted(path, sql):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_module, "execute", interrupted)
    results = tmp_path / "results.jsonl"
    with pytest.raises(KeyboardInterrupt):
        run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results, spend=Spend(PRICES))
    assert [(r["record"], r.get("input_tokens")) for r in records(results)] == [("start", None), ("spent", 100_000)]


def test_a_complete_run_or_one_with_another_prompt_version_or_other_rules_is_not_resumed(config, tmp_path):
    done = run(config, Costly(), tmp_path / "work", PROVENANCE, tmp_path / "done.jsonl")
    with pytest.raises(ValueError, match="is complete"):
        run(config, Costly(), tmp_path / "work", PROVENANCE, tmp_path / "done.jsonl", run_id=done.run_id)
    stopped = tmp_path / "stopped.jsonl"
    with pytest.raises(KeyboardInterrupt):
        run(config, Costly(stop_after=1), tmp_path / "work", PROVENANCE, stopped)
    run_id = records(stopped)[0]["run_id"]
    with pytest.raises(ValueError, match="another answer prompt"):
        run(config, Costly(), tmp_path / "work", dataclasses.replace(PROVENANCE, prompt_version="2"), stopped, run_id=run_id)
    with pytest.raises(ValueError, match="other rules or runs"):
        run(dataclasses.replace(config, runs=2), Costly(), tmp_path / "work", PROVENANCE, stopped, run_id=run_id)


def test_a_first_pass_check_without_a_spend_is_refused_before_anything_is_stored(config, tmp_path):
    results = tmp_path / "results.jsonl"
    with pytest.raises(ValueError, match="spend"):
        run(config, Costly(), tmp_path / "work", PROVENANCE, results, first_pass_estimate=1.0)
    assert not results.exists()


def test_the_run_pauses_after_a_first_pass_over_twice_its_estimate_and_goes_on_when_approved(config, tmp_path):
    config = dataclasses.replace(config, runs=3)
    results = tmp_path / "results.jsonl"
    with pytest.raises(RunStopped, match="first pass"):
        run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results,
            spend=Spend(PRICES, cap=100.0), first_pass_estimate=0.01)
    stored = records(results)
    first_pass = len(config.questions) * len(config.rules)
    assert sum(r["record"] == "answer" for r in stored) == first_pass
    run_id = stored[0]["run_id"]
    run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results, run_id=run_id,
        spend=Spend(PRICES, cap=100.0), first_pass_estimate=0.01, approve_first_pass=True)
    stored = records(results)
    assert stored[-1]["record"] == "complete" and sum(r["record"] == "answer" for r in stored) == 3 * first_pass


def test_a_resume_after_the_pause_without_approval_pauses_again(config, tmp_path):
    config = dataclasses.replace(config, runs=3)
    results = tmp_path / "results.jsonl"
    kwargs = dict(spend=Spend(PRICES, cap=100.0), first_pass_estimate=0.01)
    with pytest.raises(RunStopped):
        run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results, **kwargs)
    run_id = records(results)[0]["run_id"]
    agent = Costly(input_tokens=100_000)
    with pytest.raises(RunStopped, match="first pass"):
        run(config, agent, tmp_path / "work", PROVENANCE, results, run_id=run_id,
            spend=Spend(PRICES, cap=100.0), first_pass_estimate=0.01)
    assert agent.calls == 0


def test_an_approved_first_pass_stays_approved_when_the_run_is_resumed_again(config, tmp_path):
    config = dataclasses.replace(config, runs=3)
    results = tmp_path / "results.jsonl"
    with pytest.raises(RunStopped, match="first pass"):
        run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results,
            spend=Spend(PRICES), first_pass_estimate=0.01)
    run_id = records(results)[0]["run_id"]
    with pytest.raises(KeyboardInterrupt):
        run(config, Costly(input_tokens=100_000, stop_after=1), tmp_path / "work", PROVENANCE, results, run_id=run_id,
            spend=Spend.from_records(records(results), PRICES), first_pass_estimate=0.01, approve_first_pass=True)
    assert [r["first_pass_approved"] for r in records(results) if r["record"] == "start"] == [False, True]
    run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results, run_id=run_id,
        spend=Spend.from_records(records(results), PRICES), first_pass_estimate=0.01)
    assert records(results)[-1]["record"] == "complete"


def test_a_first_pass_within_twice_its_estimate_does_not_pause(config, tmp_path):
    config = dataclasses.replace(config, runs=3)
    results = tmp_path / "results.jsonl"
    first_pass_cost = len(config.questions) * len(config.rules) * PRICES.cost(100_000, 0)
    run(config, Costly(input_tokens=100_000), tmp_path / "work", PROVENANCE, results,
        spend=Spend(PRICES, cap=100.0), first_pass_estimate=first_pass_cost / 2)
    assert records(results)[-1]["record"] == "complete"


def test_the_command_stops_at_the_cap_and_says_how_to_resume(write_line_config, tmp_path, monkeypatch, capsys):
    # Each answer costs $60 at the list price, so the second would pass the $100 cap.
    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: Costly(input_tokens=30_000_000))
    results = tmp_path / "results.jsonl"
    assert main(main_args(write_line_config, tmp_path)) == 3
    printed = capsys.readouterr().out
    run_id = records(results)[0]["run_id"]
    assert "cap" in printed and "the lead's decision" in printed and f"--run-id {run_id}" in printed
    assert sum(r["record"] == "answer" for r in records(results)) == 1


def test_a_new_run_beside_an_incomplete_run_of_its_configuration_is_refused(write_line_config, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: Costly(input_tokens=30_000_000))
    results = tmp_path / "results.jsonl"
    main(main_args(write_line_config, tmp_path))
    run_id = records(results)[0]["run_id"]
    with pytest.raises(SystemExit):
        main(main_args(write_line_config, tmp_path))
    assert f"--run-id {run_id}" in capsys.readouterr().err
    assert [r["record"] for r in records(results)].count("start") == 1


def test_a_new_run_counts_what_every_earlier_run_in_the_results_file_spent(write_line_config, tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: Costly(input_tokens=30_000_000))
    results = tmp_path / "results.jsonl"
    assert main(main_args(write_line_config, tmp_path)) == 3
    assert main(main_args(write_line_config, tmp_path, "--new-run")) == 3
    assert [r["record"] for r in records(results)].count("start") == 2
    assert sum(r["record"] == "answer" for r in records(results)) == 1


def test_the_cap_counts_what_the_judge_validation_spent(write_line_config, tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: Costly(input_tokens=30_000_000))
    (tmp_path / "judge_validation.jsonl").write_text(
        json.dumps({"operation": "judge_validation", "input_tokens": 30_000_000, "output_tokens": 0}) + "\n")
    assert main(main_args(write_line_config, tmp_path)) == 3
    assert sum(r["record"] == "answer" for r in records(tmp_path / "results.jsonl")) == 0


def test_the_committed_predictions_are_found_by_the_injection_records_hash(config):
    pilot = load_config(REPO / "configs" / "write_line_pilot.yaml")
    committed = committed_predictions_for(pilot)
    assert committed["injection_record"] == "injections/9cfd501f2182-write_line.json"
    assert committed_predictions_for(config) is None  # no injection record named


def test_an_injection_record_with_reading_sets_and_no_committed_predictions_is_refused(tmp_path):
    pilot = load_config(REPO / "configs" / "write_line_pilot.yaml")
    with pytest.raises(ValueError, match="no committed predictions"):
        committed_predictions_for(pilot, tmp_path)
