"""The stores the allocation rules compose (#50), one per database, from sample 1's claims, the warrants
of the committed predictions and the freeze's reference claims, with no model call.

The fixture is `tests/fixtures/freeze_predictions.yaml`: on `plant`, tasks-short-cut and total-is-sum
are settled (agent alone) and site-swap is person only (a declaration); on `depot`, open-orders-cut is
predicted both (a testimony). So k = 2.
"""

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from warrant.defects.build import build
from warrant.defects.inject import load_defect
from warrant.store.claims import PredictedOutcome, Slot, Source, WarrantKind
from warrant.write_line.predict import BatterySettings, predict
from warrant.write_line.predict import record as predictions_record
from warrant.write_line.stores import compose, store_record, variant_of, written_claims
from warrant.write_line.warrants import BATTERY_BACKING, PERSON_BACKING, PROVENANCE_RECORD, slot_warrants

FIXTURES = Path(__file__).parent / "fixtures"
RAW = yaml.safe_load((FIXTURES / "freeze_predictions.yaml").read_text())
DEFECTS = tuple(load_defect(d) for d in RAW["defects"])
BY_ID = {d.id: d for d in DEFECTS}


@pytest.fixture(scope="module")
def warrants(tmp_path_factory):
    folder = tmp_path_factory.mktemp("stores")
    con = sqlite3.connect(folder / "workorders.sqlite")
    con.executescript((FIXTURES / "workorders.sql").read_text())
    con.commit()
    con.close()
    clean = {name: folder / path for name, path in RAW["databases"].items()}
    settings = BatterySettings.from_freeze(RAW)
    predictions = predict(DEFECTS, build(list(DEFECTS), clean, folder / "out"), clean, settings, folder / "battery")
    return slot_warrants(DEFECTS, predictions_record(predictions, settings, {}, ""))


def sample(database, *claims, failure=""):
    """A sample-1 record whose one output is the answer the claims were parsed from."""
    written = [{"claim_kind": kind, "subject": subject, "statement": statement, "confidence": confidence,
                "cites": list(cites)} for kind, subject, statement, confidence, cites in claims]
    return {
        "record": "sample", "variant": "confident", "database": database, "sample": 1,
        "claims": [] if failure else [{"slot": {"claim_kind": c["claim_kind"], "subject": c["subject"]},
                                       "statement": c["statement"], "confidence": c["confidence"]} for c in written],
        "outputs": [f"failed: {failure}"] if failure else [json.dumps({"claims": written})],
        "input_tokens": 0, "output_tokens": 0, "failure": failure,
    }


FORMULA = ("column_formula", "workorders.total_cost", "The total cost is labour plus parts.", 0.9,
           ("total_cost equals labor_cost + parts_cost for all rows",))
SITE = ("value_meaning", "workorders.site", "'NORTH' marks the north site.", 0.8, ())
OUTSIDE = ("grain", "tasks.taskid", "One row is one task.", 0.6, ())
PLANT = sample("plant", OUTSIDE, SITE, FORMULA)
DEPOT = sample("depot", ("coverage", "workorders", "The work orders table is complete.", 0.7, ()))


def statements(store):
    return [claim.statement for claim in store.store.claims]


def test_everything_from_the_agent_holds_sample_ones_claims_slots_first_in_slot_order_then_the_rest_as_written(warrants):
    composed = compose("all_agent", "plant", DEFECTS, warrants, PLANT)
    assert statements(composed) == ["The total cost is labour plus parts.", "'NORTH' marks the north site.",
                                    "One row is one task."]
    formula, site, outside = composed.store.claims
    assert (formula.source, formula.warrant, formula.toulmin.backing) == (Source.AGENT, WarrantKind.DATA, BATTERY_BACKING)
    assert formula.toulmin.data == "total_cost equals labor_cost + parts_cost for all rows"
    assert (site.warrant, site.predicted_outcome) == (WarrantKind.NONE, PredictedOutcome.PERSON_ONLY)
    assert (outside.slot, outside.warrant, outside.predicted_outcome) == (Slot("grain", "tasks.taskid"), WarrantKind.NONE, None)
    assert composed.slots["tasks-short-cut"] is None  # the agent wrote nothing on it


def test_the_settlement_rule_takes_the_agents_claim_on_a_settled_slot_and_the_reference_claim_elsewhere(warrants):
    plant = compose("settlement", "plant", DEFECTS, warrants, PLANT)
    assert plant.slots["total-is-sum"].source == Source.AGENT
    site = plant.slots["site-swap"]  # the agent's claim on it is set aside, whatever it says
    assert (site.source, site.statement, site.warrant, site.toulmin.backing) == (
        Source.PERSON, BY_ID["site-swap"].reference_claim, WarrantKind.DECLARATION, PERSON_BACKING)
    assert "'NORTH' marks the north site." not in statements(plant)
    depot = compose("settlement", "depot", DEFECTS, warrants, DEPOT).slots["open-orders-cut"]
    assert (depot.source, depot.warrant, depot.toulmin.qualifier) == (Source.PERSON, WarrantKind.TESTIMONY, PROVENANCE_RECORD)
    assert depot.predicted_outcome == PredictedOutcome.BOTH


