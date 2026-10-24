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
from dataclasses import replace
from fractions import Fraction
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


def probes_with(tables, rules=RULES):
    """Records of `build()` with the answers of the questions named in `tables` replaced: `tables` maps a
    question id to {rule: classes of runs 0 to 2}, every other rule being all correct."""
    kept = [r for r in build() if r.get("question_id") not in tables]
    stamp = {k: v for k, v in kept[0].items() if k in ("config_hash", "repo_commit", "model", "prompt_version", "timestamp", "run_id")}
    added = [{"record": "answer", "question_id": q, "rule": rule, "run": run, "response_class": rows.get(rule, [C, C, C])[run],
              "input_tokens": 100, "output_tokens": 10, "duration_s": 3.0, "failure": "", **stamp}
             for q, rows in tables.items() for rule in rules for run in range(3)]
    complete = next(i for i, r in enumerate(kept) if r["record"] == "complete")
    return kept[:complete] + added + kept[complete:]


def test_the_outcome_cutoff_is_applied_to_exact_means_not_floats():
    # Eight value-meaning probes (the dry run's seeing-recode pattern): correct runs of three under
    # all_agent and empty are (1,3), (2,0), (2,0), (2,0), (3,0), (0,3), (2,1), (2,1), all_person all
    # correct. A = 2/8 = 1/4 exactly and P = 5/12, so the outcome is both; the float mean of the
    # differences is 0.24999999999999997 and would give person_only.
    pairs = [(1, 3), (2, 0), (2, 0), (2, 0), (3, 0), (0, 3), (2, 1), (2, 1)]
    ids = [f"s{n}" for n in range(1, 9)]

    def row(correct):
        return [C] * correct + [W] * (3 - correct)

    tables = {q: {"all_agent": row(a), "empty": row(e)} for q, (a, e) in zip(ids, pairs)}
    config = replace(CONFIG, questions=(*(Question(q, "plant", f"{q}?", "SELECT 1", "site-swap") for q in ids),
                                        *(x for x in CONFIG.questions if x.id not in ("v1", "v2"))))
    kind = contribution(summarise(config, probes_with(tables), PREDICTIONS, config_hash=HASH), "value_meaning")
    assert kind["agent"]["mean"] == 0.25 and kind["person"]["mean"] == pytest.approx(5 / 12)
    assert kind["outcome"] == "both" and kind["agrees"] is False  # the committed prediction is person_only


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


def test_accuracy_and_wrong_answers_per_compared_rule_are_over_q_star_with_all_probes_beside_them(result):
    confirmatory = result["confirmatory"]
    # Over Q*, the test's question set (f1, v1, v2): every confidence answer wrong, every settlement
    # answer right.
    rules = confirmatory["rules"]
    assert rules["settlement"]["answers"] == rules["confidence"]["answers"] == 9
    assert (rules["settlement"]["accuracy"], rules["settlement"]["wrong_answers"]) == (1.0, 0)
    assert (rules["confidence"]["accuracy"], rules["confidence"]["wrong_answers"]) == (0.0, 9)
    assert rules["settlement"]["failure_rate"] == rules["settlement"]["clarification_rate"] == 0
    # Over all five defect probes, labelled apart: c1 and c2 are right under both rules.
    probes = confirmatory["all_defect_probes"]
    assert probes["label"] == "all defect probes, descriptive"
    assert probes["rules"]["settlement"]["answers"] == probes["rules"]["confidence"]["answers"] == 15
    assert probes["rules"]["confidence"]["accuracy"] == pytest.approx(2 / 5)
    assert (probes["rules"]["confidence"]["wrong_answers"], probes["rules"]["settlement"]["wrong_answers"]) == (9, 0)
    assert rules["settlement"]["person_asks"] == probes["rules"]["settlement"]["person_asks"] == 2


