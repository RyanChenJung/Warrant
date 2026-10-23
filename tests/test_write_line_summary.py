"""The write line's summary (#53), recomputed from stored results with no model call.

The fixture is `tests/fixtures/write_line_summary.yaml`: the four slots of freeze_predictions.yaml
(tasks-short-cut, total-is-sum and site-swap on plant; open-orders-cut on depot), predicted agent
alone, agent alone, person only and both, so k = 2 and coverage is mixed. Its results are built
below from small tables, so that every figure the tests check can be worked out by hand:

- value meaning (v1, v2): P = ((1 - 1/3) + (1 - 0)) / 2 = 5/6, with v1's clarification request left
  out (counting it as wrong would give 2/3), and A = (1/3 + 0) / 2 = 1/6: person only, as predicted;
- column formula (f1): A = 1, P = 0: agent alone, as predicted;
- the settlement store asks on open-orders-cut and site-swap, the confidence store, ranking
  [open-orders-cut, total-is-sum, site-swap, tasks-short-cut], on open-orders-cut and total-is-sum,
  so Q* is the probes of total-is-sum and site-swap: f1, v1 and v2, each with d_q = 1, so p = 1/8;
- sample 1's claim on site-swap fails on its true reading and the others hold, so the curve gives
  1, 1, 1, 0, 0 wrong writes at k = 0 to 4, and the settlement rule 0 at 2 asks.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent, ScriptedClaimWriter, ScriptedJudge
from warrant.agent.interface import Response, ResponseKind
from warrant.store.results import Provenance, config_hash
from warrant.write_line import summary as summary_module
from warrant.write_line.config import Config, Question, load_config
from warrant.write_line.predict import BatterySettings
from warrant.write_line.predict import record as predictions_record
from warrant.write_line.run import run
from warrant.write_line.summary import COINCIDE, NOT_ADDITIVE, main, summarise

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = load_config(FIXTURES / "write_line_summary.yaml")
HASH = "c" * 64
MODEL = "anthropic.claude-sonnet-5"  # its list price is $2 and $10 per million tokens
RUN = "main"
METHOD = {"operation": "judge", "rubric_sha256": "r" * 64}

PREDICTIONS = {
    "claims": {
        "tasks-short-cut": {"outcome": "agent_alone"},
        "open-orders-cut": {"outcome": "both"},
        "total-is-sum": {"outcome": "agent_alone"},
        "site-swap": {"outcome": "person_only"},
    },
    "kinds": {"coverage": "mixed", "column_formula": "agent_alone", "value_meaning": "person_only"},
}

C, W, Q = "correct_answer", "wrong_answer", "clarification_request"
PROBES = ("v1", "v2", "f1", "c1", "c2")
RULES = CONFIG.rules
# Each question's response classes for runs 0 to 2 under a rule; every other run is a correct answer.
ANSWERS = {
    ("v1", "empty"): [W, W, W], ("v1", "all_agent"): [W, W, C], ("v1", "all_person"): [C, C, Q],
    ("v2", "empty"): [W, W, W], ("v2", "all_agent"): [W, W, W],
    ("f1", "empty"): [W, W, W],
    ("v1", "confidence"): [W, W, W], ("v2", "confidence"): [W, W, W], ("f1", "confidence"): [W, W, W],
}

SLOT = {
    "tasks-short-cut": ("coverage", "tasks"),
    "open-orders-cut": ("coverage", "workorders"),
    "total-is-sum": ("column_formula", "workorders.total_cost"),
    "site-swap": ("value_meaning", "workorders.site"),
}
TRUE = {"tasks-short-cut": "under-one-hour-cut", "open-orders-cut": "parent-cut",
        "total-is-sum": "labour-and-parts", "site-swap": "swapped"}
# What sample 1 of each variant writes on each database, in order; samples 2 to 10 write the same.
CLAIMED = {
    ("confident", "plant"): ["total-is-sum", "site-swap", "tasks-short-cut"],
    ("confident", "depot"): [],
    ("abstain", "plant"): ["total-is-sum"],
    ("abstain", "depot"): [],
}
FAILS = {("confident", "site-swap")}  # sample 1's claims that fail on their true reading


def claim(defect):
    kind, subject = SLOT[defect]
    return {"slot": {"claim_kind": kind, "subject": subject}, "statement": f"A claim on {defect}.", "confidence": 0.8}


def labels(defect, label):
    return {reading: label for reading in (TRUE[defect], "other")}


def store(rule, sources, ranking=None):
    asks = {"coverage": 0, "column_formula": 0, "value_meaning": 0}
    for defect, source in sources.items():
        if source == "person":
            asks[SLOT[defect][0]] += 1
    record = {"record": "store", "rule": rule, "person_asks": asks,
              "slots": {d: None if s is None else {"source": s, "warrant": "none", "toulmin": {}} for d, s in sources.items()}}
    if ranking is not None:
        record["ranking"] = ranking
        record["scores"] = {d: None for d in ranking}
    return record


SETTLEMENT = {"tasks-short-cut": "agent", "open-orders-cut": "person", "total-is-sum": "agent", "site-swap": "person"}
CONFIDENCE = {"tasks-short-cut": "agent", "open-orders-cut": "person", "total-is-sum": "person", "site-swap": "agent"}
RANKING = ["open-orders-cut", "total-is-sum", "site-swap", "tasks-short-cut"]
# Under abstain sample 1 writes only on total-is-sum, so both rules ask on open-orders-cut and
# site-swap and leave tasks-short-cut empty: they coincide.
SETTLEMENT_ABSTAIN = {"tasks-short-cut": None, "open-orders-cut": "person", "total-is-sum": "agent", "site-swap": "person"}
RANKING_ABSTAIN = ["open-orders-cut", "site-swap", "tasks-short-cut", "total-is-sum"]

STORES = [
    store("empty", dict.fromkeys(SLOT)),
    store("all_person", dict.fromkeys(SLOT, "person")),
    store("all_agent", {d: "agent" if d != "open-orders-cut" else None for d in SLOT}),
    store("settlement", SETTLEMENT),
    store("confidence", CONFIDENCE, RANKING),
    store("all_agent_abstain", {d: "agent" if d == "total-is-sum" else None for d in SLOT}),
    store("settlement_abstain", SETTLEMENT_ABSTAIN),
    store("confidence_abstain", SETTLEMENT_ABSTAIN, RANKING_ABSTAIN),
]


def replaced(rule, record):
    """The fixture's stores with one rule's replaced."""
    return [record if s["rule"] == rule else s for s in STORES]


def judgement(variant, defect, sample, index, label="holds", **fields):
    called = sample == 1
    return {"record": "judgement", "variant": variant, "defect": defect, "sample": sample, "index": index,
            "complete": True, "error": "", "labels": labels(defect, label),
            "valid": [labels(defect, label)] * 3, "splits": [], "without_a_call": not called,
            "input_tokens": 500 if called else 0, "output_tokens": 50 if called else 0,
            "duration_s": 1.0 if called else 0.0, "method": METHOD, **fields}


def build(answers=ANSWERS, stores=None, run_id=RUN, extra=()):
    """One complete run's records, in the order the run writes them."""
    records = [{"record": "start", "battery_s": {"plant": 4.0, "depot": 6.0}, "resumed": False}]
    # A failed sample 1 on plant, drawn again by the resume: the first sample 1 without a failure counts.
    records.append({"record": "sample", "variant": "confident", "database": "plant", "sample": 1, "claims": [],
                    "failure": "malformed", "input_tokens": 1000, "output_tokens": 100, "duration_s": 5.0})
    for variant in ("confident", "abstain"):
        for database in ("plant", "depot"):
            for number in range(1, 11):
                records.append({"record": "sample", "variant": variant, "database": database, "sample": number,
                                "claims": [claim(d) for d in CLAIMED[(variant, database)]], "failure": "",
                                "input_tokens": 1000, "output_tokens": 100, "duration_s": 2.0})
    for variant in ("confident", "abstain"):
        for (v, database), defects in CLAIMED.items():
            if v != variant:
                continue
            for index, defect in enumerate(defects):
                for number in range(1, 11):
                    label = "fails" if (variant, defect) in FAILS else "holds"
                    records.append(judgement(variant, defect, number, index, label))
    records += stores or STORES
    for run in range(3):
        for rule in RULES:
            for q in (*PROBES, "ctl"):
                records.append({"record": "answer", "question_id": q, "rule": rule, "run": run,
                                "response_class": answers.get((q, rule), [C, C, C])[run],
                                "input_tokens": 100, "output_tokens": 10, "duration_s": 3.0, "failure": ""})
    # A settlement answer paid for while the run stopped: a cost, never a response.
    records.append({"record": "spent", "operation": "answer", "question_id": "f1", "rule": "settlement", "run": 0,
                    "input_tokens": 100, "output_tokens": 10, "duration_s": 1.0, "error": "interrupted"})
    records += list(extra)
    records.append({"record": "complete", "answers": 3 * len(RULES) * 6})
    return [{"config_hash": HASH, "repo_commit": "abc1234", "model": MODEL, "prompt_version": "1",
             "timestamp": "2026-10-30T00:00:00+00:00", "run_id": run_id, **r} for r in records]


