"""The warrant kind and Toulmin record of each claim a store holds (#50), computed from the committed
predictions and the freeze's reading kinds with no model call: data on a settled slot; on an
unsettled one, the reference claim's declaration or testimony warrant, with a testimony qualifier
that follows the surviving readings; none for any other agent claim."""

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from warrant.store.claims import PredictedOutcome, Source, WarrantKind
from warrant.write_line.config import load_config
from warrant.write_line.warrants import (
    BATTERY_BACKING,
    PERSON_BACKING,
    PROVENANCE_RECORD,
    STRONGER_BATTERY,
    claim_for,
    out_of_slot_claim,
    slot_warrants,
)

REPO = Path(__file__).resolve().parents[1]
PREDICTIONS = REPO / "predictions" / "9cfd501f2182-write_line.json"


@pytest.fixture
def config():
    return load_config(REPO / "configs" / "write_line_pilot.yaml")


@pytest.fixture
def predictions():
    return json.loads(PREDICTIONS.read_text())


def defect(config, defect_id):
    return next(d for d in config.defects if d.id == defect_id)


def with_readings(d, change):
    """The defect with its readings changed by `change(reading) -> reading`."""
    return dataclasses.replace(d, readings=tuple(change(dict(r)) for r in d.readings))


def test_the_frozen_slots_get_data_testimony_and_declaration(config, predictions):
    warrants = slot_warrants(config.defects, predictions)
    assert warrants["wallet-sum"].person == WarrantKind.DATA and warrants["wallet-sum"].agent == WarrantKind.DATA
    assert warrants["orders-cut"].person == WarrantKind.TESTIMONY and warrants["orders-cut"].agent == WarrantKind.NONE
    assert warrants["seeing-recode"].person == WarrantKind.DECLARATION and warrants["seeing-recode"].agent == WarrantKind.NONE
    assert {d: w.outcome for d, w in warrants.items()} == {
        "wallet-sum": PredictedOutcome.AGENT_ALONE, "orders-cut": PredictedOutcome.BOTH,
        "seeing-recode": PredictedOutcome.PERSON_ONLY}


def test_the_coverage_claims_qualifier_is_a_record_of_how_the_data_came_to_be(config, predictions):
    # orders-cut's surviving rivals (archived, other-system, mistyped) are provenance readings that
    # share the injected copy, so no stronger battery on this database could settle the claim.
    assert slot_warrants(config.defects, predictions)["orders-cut"].qualifier == PROVENANCE_RECORD


def test_a_person_only_slot_whose_rivals_are_provenance_readings_gets_testimony(config, predictions):
    seeing = with_readings(defect(config, "seeing-recode"),
                           lambda r: {**r, "kind": "provenance"} if not r["is_true"] else r)
    w = slot_warrants([seeing], predictions)["seeing-recode"]
    assert (w.person, w.qualifier) == (WarrantKind.TESTIMONY, PROVENANCE_RECORD)


def test_a_person_only_slot_whose_rival_changes_the_database_gets_testimony_a_stronger_battery_could_settle(config, predictions):
    # A rival the battery cannot tell apart although its database differs: a data part the battery missed.
    seeing = with_readings(defect(config, "seeing-recode"),
                           lambda r: {**{k: v for k, v in r.items() if k != "kind"}, "form": "world_fixed"} if not r["is_true"] else r)
    changed = copy.deepcopy(predictions)
    changed["claims"]["seeing-recode"]["readings"]["three-is-best"]["database"] = "f" * 64
    w = slot_warrants([seeing], changed)["seeing-recode"]
    assert (w.person, w.qualifier) == (WarrantKind.TESTIMONY, STRONGER_BATTERY)