def test_every_configured_rule_reports_accuracy_wrong_answers_and_rates_over_all_defect_probes(result):
    block = result["descriptive"]["rules"]
    assert block["label"] == "all defect probes, descriptive" and list(block["rules"]) == list(RULES)
    rules = block["rules"]
    # 5 probes in 3 runs; the empty store is wrong on v1, v2 and f1 in all three runs.
    assert rules["empty"] == {"answers": 15, "accuracy": pytest.approx(6 / 15), "wrong_answers": 9,
                              "failure_rate": 0.0, "clarification_rate": 0.0, "person_asks": 0}
    assert rules["all_agent"]["wrong_answers"] == 5 and rules["all_agent"]["person_asks"] == 0
    # all_person: v1's third run is a clarification request, left out of the accuracy.
    assert rules["all_person"] == {"answers": 15, "accuracy": 1.0, "wrong_answers": 0, "failure_rate": 0.0,
                                   "clarification_rate": pytest.approx(1 / 15), "person_asks": 4}
    assert rules["all_agent_abstain"]["answers"] == 15


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
    # Q* is empty, so its per-rule figures count nothing; the all-probes ones are still given.
    assert confirmatory["rules"]["confidence"]["answers"] == 0 and confirmatory["rules"]["confidence"]["accuracy"] is None
    assert confirmatory["all_defect_probes"]["rules"]["confidence"]["answers"] == 15
    # No test runs at all, not even over all defect probes.
    result = summarise_(build(stores=replaced("confidence", store("confidence", SETTLEMENT, RANKING))))
    assert result["descriptive"]["sensitivity"] == {"label": "descriptive"}


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


def test_repeated_runs_are_reported_with_all_their_outputs_and_their_spend_beside_the_selected_runs():
    aside = [r for r in build(run_id="aside") if r["record"] != "complete"]
    again = build({key: [W, W, W] for key in ANSWERS}, run_id="again")
    found = summarise_(aside + build() + again)
    repeated = {r["run_id"]: r for r in found["repeated_runs"]}
    # Every answer and judgement the run wrote: the judge's outputs (labels, valid calls, answers, re-sent).
    assert len(repeated["aside"]["answers"]) == 3 * len(RULES) * 6
    assert {"question_id", "rule", "run", "response_class"} <= repeated["aside"]["answers"][0].keys()
    judged = [r for r in aside if r["record"] == "judgement"]
    assert len(repeated["aside"]["judgements"]) == len(judged)
    assert {"defect", "sample", "index", "complete", "labels", "valid", "answers", "resent"} <= repeated["aside"]["judgements"][0].keys()
    assert [a["response_class"] for a in repeated["again"]["answers"] if a["question_id"] == "v1" and a["rule"] == "empty"] == [W, W, W]
    cost = found["descriptive"]["cost"]
    one = cost["total_spend"]
    assert one == summarise_()["descriptive"]["cost"]["total_spend"]  # still the selected run's alone
    assert {r["run_id"]: r["spend"] for r in cost["repeated_runs_spend"]} == {"aside": one, "again": one}
    # The $100 cap counts every run in the file.
    assert cost["file_spend"]["input_tokens"] == 3 * one["input_tokens"]
    assert cost["file_spend"]["dollars"] == pytest.approx(3 * one["dollars"])


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
    assert result["confirmatory"]["all_defect_probes"]["rules"]["settlement"]["answers"] == 3 * len(PROBES)
    answering = result["descriptive"]["cost"]["answering"]
    assert answering["settlement"]["input_tokens"] == answering["confidence"]["input_tokens"] + 100


def test_a_judgement_cut_short_and_judged_again_is_reported_with_the_resent_count():
    cut = judgement("confident", "total-is-sum", 1, 0, complete=False, error="throttled", resent=2,
                    answers=["{}", "{}"], valid=[labels("total-is-sum", "holds")])
    done = judgement("confident", "site-swap", 1, 1, "fails", resent=1)
    records = build()
    first = next(i for i, r in enumerate(records) if r["record"] == "judgement")
    # The cut-short record is the earlier one for its claim; the complete one is judged again.
    records[first:first] = [{**records[0], **cut, "record": "judgement"}]
    records = [{**records[0], **done, "record": "judgement"} if (r["record"], r.get("defect"), r.get("sample")) == ("judgement", "site-swap", 1) else r
               for r in records]
    judged = summarise_(records)["descriptive"]["judge"]["confident"]
    assert judged["resent"] == 3
    assert judged["cut_short"] == [{"defect": "total-is-sum", "sample": 1, "index": 0, "error": "throttled",
                                    "resent": 2, "paid_answers": 2, "judged_again": True}]
    # The cut-short record is no judgement: the pairs and instability are those of the complete ones.
    assert judged["pairs"] == summarise_()["descriptive"]["judge"]["confident"]["pairs"]
    assert summarise_()["descriptive"]["judge"]["confident"]["cut_short"] == []


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
    assert cost["evaluation"] == {"judge_validation": None, "judgements": {}}  # none given, and both variants rank
    assert cost["person_asks"] == {"empty": 0, "all_person": 4, "all_agent": 0, "settlement": 2, "confidence": 2,
                                   "all_agent_abstain": 0, "settlement_abstain": 2, "confidence_abstain": 2}