def summarise_(records=None, predictions=PREDICTIONS, **kwargs):
    return summarise(CONFIG, build() if records is None else records, predictions, config_hash=HASH, **kwargs)


@pytest.fixture(scope="module")
def result():
    return summarise_()


def contribution(result, kind, variant="confident"):
    return result["descriptive"]["variants"][variant]["contributions"][kind]


# Contributions, outcomes and agreement (AC 1, 3, 4; #41) --------------------------------------------


def test_the_persons_contribution_for_a_kind_is_the_hand_computed_mean_of_paired_differences(result):
    person = contribution(result, "value_meaning")["person"]
    assert person["mean"] == pytest.approx(5 / 6)  # 2/3 if v1's clarification request were counted
    assert person["differences"] == pytest.approx({"v1": 2 / 3, "v2": 1.0})
    assert contribution(result, "value_meaning")["agent"]["mean"] == pytest.approx(1 / 6)
    low, high = person["interval"]
    assert 2 / 3 <= low <= high <= 1


def test_each_kinds_outcome_follows_the_frozen_cutoff_on_the_point_estimates(result):
    assert contribution(result, "value_meaning")["outcome"] == "person_only"
    assert contribution(result, "column_formula")["outcome"] == "agent_alone"
    assert contribution(result, "coverage")["outcome"] == "no_measurable_contribution"


