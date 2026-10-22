"""Claim writing and the composed stores inside the run (#50): sample 1 of each prompt variant the rules
need is written on every database before any answer, the stores are composed from it and recorded,
and each question gets its own database's store. No test calls a model.

The fixture is `tests/fixtures/freeze_predictions.yaml` (see tests/test_write_line_stores.py).
"""

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent, ScriptedClaimWriter
from warrant.agent.interface import Response, ResponseKind, Usage
from warrant.agent.prompt import user_message
from warrant.agent.write_claims import WRITE_CLAIMS_PROMPT_VERSION, BusinessTerms, ClaimWritingCall, system_prompt
from warrant.defects.inject import load_defect
from warrant.store.results import Provenance
from warrant.write_line import run as run_module
from warrant.write_line.config import Config, Question, load_config
from warrant.write_line.guards import Prices, Spend
from warrant.write_line.run import RunStopped, run

FIXTURES = Path(__file__).parent / "fixtures"
RAW = yaml.safe_load((FIXTURES / "freeze_predictions.yaml").read_text())
DEFECTS = tuple(load_defect(d) for d in RAW["defects"])
BY_ID = {d.id: d for d in DEFECTS}
# The answer prompt's version differs from the write-claims prompt's, so the records can tell them apart.
PROVENANCE = Provenance(config_hash="0" * 64, repo_commit="abc1234", model="anthropic.claude-model-placeholder", prompt_version="9")
PRICES = Prices(2.0, 10.0)
RULES = ("empty", "all_person", "all_agent", "settlement", "all_agent_abstain", "settlement_abstain")
QUESTIONS = (
    Question("plant-orders", "plant", "How many work orders are there?", "SELECT COUNT(*) FROM workorders", None),
    Question("depot-tasks", "depot", "How many tasks are there?", "SELECT COUNT(*) FROM tasks", None),
)
CLAIMS = {
    "plant": [{"claim_kind": "column_formula", "subject": "workorders.total_cost",
               "statement": "The total cost is labour plus parts.", "confidence": 0.9,
               "cites": ["total_cost equals labor_cost + parts_cost for all rows"]},
              {"claim_kind": "value_meaning", "subject": "workorders.site",
               "statement": "'NORTH' marks the north site.", "confidence": 0.8, "cites": []}],
    "depot": [{"claim_kind": "coverage", "subject": "tasks", "statement": "Some tasks have no work order.",
               "confidence": 0.6, "cites": []}],
}


@pytest.fixture
def config(tmp_path):
    con = sqlite3.connect(tmp_path / "workorders.sqlite")
    con.executescript((FIXTURES / "workorders.sql").read_text())
    con.commit()
    con.close()
    return Config(
        databases={name: tmp_path / path for name, path in RAW["databases"].items()},
        defects=DEFECTS,
        questions=QUESTIONS,
        rules=RULES,
        runs=1,
        global_part=RAW["global"],
        business_terms={"plant": BusinessTerms(("total cost",), (("total cost", "workorders.total_cost"),)),
                        "depot": BusinessTerms((), ())},
    )


def database_of(user):
    return user.split("\n", 1)[0].removeprefix("Database: ")


def writes(system, user):
    return json.dumps({"claims": CLAIMS[database_of(user)]})


def answers(request, tools):
    return Response(ResponseKind.ANSWER, final_sql="SELECT 1", value=1, confidence=0.5)


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def go(config, tmp_path, agent=None, writer=None, **kwargs):
    agent = agent or ScriptedAgent(answers)
    writer = writer or ScriptedClaimWriter(writes)
    return run(config, agent, tmp_path / "work", PROVENANCE, tmp_path / "results.jsonl", claim_writer=writer, **kwargs)


def test_sample_one_of_each_variant_is_written_on_every_database_before_the_stores_and_the_answers(config, tmp_path):
    go(config, tmp_path)
    kinds = [r["record"] for r in records(tmp_path / "results.jsonl")]
    assert kinds == ["start"] + ["sample"] * 4 + ["store"] * len(RULES) + ["answer"] * 2 * len(RULES) + ["complete"]
    samples = [r for r in records(tmp_path / "results.jsonl") if r["record"] == "sample"]
    assert [(r["variant"], r["database"], r["sample"]) for r in samples] == [
        ("confident", "plant", 1), ("confident", "depot", 1), ("abstain", "plant", 1), ("abstain", "depot", 1)]
    assert {r["prompt_version"] for r in samples} == {WRITE_CLAIMS_PROMPT_VERSION}
    assert all(isinstance(r["duration_s"], float) and r["duration_s"] >= 0 for r in samples)
    assert samples[0]["claims"][0] == {"slot": {"claim_kind": "column_formula", "subject": "workorders.total_cost"},
                                       "statement": "The total cost is labour plus parts.", "confidence": 0.9}


