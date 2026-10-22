"""Samples 2 to 10, the judging and the confidence rule's store inside the run (#51). No test calls a
model.

The fixture is `tests/fixtures/freeze_predictions.yaml` (see tests/test_write_line_stores.py), with the
freeze's own judge, confidence combination and matched asks. The scripted writer writes:

- on total-is-sum, the same claim in all ten samples, at confidence 0.9: full agreement;
- on site-swap, sample 1's claim in samples 2 to 5 only, and the opposite claim in 6 to 10;
- on open-orders-cut, the same claim in all ten, at confidence 0.7;
- nothing on tasks-short-cut, so it ranks least confident.

So the confidence rule asks a person on tasks-short-cut and site-swap, its k = 2 least confident slots.
"""

import dataclasses
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent, ScriptedClaimWriter, ScriptedJudge
from warrant.agent.interface import Response, ResponseKind, Usage
from warrant.agent.judge import JUDGE_PROMPT_VERSION, JudgeCall
from warrant.agent.write_claims import BusinessTerms, system_prompt
from warrant.defects.inject import load_defect
from warrant.store.results import Provenance
from warrant.write_line import run as run_module
from warrant.write_line.config import Config, Question
from warrant.write_line.guards import Prices, Spend
from warrant.write_line.judging import reading_orders_for
from warrant.write_line.run import RunStopped, run

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
RAW = yaml.safe_load((FIXTURES / "freeze_predictions.yaml").read_text())
FROZEN = yaml.safe_load((REPO / "freeze" / "write_line.yaml").read_text())["global"]
GLOBAL = {**RAW["global"], **{key: FROZEN[key] for key in ("judge", "confidence_combination", "matched_asks")}}
DEFECTS = tuple(load_defect(d) for d in RAW["defects"])
BY_ID = {d.id: d for d in DEFECTS}
PROVENANCE = Provenance(config_hash="0" * 64, repo_commit="abc1234", model="anthropic.claude-model-placeholder", prompt_version="9")
PRICES = Prices(2.0, 10.0)
RULES = ("empty", "all_person", "all_agent", "settlement", "confidence", "confidence_abstain")
QUESTIONS = (
    Question("plant-orders", "plant", "How many work orders are there?", "SELECT COUNT(*) FROM workorders", None),
    Question("depot-tasks", "depot", "How many tasks are there?", "SELECT COUNT(*) FROM tasks", None),
)
FORMULA = "The total cost is labour plus parts."
NORTH, SOUTH = "'NORTH' marks the north site.", "'NORTH' marks the south site."
COMPLETE = "The work orders table is complete."
OUTSIDE = "One row is one task."


def claims_of(database, number):
    """What the scripted writer writes in a sample."""
    if database == "depot":
        return [{"claim_kind": "coverage", "subject": "workorders", "statement": COMPLETE, "confidence": 0.7, "cites": []}]
    return [
        {"claim_kind": "column_formula", "subject": "workorders.total_cost", "statement": FORMULA, "confidence": 0.9,
         "cites": ["total_cost equals labor_cost + parts_cost for all rows"]},
        {"claim_kind": "value_meaning", "subject": "workorders.site", "statement": NORTH if number <= 5 else SOUTH,
         "confidence": 0.8, "cites": []},
        {"claim_kind": "grain", "subject": "tasks.taskid", "statement": OUTSIDE, "confidence": 0.5, "cites": []},
    ]


def database_of(user):
    return user.split("\n", 1)[0].removeprefix("Database: ")


ATTEMPTS = 2  # ModelConfig's default, which the fixture configuration, with no model block, uses