def test_agreement_with_the_predicted_outcome_is_reported_per_claim_kind(result):
    kinds = result["descriptive"]["variants"]["confident"]["contributions"]
    assert {kind: (k["predicted"], k["agrees"]) for kind, k in kinds.items()} == {
        "value_meaning": ("person_only", True),
        "column_formula": ("agent_alone", True),
        # A mixed kind is not compared in H1.
        "coverage": ("mixed", None),
    }


def test_no_measurable_contribution_does_not_agree_with_a_prediction():
    predictions = {**PREDICTIONS, "kinds": {**PREDICTIONS["kinds"], "coverage": "both"}}
    assert contribution(summarise_(predictions=predictions), "coverage")["agrees"] is False


def test_an_interval_containing_the_cutoff_is_flagged_near_it_and_leaves_the_outcome():
    # v1 and v2 give A = 1/3 and 0 under the abstain variant's all-agent rule: a mean of 1/6 whose
    # interval reaches past 0.25.
    answers = {**ANSWERS, ("v1", "all_agent_abstain"): [W, W, C], ("v2", "all_agent_abstain"): [W, W, W]}
    kind = contribution(summarise_(build(answers)), "value_meaning", "abstain")
    assert kind["agent"]["mean"] == pytest.approx(1 / 6)
    assert kind["agent"]["interval"][0] <= 0.25 <= kind["agent"]["interval"][1]
    assert kind["near_cutoff"] is True and kind["outcome"] == "person_only"