def test_the_claim_writer_sees_the_schema_the_injected_copys_battery_output_and_the_business_terms_only(config, tmp_path):
    writer = ScriptedClaimWriter(writes)
    result = go(config, tmp_path, writer=writer)
    system, user = writer.prompts[0]
    assert system == system_prompt("confident") and writer.prompts[2][0] == system_prompt("abstain")
    # Copies are named by content; each database's writer sees its own injected copy's findings only.
    battery = {db: result.predictions.outputs[result.injected[db].stem].decode().strip() for db in ("plant", "depot")}
    assert battery["plant"] != battery["depot"]
    for _, prompt in writer.prompts:
        own = database_of(prompt)
        assert battery[own] in prompt and battery[{"plant": "depot", "depot": "plant"}[own]] not in prompt
    assert "CREATE TABLE workorders" in user and "- total cost (stored in workorders.total_cost)" in user
    for hidden in ("settlement", "all_agent", "reading", "swapped", "as-named", BY_ID["site-swap"].reference_claim):
        assert hidden not in user


def test_each_question_gets_its_own_databases_store_as_its_rule_composes_it(config, tmp_path):
    agent = ScriptedAgent(answers)
    go(config, tmp_path, agent=agent)
    by_rule = {}
    for request, rule in zip(agent.requests, [rule for rule in RULES for _ in QUESTIONS]):
        by_rule[(rule, request.database)] = [c.statement for c in request.store.claims]
    assert by_rule[("settlement", "depot")] == [BY_ID["open-orders-cut"].reference_claim, "Some tasks have no work order."]
    assert by_rule[("settlement", "plant")] == ["The total cost is labour plus parts.", BY_ID["site-swap"].reference_claim]
    assert by_rule[("all_agent", "plant")] == ["The total cost is labour plus parts.", "'NORTH' marks the north site."]
    assert by_rule[("empty", "plant")] == [] and BY_ID["open-orders-cut"].reference_claim not in by_rule[("all_person", "plant")]


def test_the_abstain_rules_are_composed_from_the_abstain_variants_sample_one(config, tmp_path):
    def abstains_on_the_formula(system, user):
        if system == system_prompt("abstain") and database_of(user) == "plant":
            return json.dumps({"claims": CLAIMS["plant"][1:]})
        return writes(system, user)

    agent = ScriptedAgent(answers)
    go(config, tmp_path, agent=agent, writer=ScriptedClaimWriter(abstains_on_the_formula))
    plant = {rule: [c.statement for c in request.store.claims]
             for request, rule in zip(agent.requests, [r for r in RULES for _ in QUESTIONS]) if request.database == "plant"}
    assert "The total cost is labour plus parts." in plant["all_agent"]
    assert plant["all_agent_abstain"] == ["'NORTH' marks the north site."]
    assert plant["settlement_abstain"] == [BY_ID["site-swap"].reference_claim]


@pytest.mark.parametrize("rule", ["confidence", "confidence_abstain"])
def test_a_confidence_rule_is_refused_before_any_call_until_its_store_is_built(config, tmp_path, rule):
    writer = ScriptedClaimWriter(writes)
    with pytest.raises(ValueError, match="#51"):
        go(dataclasses.replace(config, rules=("empty", rule)), tmp_path, writer=writer)
    assert writer.prompts == [] and not (tmp_path / "results.jsonl").exists()


def test_a_swallowed_interrupt_stops_the_run_before_its_claim_writing(config, tmp_path, monkeypatch):
    writer = ScriptedClaimWriter(writes)
    monkeypatch.setattr(run_module, "_signalled", ["SIGTERM"])
    with pytest.raises(KeyboardInterrupt, match="SIGTERM"):
        go(config, tmp_path, writer=writer)
    assert writer.prompts == []


def test_the_store_records_give_each_rules_slots_and_person_asks(config, tmp_path):
    go(config, tmp_path)
    stored = {r["rule"]: r for r in records(tmp_path / "results.jsonl") if r["record"] == "store"}
    assert set(stored) == set(RULES)
    assert stored["settlement"]["person_asks"] == {"coverage": 1, "column_formula": 0, "value_meaning": 1}
    assert stored["settlement"]["slots"]["tasks-short-cut"] is None  # settled, and the agent wrote nothing on it
    assert stored["all_agent"]["slots"]["site-swap"]["source"] == "agent"