def test_both_qualifiers_are_given_when_both_kinds_of_rival_survive(config, predictions):
    changed = copy.deepcopy(predictions)
    changed["claims"]["orders-cut"]["readings"]["filled-cut"]["differs"] = False  # now survives, another database
    w = slot_warrants(config.defects, changed)["orders-cut"]
    assert w.qualifier == f"{STRONGER_BATTERY}; {PROVENANCE_RECORD}"


def test_a_convention_rival_makes_a_person_only_slot_a_declaration_even_beside_a_provenance_rival(config, predictions):
    seeing = defect(config, "seeing-recode")
    extra = {**next(r for r in seeing.readings if not r["is_true"]), "id": "lost-export", "kind": "provenance"}
    mixed = dataclasses.replace(seeing, readings=seeing.readings + (extra,))
    changed = copy.deepcopy(predictions)
    changed["claims"]["seeing-recode"]["readings"]["lost-export"] = dict(changed["claims"]["seeing-recode"]["readings"]["three-is-best"])
    assert slot_warrants([mixed], changed)["seeing-recode"].person == WarrantKind.DECLARATION


def test_a_slot_without_committed_predictions_is_refused(config, predictions):
    changed = copy.deepcopy(predictions)
    del changed["claims"]["seeing-recode"]
    with pytest.raises(ValueError, match="seeing-recode"):
        slot_warrants(config.defects, changed)


def test_an_agent_claim_on_a_settled_slot_carries_a_data_warrant_and_the_findings_it_cites(config, predictions):
    w = slot_warrants(config.defects, predictions)
    wallet = defect(config, "wallet-sum")
    claim = claim_for(wallet, w["wallet-sum"], Source.AGENT, "walletsum is availsum plus frozensum plus margsum.",
                      cites=("walletsum equals availsum + frozensum + margsum for all 1,000 rows",))
    assert claim.warrant == WarrantKind.DATA and claim.predicted_outcome == PredictedOutcome.AGENT_ALONE
    assert claim.toulmin.backing == BATTERY_BACKING
    assert claim.toulmin.data == "walletsum equals availsum + frozensum + margsum for all 1,000 rows"


def test_a_reference_claim_carries_the_persons_backing_and_its_qualifier(config, predictions):
    w = slot_warrants(config.defects, predictions)
    orders = defect(config, "orders-cut")
    claim = claim_for(orders, w["orders-cut"], Source.PERSON, orders.reference_claim)
    assert claim.source == Source.PERSON and claim.warrant == WarrantKind.TESTIMONY
    assert (claim.toulmin.backing, claim.toulmin.qualifier) == (PERSON_BACKING, PROVENANCE_RECORD)
    assert claim.predicted_outcome == PredictedOutcome.BOTH


def test_the_reference_claim_on_a_settled_slot_carries_a_data_warrant(config, predictions):
    w = slot_warrants(config.defects, predictions)
    wallet = defect(config, "wallet-sum")
    claim = claim_for(wallet, w["wallet-sum"], Source.PERSON, wallet.reference_claim)
    assert claim.warrant == WarrantKind.DATA and claim.toulmin.backing == BATTERY_BACKING


def test_an_agent_claim_left_on_an_unsettled_slot_carries_no_warrant(config, predictions):
    w = slot_warrants(config.defects, predictions)
    seeing = defect(config, "seeing-recode")
    claim = claim_for(seeing, w["seeing-recode"], Source.AGENT, "'1' is the best seeing.", cites=())
    assert claim.warrant == WarrantKind.NONE and claim.toulmin.backing == "" and claim.toulmin.qualifier == ""
    assert claim.predicted_outcome == PredictedOutcome.PERSON_ONLY


def test_an_agent_claim_on_the_coverage_slot_carries_no_warrant_and_not_the_persons_qualifier(config, predictions):
    w = slot_warrants(config.defects, predictions)
    claim = claim_for(defect(config, "orders-cut"), w["orders-cut"], Source.AGENT, "The orders table is complete.",
                      cites=("266 rows reference a missing order",))
    assert (claim.warrant, claim.toulmin.backing, claim.toulmin.qualifier) == (WarrantKind.NONE, "", "")
    assert claim.toulmin.data == "266 rows reference a missing order"