def test_contributions_outcomes_agreement_and_the_curve_are_labelled_descriptive(result):
    assert result["confirmatory"]["label"] == "confirmatory"
    descriptive = result["descriptive"]
    assert descriptive["label"] == "descriptive"
    for variant in ("confident", "abstain"):
        found = descriptive["variants"][variant]
        assert found["label"] == "descriptive" and found["curve"]["label"] == "descriptive"
        assert all(kind["label"] == "descriptive" for kind in found["contributions"].values())
    assert descriptive["per_slot"]["label"] == descriptive["sensitivity"]["label"] == "descriptive"
    assert descriptive["cost"]["label"] == "descriptive"


# The confirmatory comparison (AC 2; #41) --------------------------------------------------------------


def test_the_rules_are_compared_by_the_frozen_sign_flip_test_at_k_asks_labelled_confirmatory(result):
    confirmatory = result["confirmatory"]
    assert confirmatory["label"] == "confirmatory" and confirmatory["result"] is None
    assert confirmatory["k"] == 2
    assert {rule: r["person_asks"] for rule, r in confirmatory["rules"].items()} == {"settlement": 2, "confidence": 2}
    assert confirmatory["slots"] == ["site-swap", "total-is-sum"]
    assert confirmatory["questions"] == ["f1", "v1", "v2"]
    test = confirmatory["test"]
    assert (test["statistic"], test["n"]) == ("3", 3)
    assert (test["p_exact"], test["two_sided_p_exact"]) == ("1/8", "1/4")
    assert test["p"] == pytest.approx(0.125) and test["significant"] is False
    assert test["mean_difference"] == pytest.approx(1.0)


def test_accuracy_and_wrong_answers_are_reported_per_compared_rule_over_the_probes(result):
    rules = result["confirmatory"]["rules"]
    assert rules["settlement"]["accuracy"] == pytest.approx(1.0)
    assert rules["confidence"]["accuracy"] == pytest.approx(2 / 5)
    assert rules["confidence"]["wrong_answers"] == 9 and rules["settlement"]["wrong_answers"] == 0
    assert rules["settlement"]["failure_rate"] == rules["settlement"]["clarification_rate"] == 0


def test_the_confirmatory_comparison_is_also_reported_per_slot_of_q_star(result):
    assert result["descriptive"]["per_slot"]["slots"] == {
        "site-swap": {"questions": 2, "sum": "2", "mean": 1.0},
        "total-is-sum": {"questions": 1, "sum": "1", "mean": 1.0},
    }


def test_the_sensitivity_analyses_are_reported_descriptively_with_their_codings(result):
    sensitivity = result["descriptive"]["sensitivity"]
    # No failure or clarification falls on a pair of Q*, and every other probe has d_q = 0.
    for name in ("failures_as_wrong", "clarifications_as_wrong", "all_defect_probes"):
        assert sensitivity[name]["p_exact"] == "1/8"


def test_rules_whose_stores_coincide_report_the_frozen_wording_and_no_test():
    confirmatory = summarise_(build(stores=replaced("confidence", store("confidence", SETTLEMENT, RANKING))))["confirmatory"]
    assert confirmatory["result"] == COINCIDE == "rules coincide; H3 not tested at write time"
    assert confirmatory["test"] is None and confirmatory["questions"] == []
    assert confirmatory["ranking"] == RANKING and confirmatory["scores"] == dict.fromkeys(RANKING)


def test_a_store_whose_person_asks_differ_from_k_is_refused():
    three = store("settlement", {**SETTLEMENT, "tasks-short-cut": "person"})
    with pytest.raises(ValueError, match="person asks"):
        summarise_(build(stores=replaced("settlement", three)))


# The abstain variant (ADR 0012) ------------------------------------------------------------------------