def test_judgements_of_a_variant_without_its_confidence_rule_are_evaluation_cost():
    records = build()
    called = [r for r in records if r["record"] == "judgement" and r["variant"] == "abstain" and not r["without_a_call"]]
    assert called
    config = replace(CONFIG, rules=tuple(r for r in CONFIG.rules if r != "confidence_abstain"))
    cost = summarise(config, records, PREDICTIONS, config_hash=HASH)["descriptive"]["cost"]
    evaluation = cost["evaluation"]["judgements"]
    assert list(evaluation) == ["abstain"] and evaluation["abstain"]["calls"] == len(called)
    assert evaluation["abstain"]["input_tokens"] == 500 * len(called)
    # The confident variant keeps its confidence rule, so its judgements stay that rule's method cost.
    assert cost["method"]["confidence"]["calls"] == 24
    assert "confidence_abstain" not in cost["method"]
    assert cost["evaluation"]["judge_validation"] is None


def test_the_judge_validation_file_is_evaluation_cost_charged_to_no_rule(monkeypatch, tmp_path):
    monkeypatch.setattr(summary_module, "validation_problems", lambda path, method, model: [])
    path = tmp_path / "judge_validation.jsonl"
    path.write_text(json.dumps({"input_tokens": 700, "output_tokens": 70, "duration_s": 1.5}) + "\n"
                    + json.dumps({"record": "note"}) + "\n")
    cost = summarise_(validation=path)["descriptive"]["cost"]
    assert cost["evaluation"]["judge_validation"]["input_tokens"] == 700
    assert cost["method"]["confidence"]["calls"] == 24


def test_a_time_that_was_not_recorded_is_unknown_not_zero(validated):
    # validate_judge.py records no duration_s, so the validation's time is null.
    judge = summarise_(validation=validated)["descriptive"]["cost"]["evaluation"]["judge_validation"]
    assert judge["input_tokens"] == 700 and judge["seconds_total"] is None and judge["seconds_median"] is None
    # A start record without the battery's times leaves the settlement rule's time unknown too.
    records = build()
    del records[0]["battery_s"]
    settlement = summarise_(records)["descriptive"]["cost"]["method"]["settlement"]
    assert settlement["battery_s"] is None and settlement["seconds_total"] is None
    assert settlement["calls"] == 3 and settlement["dollars"] == pytest.approx(0.009)


def test_the_runs_total_spend_sits_beside_the_per_rule_costs_and_is_not_their_sum(result):
    cost = result["descriptive"]["cost"]
    tokens = result["descriptive"]["tokens"]
    total_in = sum(t["input_tokens"] for t in tokens.values())
    total_out = sum(t["output_tokens"] for t in tokens.values())
    assert cost["total_spend"] == {"input_tokens": total_in, "output_tokens": total_out,
                                   "dollars": pytest.approx((total_in * 2 + total_out * 10) / 1e6)}
    assert cost["note"] == NOT_ADDITIVE
    assert "total spend" in summary_module._report(result)


def test_the_summary_is_written_to_results_thin_by_default(tmp_path, monkeypatch, capsys, validated):
    monkeypatch.chdir(tmp_path)
    results = tmp_path / "results.jsonl"
    results.write_text("\n".join(json.dumps(r) for r in build()) + "\n")
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(PREDICTIONS))
    monkeypatch.setattr(summary_module, "config_hash", lambda path: HASH)
    assert main(["--config", str(FIXTURES / "write_line_summary.yaml"), "--results", str(results),
                 "--predictions", str(predictions), "--judge-validation", str(validated)]) == 0
    assert list((tmp_path / "results" / "thin").glob("*.json"))


def test_token_totals_are_reported_per_operation(result):
    assert result["descriptive"]["tokens"] == {
        "answer": {"input_tokens": 100 * (3 * 8 * 6 + 1), "output_tokens": 10 * (3 * 8 * 6 + 1)},
        "write_claims": {"input_tokens": 1000 * 41, "output_tokens": 100 * 41},
        "judge": {"input_tokens": 500 * 4, "output_tokens": 50 * 4},
    }