class Writer(ScriptedClaimWriter):
    """Counts the samples written per variant and database, so each call knows its sample's number;
    every attempt of a sample in `fails`, named (variant, database, number), fails."""

    def __init__(self, fails=()):
        self.done, self.failed, self.fails = Counter(), Counter(), set(fails)
        super().__init__(self._write)

    def _write(self, system, user):
        variant = "confident" if system == system_prompt("confident") else "abstain"
        database = database_of(user)
        number = self.done[(variant, database)] + 1
        if (variant, database, number) in self.fails:
            self.failed[(variant, database, number)] += 1
            if self.failed[(variant, database, number)] == ATTEMPTS:
                self.done[(variant, database)] += 1
            return None
        self.done[(variant, database)] += 1
        return json.dumps({"claims": claims_of(database, number)})


LETTER = re.compile(r"^([A-Z])\. (.*)$", re.M)


def claim_of(prompt):
    return prompt.split("Claim:\n", 1)[1].split("\n\nReadings:", 1)[0]


def judges(prompt):
    """Every reading fails a claim that says 'south', and holds every other claim."""
    letters = dict(LETTER.findall(prompt.split("Readings:", 1)[1]))
    return json.dumps({letter: "fails" if "south" in claim_of(prompt) else "holds" for letter in letters})


def answers(request, tools):
    return Response(ResponseKind.ANSWER, final_sql="SELECT 1", value=1, confidence=0.5)


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


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
        global_part=GLOBAL,
        business_terms={"plant": BusinessTerms((), ()), "depot": BusinessTerms((), ())},
    )


def go(config, tmp_path, agent=None, writer=None, judge=None, **kwargs):
    return run(config, agent or ScriptedAgent(answers), tmp_path / "work", PROVENANCE, tmp_path / "results.jsonl",
               claim_writer=writer or Writer(), judge_model=judge or ScriptedJudge(judges), **kwargs)


def of(stored, kind):
    return [r for r in stored if r["record"] == kind]


def test_samples_two_to_ten_of_each_confidence_variant_follow_every_sample_one_then_the_judgements_and_stores(config, tmp_path):
    go(config, tmp_path)
    stored = records(tmp_path / "results.jsonl")
    kinds = [r["record"] for r in stored]
    samples = [(r["variant"], r["database"], r["sample"]) for r in of(stored, "sample")]
    assert samples[:4] == [("confident", "plant", 1), ("confident", "depot", 1), ("abstain", "plant", 1), ("abstain", "depot", 1)]
    assert sorted(samples[4:]) == sorted((v, d, n) for v in ("confident", "abstain") for d in ("plant", "depot")
                                         for n in range(2, 11))
    first_judgement, first_store = kinds.index("judgement"), kinds.index("store")
    assert kinds.index("sample") < first_judgement and max(i for i, k in enumerate(kinds) if k == "sample") < first_judgement
    assert max(i for i, k in enumerate(kinds) if k == "judgement") < first_store < kinds.index("answer")


def test_every_slot_claim_of_every_sample_is_judged_once_in_its_slots_reading_order(config, tmp_path):
    judge = ScriptedJudge(judges)
    go(config, tmp_path, judge=judge)
    judgements = of(records(tmp_path / "results.jsonl"), "judgement")
    keys = [(r["variant"], r["defect"], r["sample"]) for r in judgements]
    # Three slot claims per sample (the grain claim is out-of-slot), 10 samples, 2 variants.
    assert Counter(keys) == Counter((v, d, n) for v in ("confident", "abstain")
                                    for d in ("total-is-sum", "site-swap", "open-orders-cut") for n in range(1, 11))
    orders = reading_orders_for(config)
    assert all(r["reading_order"] == list(orders[r["defect"]]) and r["complete"] for r in judgements)
    assert {r["prompt_version"] for r in judgements} == {JUDGE_PROMPT_VERSION}
    assert all(isinstance(r["duration_s"], float) for r in judgements)
    # An identical claim string on a slot is judged once; the rest agree with it without a call.
    called = [r for r in judgements if not r["without_a_call"]]
    assert sorted((r["defect"], r["claim"]) for r in called) == sorted(
        [("total-is-sum", FORMULA), ("site-swap", NORTH), ("site-swap", SOUTH), ("open-orders-cut", COMPLETE)])
    assert len(judge.prompts) == 4 * 3  # three valid calls each