def test_the_abstain_variant_is_reported_descriptively_and_never_enters_the_confirmatory_test(result):
    abstain = result["descriptive"]["variants"]["abstain"]
    assert abstain["rules_coincide"] is True and abstain["comparison"]["result"] == COINCIDE
    assert contribution(result, "value_meaning", "abstain")["agent"]["mean"] == pytest.approx(1.0)
    worse = {**ANSWERS, **{(q, "confidence_abstain"): [W, W, W] for q in PROBES},
             **{(q, "settlement_abstain"): [W, W, W] for q in PROBES}}
    assert summarise_(build(worse))["confirmatory"] == result["confirmatory"]
    assert result["descriptive"]["variants"]["confident"]["rules_coincide"] is False


# The wrong-writes curve (AC 5) -------------------------------------------------------------------------


def points(curve, field="wrong_writes"):
    return [p[field] for p in curve["points"]]


def test_the_curve_has_one_point_per_k_and_the_settlement_rule_is_one_point(result):
    curve = result["descriptive"]["variants"]["confident"]["curve"]
    assert [p["k"] for p in curve["points"]] == [0, 1, 2, 3, 4]
    assert points(curve) == [1, 1, 1, 0, 0]
    assert curve["settlement"] == {"asks": 2, "wrong_writes": 0, "wrong_writes_with_splits": 0, "incomplete": 0}
    assert points(result["descriptive"]["variants"]["abstain"]["curve"]) == [0, 0, 0, 0, 0]


def test_a_split_on_the_true_reading_is_incomplete_and_counts_only_in_the_split_variant():
    records = build()
    for r in records:
        if r["record"] == "judgement" and r["variant"] == "confident" and r["defect"] == "tasks-short-cut" and r["sample"] == 1:
            r["labels"] = {**r["labels"], TRUE["tasks-short-cut"]: "not_addressed"}
            r["splits"] = [TRUE["tasks-short-cut"]]
            r["valid"] = [{**r["valid"][0], TRUE["tasks-short-cut"]: label} for label in ("fails", "holds", "not_addressed")]
    curve = summarise_(records)["descriptive"]["variants"]["confident"]["curve"]
    assert points(curve) == [1, 1, 1, 0, 0]
    assert points(curve, "wrong_writes_with_splits") == [2, 2, 2, 1, 0]
    assert points(curve, "incomplete") == [1, 1, 1, 1, 0]
    assert curve["settlement"]["wrong_writes_with_splits"] == 1 and curve["settlement"]["incomplete"] == 1


def test_a_slot_claim_without_a_complete_judgement_is_refused():
    records = [r for r in build() if not (r["record"] == "judgement" and r["defect"] == "site-swap" and r["sample"] == 1)]
    with pytest.raises(ValueError, match="site-swap"):
        summarise_(records)


# Which records are read (#53, 2026-10-21 and 2026-10-22) ------------------------------------------------


def test_the_summary_reads_the_first_complete_run_and_reports_the_others_as_repeated(result):
    aside = [r for r in build(run_id="aside") if r["record"] != "complete"]
    again = build({key: [W, W, W] for key in ANSWERS}, run_id="again")
    other = [{**r, "config_hash": "d" * 64} for r in build(run_id="other")]
    found = summarise_(other + aside + build() + again)
    assert found["run_id"] == RUN
    assert found["confirmatory"] == result["confirmatory"]
    assert [(r["run_id"], r["complete"]) for r in found["repeated_runs"]] == [("aside", False), ("again", True)]
    with pytest.raises(ValueError, match="no complete run"):
        summarise_(aside)


def test_a_claims_judgement_is_its_first_complete_one():
    records = build()
    first = next(i for i, r in enumerate(records) if r["record"] == "judgement" and r["defect"] == "site-swap")
    cut_short = {**records[first], "complete": False, "error": "interrupted", "labels": labels("site-swap", "holds")}
    records.insert(first, cut_short)
    assert points(summarise_(records)["descriptive"]["variants"]["confident"]["curve"]) == [1, 1, 1, 0, 0]