def test_a_settled_slot_with_no_agent_claim_stays_empty_under_the_settlement_rule(warrants):
    composed = compose("settlement", "plant", DEFECTS, warrants, PLANT)
    assert composed.slots["tasks-short-cut"] is None
    record = store_record("settlement", {db: compose("settlement", db, DEFECTS, warrants, s)
                                         for db, s in (("plant", PLANT), ("depot", DEPOT))}, DEFECTS)
    assert record["slots"]["tasks-short-cut"] is None
    assert sum(record["person_asks"].values()) == 2  # k, the frozen ask count


def test_a_second_claim_on_a_filled_slot_and_a_kind_outside_the_five_are_out_of_slot(warrants):
    again = ("value_meaning", "workorders.site", "'SOUTH' marks the south site.", 0.5, ())
    odd = ("row_meaning", "workorders", "One row is one work order.", 0.5, ())
    composed = compose("all_agent", "plant", DEFECTS, warrants, sample("plant", SITE, again, odd))
    assert composed.slots["site-swap"].statement == "'NORTH' marks the north site."
    assert [(c.slot.claim_kind, c.statement) for c in composed.out_of_slot] == [
        ("value_meaning", "'SOUTH' marks the south site."), ("row_meaning", "One row is one work order.")]
    assert all(c.warrant == WarrantKind.NONE and c.predicted_outcome is None for c in composed.out_of_slot)


def test_a_claim_on_another_subject_fills_no_slot(warrants):
    # The battery reports the cut orders on the child table, which is not the coverage slot's subject.
    child = ("coverage", "tasks", "Some tasks reference work orders that are missing.", 0.7, ())
    composed = compose("all_agent", "depot", DEFECTS, warrants, sample("depot", child))
    assert composed.slots["open-orders-cut"] is None and len(composed.out_of_slot) == 1


def test_a_store_holds_only_its_own_databases_claims(warrants):
    assert all(c.slot != BY_ID["open-orders-cut"].slot
               for c in compose("all_person", "plant", DEFECTS, warrants).store.claims)
    assert [c.statement for c in compose("all_person", "depot", DEFECTS, warrants).store.claims] == [
        BY_ID["open-orders-cut"].reference_claim]


def test_everything_from_a_person_holds_the_reference_claims_with_their_warrants(warrants):
    plant = compose("all_person", "plant", DEFECTS, warrants)
    # Slot order, (database, claim kind, subject), not the freeze's order.
    assert statements(plant) == [BY_ID[d].reference_claim for d in ("total-is-sum", "tasks-short-cut", "site-swap")]
    assert {d: (c.source, c.warrant) for d, c in plant.slots.items()} == {
        "tasks-short-cut": (Source.PERSON, WarrantKind.DATA), "total-is-sum": (Source.PERSON, WarrantKind.DATA),
        "site-swap": (Source.PERSON, WarrantKind.DECLARATION)}
    assert plant.out_of_slot == () and compose("empty", "plant", DEFECTS, warrants).store.claims == ()


def test_each_rule_records_its_person_asks_per_claim_kind_with_every_frozen_kind(warrants):
    def asks(rule):
        return store_record(rule, {db: compose(rule, db, DEFECTS, warrants, s)
                                   for db, s in (("plant", PLANT), ("depot", DEPOT))}, DEFECTS)["person_asks"]

    assert asks("empty") == asks("all_agent") == {"coverage": 0, "column_formula": 0, "value_meaning": 0}
    assert asks("all_person") == {"coverage": 2, "column_formula": 1, "value_meaning": 1}
    assert asks("settlement") == {"coverage": 1, "column_formula": 0, "value_meaning": 1}


def test_the_store_record_maps_every_frozen_slot_to_its_claims_source_warrant_and_toulmin_record(warrants):
    record = store_record("settlement", {db: compose("settlement", db, DEFECTS, warrants, s)
                                         for db, s in (("plant", PLANT), ("depot", DEPOT))}, DEFECTS)
    assert record["rule"] == "settlement" and set(record["slots"]) == set(BY_ID)
    assert record["slots"]["total-is-sum"] == {"source": "agent", "warrant": "data", "toulmin": {
        "data": "total_cost equals labor_cost + parts_cost for all rows", "backing": BATTERY_BACKING}}
    assert record["slots"]["open-orders-cut"] == {"source": "person", "warrant": "testimony", "toulmin": {
        "backing": PERSON_BACKING, "qualifier": PROVENANCE_RECORD}}


def test_a_failed_sample_one_gives_the_agent_dependent_rules_no_agent_claim(warrants):
    composed = compose("all_agent", "plant", DEFECTS, warrants, sample("plant", failure="malformed"))
    assert composed.store.claims == ()


def test_a_sample_records_claims_are_read_back_with_the_findings_they_cite():
    (formula,) = written_claims(sample("plant", FORMULA))
    assert formula.cites == ("total_cost equals labor_cost + parts_cost for all rows",)
    tampered = sample("plant", FORMULA)
    tampered["claims"][0]["statement"] = "Something else."
    with pytest.raises(ValueError, match="differ from its output"):
        written_claims(tampered)


def test_each_rule_names_its_prompt_variant_and_an_unknown_rule_is_refused(warrants):
    assert [variant_of(r) for r in ("empty", "all_person", "all_agent", "settlement_abstain")] == [
        None, None, "confident", "abstain"]
    with pytest.raises(ValueError, match="unknown allocation rule"):
        compose("hybrid", "plant", DEFECTS, warrants, PLANT)
    with pytest.raises(ValueError, match="needs sample 1"):
        compose("settlement", "plant", DEFECTS, warrants)