def test_the_answer_prompt_is_the_same_for_two_rules_whose_stores_hold_the_same_statements(config, tmp_path):
    def writes_the_reference_claim(system, user):
        if database_of(user) != "plant":
            return writes(system, user)
        claims = [CLAIMS["plant"][0], {**CLAIMS["plant"][1], "statement": BY_ID["site-swap"].reference_claim}]
        return json.dumps({"claims": claims})

    agent = ScriptedAgent(answers)
    go(config, tmp_path, agent=agent, writer=ScriptedClaimWriter(writes_the_reference_claim))
    plant = {rule: request for request, rule in zip(agent.requests, [r for r in RULES for _ in QUESTIONS])
             if request.database == "plant"}
    assert plant["all_agent"].store != plant["settlement"].store  # one claim's source and warrant differ
    assert user_message(plant["all_agent"]) == user_message(plant["settlement"])


def test_the_start_record_carries_the_batterys_wall_time_and_each_answer_its_own(config, tmp_path):
    go(config, tmp_path)
    stored = records(tmp_path / "results.jsonl")
    assert set(stored[0]["battery_s"]) == {"plant", "depot"} and all(s >= 0 for s in stored[0]["battery_s"].values())
    assert all(isinstance(r["duration_s"], float) for r in stored if r["record"] == "answer")


class Interrupts:
    """An answering agent that raises after `after` answers."""

    def __init__(self, after):
        self.after, self.calls = after, 0

    def answer(self, request, tools):
        if self.calls >= self.after:
            raise KeyboardInterrupt
        self.calls += 1
        return ScriptedAgent(answers).answer(request, tools)


def test_a_resumed_run_reuses_its_samples_and_stores_and_writes_no_claim_again(config, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, agent=Interrupts(after=3))
    run_id = records(tmp_path / "results.jsonl")[0]["run_id"]
    writer = ScriptedClaimWriter(writes)
    go(config, tmp_path, writer=writer, run_id=run_id)
    stored = records(tmp_path / "results.jsonl")
    assert writer.prompts == []
    assert [r["record"] for r in stored].count("sample") == 4 and [r["record"] for r in stored].count("store") == len(RULES)
    assert stored[-1]["record"] == "complete"


def test_a_resume_whose_stores_would_differ_from_the_stored_ones_is_refused(config, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, agent=Interrupts(after=1))
    path = tmp_path / "results.jsonl"
    stored = records(path)
    for r in stored:
        if r["record"] == "store" and r["rule"] == "settlement":
            r["slots"]["site-swap"]["warrant"] = "testimony"
    path.write_text("".join(json.dumps(r) + "\n" for r in stored))
    with pytest.raises(ValueError, match="differ from the stored"):
        go(config, tmp_path, run_id=stored[0]["run_id"])


def test_a_resume_under_another_write_claims_prompt_version_is_refused(config, tmp_path, monkeypatch):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, agent=Interrupts(after=1))
    monkeypatch.setattr(run_module, "WRITE_CLAIMS_PROMPT_VERSION", "2")
    with pytest.raises(ValueError, match="another write-claims prompt"):
        go(config, tmp_path, run_id=records(tmp_path / "results.jsonl")[0]["run_id"])


class Paid:
    """A claim-writing model whose every call costs `input_tokens`, and that raises on call `raise_on`."""

    def __init__(self, input_tokens, raise_on=None):
        self.input_tokens, self.raise_on, self.calls = input_tokens, raise_on, 0

    def call(self, system, user):
        self.calls += 1
        if self.calls == self.raise_on:
            raise KeyboardInterrupt
        text = writes(system, user) if self.calls % 2 == 0 else "no JSON here"  # every other attempt is invalid
        return ClaimWritingCall(text, Usage(self.input_tokens, 0))


def test_a_claim_writing_call_stopped_after_a_paid_attempt_is_recorded_as_spent(config, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, writer=Paid(100_000, raise_on=2), spend=Spend(PRICES))
    stored = records(tmp_path / "results.jsonl")
    assert [r["record"] for r in stored] == ["start", "spent"]
    assert (stored[1]["operation"], stored[1]["variant"], stored[1]["database"], stored[1]["sample"],
            stored[1]["input_tokens"], stored[1]["prompt_version"]) == (
        "write_claims", "confident", "plant", 1, 100_000, WRITE_CLAIMS_PROMPT_VERSION)


def test_the_run_stops_before_a_claim_writing_call_that_could_pass_the_cap(config, tmp_path):
    # Each sample costs two attempts of $0.20; with a $0.60 cap a second sample could pass it.
    with pytest.raises(RunStopped, match="cap"):
        go(config, tmp_path, writer=Paid(100_000), spend=Spend(PRICES, cap=0.6))
    assert [r["record"] for r in records(tmp_path / "results.jsonl")] == ["start", "sample"]


def test_an_agent_rule_without_a_claim_writer_is_refused_before_anything_is_stored(config, tmp_path):
    with pytest.raises(ValueError, match="claim writer"):
        run(config, ScriptedAgent(answers), tmp_path / "work", PROVENANCE, tmp_path / "results.jsonl")
    assert not (tmp_path / "results.jsonl").exists()