def test_sample_one_is_the_first_without_a_failure(result):
    slots = result["descriptive"]["slots"]["confident"]
    assert {d: s["samples_filling"] for d, s in slots.items()} == {
        "tasks-short-cut": 10, "open-orders-cut": 0, "total-is-sum": 10, "site-swap": 10}
    assert {d for d, s in result["descriptive"]["slots"]["abstain"].items() if s["settled_left_empty"]} == {"tasks-short-cut"}


def test_spent_records_add_cost_but_are_never_responses(result):
    assert result["confirmatory"]["rules"]["settlement"]["answers"] == 3 * len(PROBES)
    answering = result["descriptive"]["cost"]["answering"]
    assert answering["settlement"]["input_tokens"] == answering["confidence"]["input_tokens"] + 100


def test_judgements_made_with_another_method_than_the_validated_one_are_refused(tmp_path, monkeypatch):
    records = build()
    next(r for r in records if r["record"] == "judgement")["method"] = {"operation": "judge", "rubric_sha256": "x"}
    with pytest.raises(ValueError, match="method"):
        summarise_(records)
    monkeypatch.setattr(summary_module, "validation_problems", lambda path, method, model: ["no judge validation"])
    with pytest.raises(ValueError, match="no judge validation"):
        summarise_(validation=tmp_path / "judge_validation.jsonl")


# Cost and time per rule (#53, 2026-10-22) ---------------------------------------------------------------


def test_cost_and_time_per_rule_follow_the_three_classes(result):
    cost = result["descriptive"]["cost"]
    assert cost["note"] == NOT_ADDITIVE
    method = cost["method"]
    # Sample 1 of confident on both databases, the failed draw included: 3 calls of 1,000 and 100
    # tokens, 5 + 2 + 2 seconds.
    assert method["all_agent"] == {"calls": 3, "input_tokens": 3000, "output_tokens": 300, "dollars": pytest.approx(0.009),
                                   "seconds_total": 9.0, "seconds_median": 2.0}
    # The settlement rule adds the baseline battery's 4 + 6 seconds.
    assert method["settlement"]["battery_s"] == 10.0 and method["settlement"]["seconds_total"] == 19.0
    assert method["settlement"]["dollars"] == pytest.approx(0.009)
    # Samples 1 to 10 (21 calls) and the three judgements made with a call.
    assert (method["confidence"]["calls"], method["confidence"]["input_tokens"]) == (24, 22_500)
    assert method["confidence"]["dollars"] == pytest.approx((22_500 * 2 + 2_250 * 10) / 1e6)
    assert method["confidence"]["seconds_total"] == 48.0 and method["confidence"]["seconds_median"] == 2.0
    assert method["empty"] is None and method["all_person"] is None
    # 18 answers of 100 and 10 tokens and 3 seconds; the settlement rule's spent call adds one.
    assert cost["answering"]["empty"] == {"calls": 18, "input_tokens": 1800, "output_tokens": 180,
                                          "dollars": pytest.approx(0.0054), "seconds_total": 54.0, "seconds_median": 3.0}
    assert cost["answering"]["settlement"]["seconds_total"] == 55.0
    assert cost["evaluation"] is None  # no judge validation was given
    assert cost["person_asks"] == {"empty": 0, "all_person": 4, "all_agent": 0, "settlement": 2, "confidence": 2,
                                   "all_agent_abstain": 0, "settlement_abstain": 2, "confidence_abstain": 2}


def test_token_totals_are_reported_per_operation(result):
    assert result["descriptive"]["tokens"] == {
        "answer": {"input_tokens": 100 * (3 * 8 * 6 + 1), "output_tokens": 10 * (3 * 8 * 6 + 1)},
        "write_claims": {"input_tokens": 1000 * 41, "output_tokens": 100 * 41},
        "judge": {"input_tokens": 500 * 4, "output_tokens": 50 * 4},
    }


def test_the_flip_rate_is_reported(result):
    # v1 flips under all_agent and all_person; every other question is steady.
    assert result["descriptive"]["flip_rate"] == pytest.approx(1 / 6)


# The command (AC 6) ------------------------------------------------------------------------------------