def test_the_flip_rate_is_reported(result):
    # v1 flips under all_agent and all_person; every other question is steady.
    assert result["descriptive"]["flip_rate"] == pytest.approx(1 / 6)


def test_the_analysis_without_a_question_found_unscorable_is_descriptive_and_beside_the_full_one(result):
    found = summarise_(without=("v1",))
    # The question stays in the confirmatory analysis (ADR 0011).
    assert found["confirmatory"] == result["confirmatory"] and found["confirmatory"]["label"] == "confirmatory"
    without = found["descriptive"]["without"]
    assert without["questions"] == ["v1"]
    assert without["confirmatory"]["label"] == "descriptive"
    assert without["confirmatory"]["questions"] == ["f1", "v2"] and without["confirmatory"]["test"]["p_exact"] == "1/4"
    # v1 was the only question that flips.
    assert without["descriptive"]["flip_rate"] == 0.0
    assert "without" not in without["descriptive"]
    assert "without" not in result["descriptive"]


def test_a_question_to_leave_out_must_be_in_the_configuration():
    with pytest.raises(ValueError, match="ghost"):
        summarise_(without=("ghost",))


def test_the_flip_rate_counts_the_configurations_questions_only(result):
    stray = [{"record": "answer", "question_id": "ghost", "rule": rule, "run": run, "response_class": cls,
              "input_tokens": 0, "output_tokens": 0, "duration_s": 0.0, "failure": ""}
             for rule in RULES for run, cls in enumerate([C, W, C])]
    records = build()
    records[-1:-1] = [{**records[0], **r, "record": "answer"} for r in stray]
    assert summarise_(records)["descriptive"]["flip_rate"] == result["descriptive"]["flip_rate"]


def test_the_command_takes_questions_to_leave_out_more_than_once(tmp_path, monkeypatch, validated):
    monkeypatch.setattr(summary_module, "config_hash", lambda path: HASH)
    results, predictions, out = tmp_path / "results.jsonl", tmp_path / "predictions.json", tmp_path / "summary.json"
    results.write_text("".join(json.dumps(r) + "\n" for r in build()))
    predictions.write_text(json.dumps(PREDICTIONS))
    assert main(["--config", str(FIXTURES / "write_line_summary.yaml"), "--results", str(results), "--predictions",
                 str(predictions), "--judge-validation", str(validated), "--out", str(out),
                 "--without", "v1", "--without", "v2"]) == 0
    assert json.loads(out.read_text())["descriptive"]["without"]["questions"] == ["v1", "v2"]
    assert main(["--config", str(FIXTURES / "write_line_summary.yaml"), "--results", str(results), "--predictions",
                 str(predictions), "--judge-validation", str(validated), "--out", str(out), "--without", "ghost"]) == 1


# The command (AC 6) ------------------------------------------------------------------------------------


@pytest.fixture
def validated(tmp_path, monkeypatch):
    """A judge validation file that clears every check, so a command test gets past it."""
    monkeypatch.setattr(summary_module, "validation_problems", lambda path, method, model: [])
    path = tmp_path / "judge_validation.jsonl"
    path.write_text(json.dumps({"input_tokens": 700, "output_tokens": 70}) + "\n")
    return path


def test_the_judge_validation_file_is_required_by_the_command(tmp_path, capsys):
    with pytest.raises(SystemExit) as stopped:
        main(["--config", str(FIXTURES / "write_line_summary.yaml"), "--results", str(tmp_path / "r.jsonl")])
    assert stopped.value.code == 2 and "--judge-validation" in capsys.readouterr().err


def test_the_summary_makes_no_model_call(tmp_path, monkeypatch, capsys, validated):
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
                 "--judge-validation", str(validated), "--out", str(out)]) == 0
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