def test_a_rival_under_which_the_reference_claim_holds_neither_survives_nor_qualifies(config, predictions):
    # Give seeing-recode a second, holding, convention rival: it must not be what makes the slot a declaration.
    seeing = defect(config, "seeing-recode")
    holding = {**next(r for r in seeing.readings if not r["is_true"]), "id": "also-true", "holds": True}
    provenance = with_readings(seeing, lambda r: {**r, "kind": "provenance"} if not r["is_true"] else r)
    mixed = dataclasses.replace(provenance, readings=provenance.readings + (holding,))
    changed = copy.deepcopy(predictions)
    changed["claims"]["seeing-recode"]["readings"]["also-true"] = {
        **changed["claims"]["seeing-recode"]["readings"]["three-is-best"], "holds": True}
    w = slot_warrants([mixed], changed)["seeing-recode"]
    assert (w.person, w.qualifier) == (WarrantKind.TESTIMONY, PROVENANCE_RECORD)


def test_a_both_slot_whose_only_survivor_changes_the_database_needs_a_stronger_battery(config, predictions):
    orders = defect(config, "orders-cut")
    world = with_readings(orders, lambda r: {k: v for k, v in r.items() if k != "kind"} | {"form": "world_fixed"}
                          if r["id"] in ("archived", "other-system", "mistyped") else r)
    # Put the true reading last, so nothing depends on its position.
    world = dataclasses.replace(world, readings=tuple(r for r in world.readings if not r["is_true"])
                                + tuple(r for r in world.readings if r["is_true"]))
    changed = copy.deepcopy(predictions)
    for reading in ("archived", "other-system", "mistyped"):
        changed["claims"]["orders-cut"]["readings"][reading]["database"] = "e" * 64
    assert slot_warrants([world], changed)["orders-cut"].qualifier == STRONGER_BATTERY


def test_a_both_slot_with_a_surviving_convention_rival_is_refused(config, predictions):
    orders = with_readings(defect(config, "orders-cut"), lambda r: {**r, "kind": "convention"} if r["id"] == "archived" else r)
    with pytest.raises(ValueError, match="does not cover"):
        slot_warrants([orders], predictions)


def test_a_testimony_with_nothing_to_say_what_could_settle_it_is_refused(config, predictions):
    # A world-fixed rival on the true reading's own database: neither a data part nor provenance.
    seeing = with_readings(defect(config, "seeing-recode"),
                           lambda r: {k: v for k, v in r.items() if k != "kind"} | {"form": "world_fixed"} if not r["is_true"] else r)
    with pytest.raises(ValueError, match="nothing says what could settle it"):
        slot_warrants([seeing], predictions)


def test_a_reading_missing_from_the_predictions_or_disagreeing_on_holds_is_refused(config, predictions):
    missing = copy.deepcopy(predictions)
    del missing["claims"]["orders-cut"]["readings"]["archived"]
    with pytest.raises(ValueError, match="'archived' has no committed prediction"):
        slot_warrants(config.defects, missing)
    flipped = copy.deepcopy(predictions)
    flipped["claims"]["orders-cut"]["readings"]["archived"]["holds"] = True
    with pytest.raises(ValueError, match="holds differs"):
        slot_warrants(config.defects, flipped)


def test_an_out_of_slot_claim_keeps_its_kind_and_subject_and_carries_no_warrant():
    claim = out_of_slot_claim("coverage", "orderexecutions", " 266 executions have no order. ", cites=("a finding",))
    assert (claim.slot.claim_kind, claim.slot.subject, claim.statement) == ("coverage", "orderexecutions", "266 executions have no order.")
    assert (claim.warrant, claim.predicted_outcome, claim.toulmin.data) == (WarrantKind.NONE, None, "a finding")