def test_the_confidence_store_asks_a_person_on_its_k_least_confident_slots_and_as_often_as_settlement(config, tmp_path):
    agent = ScriptedAgent(answers)
    go(config, tmp_path, agent=agent)
    stores = {r["rule"]: r for r in of(records(tmp_path / "results.jsonl"), "store")}
    confidence = stores["confidence"]
    assert confidence["ranking"] == ["tasks-short-cut", "site-swap", "open-orders-cut", "total-is-sum"]
    assert confidence["scores"]["tasks-short-cut"] is None
    assert confidence["scores"]["site-swap"] == {"agreement": 4 / 9, "mean_confidence": 0.8}
    assert confidence["scores"]["total-is-sum"] == {"agreement": 1.0, "mean_confidence": 0.9}
    assert {d: s and s["source"] for d, s in confidence["slots"].items()} == {
        "tasks-short-cut": "person", "site-swap": "person", "open-orders-cut": "agent", "total-is-sum": "agent"}
    assert sum(confidence["person_asks"].values()) == sum(stores["settlement"]["person_asks"].values()) == 2
    plant = next(r for r, rule in zip(agent.requests, [r for r in RULES for _ in QUESTIONS])
                 if rule == "confidence" and r.database == "plant")
    assert [c.statement for c in plant.store.claims] == [
        FORMULA, BY_ID["tasks-short-cut"].reference_claim, BY_ID["site-swap"].reference_claim, OUTSIDE]


def test_the_abstain_confidence_rule_ranks_the_abstain_variants_samples(config, tmp_path):
    class AbstainsAgree(Writer):
        def _write(self, system, user):
            text = super()._write(system, user)
            return text.replace("south", "north") if system == system_prompt("abstain") else text

    go(config, tmp_path, writer=AbstainsAgree())
    stores = {r["rule"]: r for r in of(records(tmp_path / "results.jsonl"), "store")}
    assert stores["confidence_abstain"]["scores"]["site-swap"]["agreement"] == 1.0
    assert stores["confidence"]["scores"]["site-swap"]["agreement"] == 4 / 9


def test_a_failed_later_sample_counts_as_disagreeing_and_is_not_drawn_again(config, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, writer=Writer(fails={("confident", "plant", 2)}), agent=Interrupts(after=0))
    stores = {r["rule"]: r for r in of(records(tmp_path / "results.jsonl"), "store")}
    assert stores["confidence"]["scores"]["total-is-sum"]["agreement"] == 8 / 9
    writer = Writer()
    go(config, tmp_path, writer=writer, run_id=records(tmp_path / "results.jsonl")[0]["run_id"])
    assert writer.prompts == []


class Interrupts:
    def __init__(self, after):
        self.after, self.calls = after, 0

    def answer(self, request, tools):
        if self.calls >= self.after:
            raise KeyboardInterrupt
        self.calls += 1
        return ScriptedAgent(answers).answer(request, tools)


def test_a_resume_judges_nothing_again_that_was_judged(config, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, agent=Interrupts(after=2))
    judge = ScriptedJudge(judges)
    go(config, tmp_path, judge=judge, run_id=records(tmp_path / "results.jsonl")[0]["run_id"])
    assert judge.prompts == []
    assert len(of(records(tmp_path / "results.jsonl"), "judgement")) == 60


class PaidJudge:
    """A judge model whose calls cost `input_tokens` each and that raises on call `raise_on`."""

    def __init__(self, input_tokens, raise_on=None):
        self.input_tokens, self.raise_on, self.calls = input_tokens, raise_on, 0

    def call(self, prompt):
        self.calls += 1
        if self.calls == self.raise_on:
            raise KeyboardInterrupt
        return JudgeCall(judges(prompt), Usage(self.input_tokens, 0))