def test_the_judges_repeat_instability_counts_unstable_pairs_and_true_reading_splits_over_calls_only():
    records = build()

    def edit(variant, defect, sample, **fields):
        for i, r in enumerate(records):
            if (r["record"], r.get("variant"), r.get("defect"), r.get("sample")) == ("judgement", variant, defect, sample):
                records[i] = {**r, **fields}

    holds = labels("total-is-sum", "holds")
    edit("confident", "total-is-sum", 1, valid=[holds, holds, {**holds, "other": "fails"}])  # one unstable reading
    edit("confident", "site-swap", 1, valid=[labels("site-swap", "fails")] * 2)  # two valid calls: both readings
    edit("confident", "tasks-short-cut", 1, splits=[TRUE["tasks-short-cut"]])  # a split on the true reading
    # A judgement made without a call is no repeat measurement, whatever it holds.
    edit("confident", "total-is-sum", 2, valid=[], splits=[TRUE["total-is-sum"]])
    judge = summarise_(records)["descriptive"]["judge"]
    assert judge["confident"] == {"pairs": 6, "unstable": 3, "share": 0.5, "true_reading_splits": 1, "resent": 0, "cut_short": []}
    # The abstain variant's one claim is stable.
    assert judge["abstain"]["pairs"] == 2 and judge["abstain"]["unstable"] == 0 and judge["abstain"]["share"] == 0.0


def test_the_three_sensitivity_codings_pin_their_per_question_differences():
    F = "failed"
    # f1 under settlement fails once and v1 under settlement asks once; confidence is wrong on both throughout.
    answers = {**ANSWERS, ("f1", "settlement"): [F, C, C], ("v1", "settlement"): [Q, C, C]}
    found = summarise_(build(answers))
    assert found["confirmatory"]["test"]["differences"] == {"f1": "1", "v1": "1", "v2": "1"}
    sensitivity = found["descriptive"]["sensitivity"]
    # Failures as wrong: f1's failed pair counts, as an error under settlement: (0 + 1 + 1) / 3.
    assert sensitivity["failures_as_wrong"]["differences"] == {"f1": "2/3", "v1": "1", "v2": "1"}
    # Clarifications as wrong: v1's clarification request counts the same way, f1's failed pair is dropped.
    assert sensitivity["clarifications_as_wrong"]["differences"] == {"f1": "1", "v1": "2/3", "v2": "1"}
    # Every defect probe under the freeze's own coding: the other slots' probes have d_q = 0.
    assert sensitivity["all_defect_probes"]["differences"] == {"c1": "0", "c2": "0", "f1": "1", "v1": "1", "v2": "1"}


def test_failure_and_clarification_rates_and_over_refusals_are_reported_per_compared_rule():
    answers = {**ANSWERS, ("f1", "confidence"): ["failed", "over_refusal", W], ("v1", "confidence"): [Q, W, W]}
    found = summarise_(build(answers))
    on_q_star = found["confirmatory"]["rules"]["confidence"]
    # Nine answers on Q*: one failure, one clarification request, and seven wrong answers (the
    # over-refusal included); the seven scored answers are all wrong.
    assert on_q_star == {"answers": 9, "accuracy": 0.0, "wrong_answers": 7, "failure_rate": pytest.approx(1 / 9),
                         "clarification_rate": pytest.approx(1 / 9), "person_asks": 2}
    everywhere = found["confirmatory"]["all_defect_probes"]["rules"]["confidence"]
    assert everywhere == {"answers": 15, "accuracy": pytest.approx(6 / 13), "wrong_answers": 7,
                          "failure_rate": pytest.approx(1 / 15), "clarification_rate": pytest.approx(1 / 15), "person_asks": 2}
    assert found["descriptive"]["rules"]["rules"]["confidence"] == everywhere
    assert found["confirmatory"]["rules"]["settlement"]["failure_rate"] == 0.0


def eight_probes(tables):
    """The config with eight value-meaning probes, s1 to s8, and records whose answers to them are
    `tables`: {question: {rule: classes}}, every other rule being all correct."""
    questions = (*(Question(q, "plant", f"{q}?", "SELECT 1", "site-swap") for q in tables),
                 *(x for x in CONFIG.questions if x.id not in ("v1", "v2")))
    return replace(CONFIG, questions=questions), probes_with(tables)


def correct_of_three(n):
    return [C] * n + [W] * (3 - n)