def test_the_business_terms_are_read_from_the_configuration(write_line_config):
    raw = yaml.safe_load(write_line_config.read_text())
    raw["business_terms"] = {"workorders": {"terms": ["total cost"], "grounding": {"total cost": "workorders.total_cost"}}}
    write_line_config.write_text(yaml.safe_dump(raw))
    assert load_config(write_line_config).business_terms == {
        "workorders": BusinessTerms(("total cost",), (("total cost", "workorders.total_cost"),))}


def test_business_terms_for_a_database_the_configuration_does_not_have_are_refused(write_line_config):
    # A misspelled database would silently leave its claim writer with no business terms.
    raw = yaml.safe_load(write_line_config.read_text())
    raw["business_terms"] = {"work_orders": {"terms": ["total cost"]}}
    write_line_config.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="work_orders"):
        load_config(write_line_config)


REPO = Path(__file__).resolve().parents[1]


def test_claim_writing_waits_for_a_complete_judge_validation_of_the_runs_judge_method_and_model(tmp_path):
    pilot = load_config(REPO / "configs" / "write_line_pilot.yaml")
    validation = REPO / "results" / "judge_validation" / "2026-10-21-4af7c61.jsonl"
    assert run_module._claim_writing_problems(pilot, validation) == []
    assert run_module._claim_writing_problems(pilot, tmp_path / "none.jsonl") == [
        f"no judge validation in {tmp_path / 'none.jsonl'}"]


def test_the_command_hands_the_run_the_claim_writer_it_built(write_line_config, tmp_path, monkeypatch):
    raw = yaml.safe_load(write_line_config.read_text())
    write_line_config.write_text(yaml.safe_dump({**raw, "rules": ["empty", "all_agent"]}))
    writer, given = ScriptedClaimWriter(writes), {}

    def stopped(*args, **kwargs):
        given.update(kwargs)
        raise RunStopped("stopped", "f" * 32)

    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: ScriptedAgent(answers))
    monkeypatch.setattr(run_module, "ClaudeClaimWriter", lambda model: writer)
    monkeypatch.setattr(run_module, "_claim_writing_problems", lambda config, path: [])
    monkeypatch.setattr(run_module, "run", stopped)
    assert run_module.main(["--config", str(write_line_config), "--work-dir", str(tmp_path / "work"),
                            "--results", str(tmp_path / "results.jsonl"),
                            "--judge-validation", str(tmp_path / "judge_validation.jsonl")]) == 3
    assert given["claim_writer"] is writer


def test_the_command_writes_no_claim_before_the_judge_validation_clears_it(write_line_config, tmp_path, monkeypatch, capsys):
    raw = yaml.safe_load(write_line_config.read_text())
    write_line_config.write_text(yaml.safe_dump({**raw, "rules": ["empty", "all_agent"]}))

    def never(*args, **kwargs):
        raise AssertionError("the run started")

    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: ScriptedAgent(answers))
    monkeypatch.setattr(run_module, "ClaudeClaimWriter", lambda model: ScriptedClaimWriter(writes))
    monkeypatch.setattr(run_module, "run", never)
    with pytest.raises(SystemExit):
        run_module.main(["--config", str(write_line_config), "--work-dir", str(tmp_path / "work"),
                         "--results", str(tmp_path / "results.jsonl"),
                         "--judge-validation", str(tmp_path / "judge_validation.jsonl")])
    assert "judge's validation" in capsys.readouterr().err


def test_a_failed_sample_one_stops_the_run_before_the_stores_and_a_resume_draws_only_it_again(config, tmp_path):
    # Decided by the lead on 2026-10-22: a failed sample 1 has no claim set to keep, so it is drawn again.
    def last_fails(system, user):
        return None if system == system_prompt("abstain") and database_of(user) == "depot" else writes(system, user)

    with pytest.raises(RunStopped, match="sample 1 of depot under the abstain variant failed"):
        go(config, tmp_path, writer=ScriptedClaimWriter(last_fails))
    first = records(tmp_path / "results.jsonl")
    assert [r["record"] for r in first] == ["start"] + ["sample"] * 4
    assert first[-1]["failure"] and first[-1]["claims"] == []
    writer = ScriptedClaimWriter(writes)
    go(config, tmp_path, writer=writer, run_id=first[0]["run_id"])
    assert [database_of(user) for system, user in writer.prompts] == ["depot"]  # the failed sample only
    stored = records(tmp_path / "results.jsonl")
    settlement = next(r for r in stored if r["record"] == "store" and r["rule"] == "settlement_abstain")
    assert settlement["slots"]["open-orders-cut"]["source"] == "person" and stored[-1]["record"] == "complete"
    abstain_depot = [r for r in stored if r["record"] == "sample" and (r["variant"], r["database"]) == ("abstain", "depot")]
    assert [bool(r["failure"]) for r in abstain_depot] == [True, False]