def test_an_interrupted_judgement_keeps_its_paid_answers_and_is_judged_again_on_resume(config, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, judge=PaidJudge(100_000, raise_on=3), spend=Spend(PRICES))
    stored = records(tmp_path / "results.jsonl")
    (cut,) = of(stored, "judgement")
    assert (cut["complete"], cut["input_tokens"], len(cut["answers"])) == (False, 200_000, 2)
    assert cut["error"].startswith("KeyboardInterrupt") and cut["labels"] == {}
    assert Spend.from_records(stored, PRICES).total == pytest.approx(0.4)
    go(config, tmp_path, run_id=stored[0]["run_id"])
    first = next(r for r in of(records(tmp_path / "results.jsonl"), "judgement") if r["complete"])
    assert (first["defect"], first["sample"]) == (cut["defect"], cut["sample"])


def test_the_run_stops_before_a_judgement_that_could_pass_the_cap(config, tmp_path):
    # Three calls of $0.20 per claim: with a $1 cap, the second claim could pass it.
    with pytest.raises(RunStopped, match="cap"):
        go(config, tmp_path, judge=PaidJudge(100_000), spend=Spend(PRICES, cap=1.0))
    assert len(of(records(tmp_path / "results.jsonl"), "judgement")) == 1


def test_a_swallowed_interrupt_stops_the_run_before_its_judging(config, tmp_path, monkeypatch):
    writer, judge = Writer(), ScriptedJudge(judges)
    original = run_module.write_claims

    def signalled_after_the_last_sample(*args, **kwargs):
        output = original(*args, **kwargs)
        if sum(writer.done.values()) == 40:
            run_module._signalled.append("SIGTERM")
        return output

    monkeypatch.setattr(run_module, "_signalled", [])
    monkeypatch.setattr(run_module, "write_claims", signalled_after_the_last_sample)
    with pytest.raises(KeyboardInterrupt, match="SIGTERM"):
        go(config, tmp_path, writer=writer, judge=judge)
    assert judge.prompts == []


@pytest.mark.parametrize("rule", ["confidence", "confidence_abstain"])
def test_a_confidence_rule_without_a_judge_model_is_refused_before_any_call(config, tmp_path, rule):
    writer = Writer()
    with pytest.raises(ValueError, match="judge"):
        run(dataclasses.replace(config, rules=("empty", rule)), ScriptedAgent(answers), tmp_path / "work", PROVENANCE,
            tmp_path / "results.jsonl", claim_writer=writer)
    assert writer.prompts == [] and not (tmp_path / "results.jsonl").exists()


def test_the_command_hands_the_run_the_judge_it_built(write_line_config, tmp_path, monkeypatch):
    raw = yaml.safe_load(write_line_config.read_text())
    write_line_config.write_text(yaml.safe_dump({**raw, "rules": ["empty", "all_agent"]}))
    judge, given = ScriptedJudge(judges), {}

    def stopped(*args, **kwargs):
        given.update(kwargs)
        raise RunStopped("stopped", "f" * 32)

    monkeypatch.setattr(run_module, "ClaudeAgent", lambda model: ScriptedAgent(answers))
    monkeypatch.setattr(run_module, "ClaudeClaimWriter", lambda model: Writer())
    monkeypatch.setattr(run_module, "ClaudeJudge", lambda model: judge)
    monkeypatch.setattr(run_module, "_claim_writing_problems", lambda config, path: [])
    monkeypatch.setattr(run_module, "run", stopped)
    assert run_module.main(["--config", str(write_line_config), "--work-dir", str(tmp_path / "work"),
                            "--results", str(tmp_path / "results.jsonl"),
                            "--judge-validation", str(tmp_path / "judge_validation.jsonl")]) == 3
    assert given["judge_model"] is judge


def test_a_resume_under_another_judge_prompt_version_is_refused(config, tmp_path, monkeypatch):
    with pytest.raises(KeyboardInterrupt):
        go(config, tmp_path, agent=Interrupts(after=0))
    monkeypatch.setattr(run_module, "JUDGE_PROMPT_VERSION", "2")
    with pytest.raises(ValueError, match="another judge prompt"):
        go(config, tmp_path, run_id=records(tmp_path / "results.jsonl")[0]["run_id"])