def test_the_outcome_rule_has_a_both_branch_and_keeps_contributions_at_the_cutoff():
    # A = 6/24 and P = (12 - 6)/24, both exactly the cutoff: both, which a strict comparison would miss.
    agent, person = [1, 1, 1, 1, 1, 1, 0, 0], [2, 2, 2, 2, 1, 1, 1, 1]
    tables = {f"s{n}": {"empty": correct_of_three(0), "all_agent": correct_of_three(a), "all_person": correct_of_three(p)}
              for n, (a, p) in enumerate(zip(agent, person), 1)}
    config, records = eight_probes(tables)
    kind = contribution(summarise(config, records, PREDICTIONS, config_hash=HASH), "value_meaning")
    assert (kind["agent"]["mean"], kind["person"]["mean"]) == (0.25, 0.25) and kind["outcome"] == "both"
    # A = 0 and P = 6/24: person only, at the cutoff.
    tables = {q: {"empty": row["empty"], "all_agent": row["empty"], "all_person": correct_of_three(p)}
              for (q, row), p in zip(tables.items(), [1, 1, 1, 1, 1, 1, 0, 0])}
    config, records = eight_probes(tables)
    kind = contribution(summarise(config, records, PREDICTIONS, config_hash=HASH), "value_meaning")
    assert (kind["agent"]["mean"], kind["person"]["mean"]) == (0.0, 0.25) and kind["outcome"] == "person_only"


def test_near_the_cutoff_looks_at_the_persons_interval_as_well_as_the_agents(result):
    # Under abstain A = 0 on both probes (an interval of one point), and P = (1 + 0) / 2, whose interval
    # contains 0.25.
    answers = {**ANSWERS, ("v1", "all_agent_abstain"): [W, W, W], ("v2", "all_agent_abstain"): [W, W, W],
               ("v2", "all_person"): [W, W, W]}
    kind = contribution(summarise_(build(answers)), "value_meaning", "abstain")
    assert kind["agent"]["interval"] == [0.0, 0.0] and kind["person"]["interval"][0] < 0.25 < kind["person"]["interval"][1]
    assert kind["near_cutoff"] is True and kind["outcome"] == "person_only"
    # Neither interval reaches the cutoff for a kind whose contributions are 1 and 0 exactly.
    assert contribution(result, "column_formula")["near_cutoff"] is False


def test_the_bootstrap_seed_resamples_and_level_are_read_from_the_freeze():
    from warrant.scoring.stats import bootstrap_interval

    agent, empty = [1, 2, 2, 2, 3, 0, 2, 2], [3, 0, 0, 0, 0, 3, 1, 1]
    tables = {f"s{n}": {"all_agent": correct_of_three(a), "empty": correct_of_three(e)} for n, (a, e) in enumerate(zip(agent, empty), 1)}
    frozen = json.loads(json.dumps(CONFIG.global_part))
    frozen["seeds"]["bootstrap"] = 7
    frozen["outcome_rule"]["bootstrap"].update(resamples=500, level=0.9)
    config, records = eight_probes(tables)
    kind = contribution(summarise(replace(config, global_part=frozen), records, PREDICTIONS, config_hash=HASH), "value_meaning")
    differences = [Fraction(a - e, 3) for a, e in zip(agent, empty)]
    assert kind["agent"]["interval"] == list(bootstrap_interval(differences, seed=7, resamples=500, level=0.9))
    assert kind["agent"]["interval"] != list(bootstrap_interval(differences, seed=20261013))


def test_a_write_claims_spent_record_is_charged_to_the_rules_that_need_it():
    def spent(variant, sample):
        return {"record": "spent", "operation": "write_claims", "variant": variant, "database": "plant", "sample": sample,
                "input_tokens": 1000, "output_tokens": 100, "duration_s": 2.0, "error": "interrupted"}

    before = summarise_()["descriptive"]["cost"]["method"]
    after = summarise_(build(extra=[spent("confident", 5)]))["descriptive"]["cost"]["method"]
    # A later sample is the confidence rule's alone, and only in its own variant.
    assert after["confidence"]["calls"] == before["confidence"]["calls"] + 1
    assert after["confidence"]["input_tokens"] == before["confidence"]["input_tokens"] + 1000
    for rule in ("all_agent", "settlement", "all_agent_abstain", "confidence_abstain"):
        assert after[rule] == before[rule]
    # Sample 1 is needed by all three confident rules.
    after = summarise_(build(extra=[spent("confident", 1)]))["descriptive"]["cost"]["method"]
    assert all(after[rule]["calls"] == before[rule]["calls"] + 1 for rule in ("all_agent", "settlement", "confidence"))
    assert after["confidence_abstain"] == before["confidence_abstain"]


def test_the_battery_time_is_the_first_start_records():
    resumed = {"record": "start", "battery_s": {"plant": 1.0, "depot": 1.0}, "resumed": True}
    settlement = summarise_(build(extra=[resumed]))["descriptive"]["cost"]["method"]["settlement"]
    assert settlement["battery_s"] == 10.0 and settlement["seconds_total"] == 19.0