def test_the_summary_makes_no_model_call(tmp_path, monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise AssertionError("the summary tried to build a model client")

    for name in ("ClaudeAgent", "ClaudeClaimWriter", "ClaudeJudge"):
        monkeypatch.setattr(f"warrant.agent.claude.{name}.__init__", refuse)
    config = Path(shutil.copy(FIXTURES / "write_line_summary.yaml", tmp_path))
    shutil.copy(FIXTURES / "freeze_predictions.yaml", tmp_path)
    results, predictions, out = tmp_path / "results.jsonl", tmp_path / "predictions.json", tmp_path / "summary.json"
    results.write_text("".join(json.dumps({**r, "config_hash": config_hash(config)}) + "\n" for r in build()))
    predictions.write_text(json.dumps(PREDICTIONS))
    assert main(["--config", str(config), "--results", str(results), "--predictions", str(predictions),
                 "--out", str(out)]) == 0
    written = json.loads(out.read_text())
    assert written["confirmatory"]["test"]["p_exact"] == "1/8"
    assert "confirmatory" in capsys.readouterr().out


# The records the run writes (#54's run, with scripted fakes) --------------------------------------------


def test_the_summary_reads_the_records_the_run_writes(tmp_path):
    """The real run, with the scripted fakes, on the work-order fixture: what it stores is what the
    summary reads, so the two cannot drift apart."""
    con = sqlite3.connect(tmp_path / "workorders.sqlite")
    con.executescript((FIXTURES / "workorders.sql").read_text())
    con.commit()
    con.close()
    frozen = yaml.safe_load((Path(__file__).parents[1] / "freeze" / "write_line.yaml").read_text())["global"]
    global_part = {**CONFIG.global_part, **{k: frozen[k] for k in ("judge", "confidence_combination", "matched_asks")}}
    config = Config(
        databases={name: tmp_path / "workorders.sqlite" for name in ("plant", "depot")},
        defects=CONFIG.defects,
        questions=(Question("orders", "plant", "How many work orders are there?", "SELECT COUNT(*) FROM workorders", None),),
        rules=RULES, runs=3, global_part=global_part,
    )

    def write(system, user):
        database = user.split("\n", 1)[0].removeprefix("Database: ")
        claims = [] if database == "depot" else [
            {"claim_kind": kind, "subject": subject, "statement": f"A claim on {subject}.", "confidence": 0.9, "cites": []}
            for kind, subject in (SLOT["total-is-sum"], SLOT["site-swap"])]
        return json.dumps({"claims": claims})

    def judge(prompt):
        letters = [line[0] for line in prompt.split("Readings:", 1)[1].splitlines() if line[1:3] == ". "]
        return json.dumps(dict.fromkeys(letters, "holds"))

    provenance = Provenance(config_hash=HASH, repo_commit="abc1234", model=MODEL, prompt_version="1")
    results = tmp_path / "results.jsonl"
    done = run(config, ScriptedAgent(lambda request, tools: Response(ResponseKind.ANSWER, final_sql="SELECT 1", value=1)),
               tmp_path / "work", provenance, results,
               claim_writer=ScriptedClaimWriter(write), judge_model=ScriptedJudge(judge))
    predictions = predictions_record(done.predictions, BatterySettings.from_freeze({"global": global_part}), {}, "")
    records = [json.loads(line) for line in results.read_text().splitlines()]

    found = summarise(config, records, predictions, config_hash=HASH)

    assert found["run_id"] == done.run_id and found["confirmatory"]["k"] == 2
    curve = found["descriptive"]["variants"]["confident"]["curve"]
    assert [p["k"] for p in curve["points"]] == [0, 1, 2, 3, 4] and curve["settlement"]["asks"] == 2
    assert found["descriptive"]["slots"]["confident"]["total-is-sum"]["samples_filling"] == 10
    cost = found["descriptive"]["cost"]
    assert cost["answering"]["empty"]["calls"] == 3
    assert cost["method"]["confidence"]["calls"] > cost["method"]["settlement"]["calls"] == 2
    assert cost["method"]["settlement"]["battery_s"] > 0
