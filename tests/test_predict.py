"""Predicted outcomes and the bridge prediction under the baseline battery (#37).

Every test runs on the work-order fixture through `tests/fixtures/freeze_predictions.yaml`, never on
the release, and no test calls a model.
"""

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

from warrant.battery.normalise import normalise_database
from warrant.battery.settings import Normalisation
from warrant.defects.build import Built, DriftType, build, content_hash
from warrant.defects.inject import load_defect
from warrant.freeze.validate import read_schema, validate
from warrant.store.claims import ClaimKind, PredictedOutcome
from warrant.write_line.predict import (
    MIXED,
    BatterySettings,
    ReadingResult,
    combine,
    main,
    outcome,
    predict,
)

FIXTURES = Path(__file__).parent / "fixtures"
FREEZE = FIXTURES / "freeze_predictions.yaml"
RAW = yaml.safe_load(FREEZE.read_text())
DEFECTS = [load_defect(d) for d in RAW["defects"]]
SETTINGS = BatterySettings.from_freeze(RAW)


def clean_workorders(folder: Path) -> Path:
    path = folder / "workorders.sqlite"
    con = sqlite3.connect(path)
    con.executescript((FIXTURES / "workorders.sql").read_text())
    con.commit()
    con.close()
    return path


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    """The freeze next to a clean work-order database, as its `databases:` paths expect."""
    folder = tmp_path_factory.mktemp("freeze")
    clean_workorders(folder)
    shutil.copy(FREEZE, folder)
    return folder


@pytest.fixture(scope="module")
def clean(folder):
    return {name: folder / path for name, path in RAW["databases"].items()}


@pytest.fixture(scope="module")
def built(folder, clean):
    return build(DEFECTS, clean, folder / "out")


@pytest.fixture(scope="module")
def predictions(built, clean, folder):
    return predict(DEFECTS, built, clean, SETTINGS, folder / "battery")


# The acceptance criteria -----------------------------------------------------------------------------


def test_a_swapped_code_value_meaning_defect_is_predicted_person_only_and_the_battery_cannot_tell_its_drift_reading(
    predictions,
):
    assert predictions.claims["site-swap"].outcome == PredictedOutcome.PERSON_ONLY
    bridge = predictions.bridge["site-swap"]
    assert (bridge.drift_reading, bridge.drift_type) == ("as-named", DriftType.CONVENTION)
    assert bridge.battery_tells_apart is False


def test_a_column_formula_data_change_within_the_identity_searchs_reach_is_predicted_agent_alone(
    folder, predictions,
):
    schema = {name: read_schema(folder / path) for name, path in RAW["databases"].items()}
    errors, warnings = validate(RAW, schema)
    assert errors == [] and not [w for w in warnings if "reach" in w]
    assert predictions.claims["total-is-sum"].outcome == PredictedOutcome.AGENT_ALONE
    assert {r.reading: r.differs for r in predictions.claims["total-is-sum"].readings} == {
        "labour-and-parts": False, "labour-only": True, "as-released": True,
    }
    assert predictions.bridge["total-is-sum"].battery_tells_apart is True


def test_a_coverage_defect_that_leaves_child_rows_on_a_same_named_key_is_not_predicted_person_only(predictions):
    claim = predictions.claims["open-orders-cut"]
    assert claim.outcome != PredictedOutcome.PERSON_ONLY
    # The battery tells the cut from "nothing was cut", but not from mistyped references, under which
    # the reference claim fails: the battery narrows the readings and a person picks among the rest.
    assert claim.outcome == PredictedOutcome.BOTH
    assert {r.reading: r.differs for r in claim.readings}["mistyped-references"] is False
    assert predictions.bridge["open-orders-cut"].battery_tells_apart is True


def test_per_kind_predictions_follow_the_combination_rule_in_the_global_part(predictions):
    assert predictions.claims["tasks-short-cut"].outcome == PredictedOutcome.AGENT_ALONE
    assert predictions.kinds == {
        ClaimKind.COVERAGE: MIXED,  # agent alone and both
        ClaimKind.COLUMN_FORMULA: PredictedOutcome.AGENT_ALONE,
        ClaimKind.VALUE_MEANING: PredictedOutcome.PERSON_ONLY,
    }
    assert SETTINGS.per_kind_combination == "the prediction all claims of the kind share, else mixed"


# The outcome rule and the combination rule -----------------------------------------------------------


def reading(name, differs, holds):
    return ReadingResult(name, database="d", output="o", differs=differs, holds=holds)


TRUE = reading("true", False, True)


@pytest.mark.parametrize("rivals, expected", [
    ([reading("a", True, False), reading("b", False, True)], PredictedOutcome.AGENT_ALONE),
    ([reading("a", True, False), reading("b", False, False)], PredictedOutcome.BOTH),
    ([reading("a", False, False)], PredictedOutcome.PERSON_ONLY),
    # The degenerate case both rules cover: no reading differs and the claim holds under all of them.
    # Person only comes first.
    ([reading("a", False, True)], PredictedOutcome.PERSON_ONLY),
])
def test_the_predicted_outcome_follows_the_readings_outputs_and_holds_flags(rivals, expected):
    assert outcome([TRUE, *rivals]) == expected


def test_a_kind_gets_the_prediction_its_claims_share_else_mixed():
    assert combine([PredictedOutcome.BOTH, PredictedOutcome.BOTH]) == PredictedOutcome.BOTH
    assert combine([PredictedOutcome.BOTH, PredictedOutcome.PERSON_ONLY]) == MIXED


# One battery run per database, with the freeze's settings --------------------------------------------


def test_readings_that_share_a_content_hash_share_one_battery_run(built, clean, tmp_path):
    runs = []

    def battery(db, today, work_dir, settings):
        runs.append((content_hash(db.path), today, settings))
        return b""

    predict(DEFECTS, built, clean, SETTINGS, tmp_path, battery=battery)
    distinct = {h for r in built.readings.values() for h in r.values()}
    assert sorted(h for h, _, _ in runs) == sorted(distinct)
    assert {(today, settings) for _, today, settings in runs} == {("2026-10-12", Normalisation())}


def test_the_battery_reads_each_readings_database_with_the_declared_foreign_keys(built, clean, tmp_path):
    keys = []

    def battery(db, today, work_dir, settings):
        keys.append(tuple(db.foreign_keys))
        return normalise_database(db, today, work_dir, settings)

    predict(DEFECTS[1:2], built, clean, SETTINGS, tmp_path, battery=battery)
    assert {tuple((k.table, k.column, k.ref_table, k.ref_column) for k in ks) for ks in keys} == {
        (("tasks", "wonum", "workorders", "wonum"),)
    }


def test_the_battery_settings_are_read_from_the_freeze():
    raw = {**RAW, "global": {**RAW["global"], "battery": {**RAW["global"]["battery"],
                                                          "normalisation": {"counts": "round", "percentages": "drop"}}}}
    settings = BatterySettings.from_freeze(raw)
    assert settings.normalisation == Normalisation("round", "drop")
    assert (settings.fixed_date, settings.duckdb_version) == ("2026-10-12", "1.5.5")


@pytest.mark.parametrize("change", [
    {"duckdb_version": "0.0.1"},
    {"battery": {**RAW["global"]["battery"], "pairing": "both_directions"}},
    {"battery": {**RAW["global"]["battery"], "peers": "every_table"}},
])
def test_prediction_refuses_settings_the_battery_does_not_run_with(built, clean, tmp_path, change):
    settings = BatterySettings.from_freeze({**RAW, "global": {**RAW["global"], **change}})
    with pytest.raises(ValueError):
        predict(DEFECTS, built, clean, settings, tmp_path, battery=lambda *a: b"")


# The command and its record -----------------------------------------------------------------------------


def injection_record(built: Built, freeze: Path, **change) -> dict:
    """The parts of #36's injection record the command reads, as `warrant.defects.build` writes it."""
    return {
        "commit": "c0ffee" * 6 + "abcd",
        "freeze_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(),
        "outcome": "built",
        "injected": built.injected,
        "readings": built.readings,
        "drift": {d: {"reading": r, "type": t.value, "expected": t.value} for d, (r, t) in built.drift.items()},
        **change,
    }


def command(folder, built, tmp_path, **change):
    record = tmp_path / "injection.json"
    record.write_text(json.dumps(injection_record(built, folder / FREEZE.name, **change)))
    out = tmp_path / "predictions"
    code = main(["--freeze", str(folder / FREEZE.name), "--injection-record", str(record),
                 "--built", str(built.out), "--out-dir", str(out)])
    return code, out


def test_the_command_writes_the_predictions_and_the_normalised_outputs_for_a_person_to_commit(
    folder, built, predictions, tmp_path,
):
    code, out = command(folder, built, tmp_path)
    assert code == 0
    [path] = out.glob("*.json")
    assert path.name == "c0ffeec0ffee-freeze_predictions.json"
    written = json.loads(path.read_text())
    assert written["commit"].startswith("c0ffee")
    assert written["settings"]["per_kind_combination"] == RAW["global"]["per_kind_combination"]
    assert written["settings"]["fixed_date"] == "2026-10-12"
    assert written["kinds"] == {"coverage": "mixed", "column_formula": "agent_alone", "value_meaning": "person_only"}
    assert written["claims"]["site-swap"]["outcome"] == "person_only"
    assert written["bridge"]["site-swap"] == {"drift_reading": "as-named", "drift_type": "convention",
                                              "battery_tells_apart": False}
    # Each distinct database's normalised output is committed beside the record, named by its content hash.
    assert set(written["outputs"]) == set(predictions.outputs)
    for content, entry in written["outputs"].items():
        data = (out / entry["file"]).read_bytes()
        assert data == predictions.outputs[content]
        assert entry["sha256"] == hashlib.sha256(data).hexdigest() and entry["records"] == data.count(b"\n")
    # No local path, and no database, goes into what is committed.
    text = path.read_text()
    assert str(folder) not in text and str(tmp_path) not in text
    assert all(not p.name.endswith(".sqlite") for p in out.rglob("*"))


@pytest.mark.parametrize("change, reason", [
    ({"outcome": "failed"}, "not built"),
    ({"freeze_sha256": "0" * 64}, "freeze"),
])
def test_the_command_refuses_an_injection_record_that_is_not_of_this_freeze_or_did_not_build(
    folder, built, tmp_path, capsys, change, reason,
):
    code, out = command(folder, built, tmp_path, **change)
    assert code == 1 and reason in capsys.readouterr().out
    assert not out.exists()


def test_the_command_refuses_a_copy_whose_content_differs_from_its_name(folder, built, tmp_path, capsys):
    fake = tmp_path / "fake"
    shutil.copytree(built.out / "copies", fake / "copies")
    victim = fake / "copies" / f"{built.injected['plant']}.sqlite"
    victim.chmod(0o644)
    con = sqlite3.connect(victim)
    with con:
        con.execute("DELETE FROM tasks")
    con.close()
    code, out = command(folder, Built(fake, built.injected, built.readings, built.drift, ()), tmp_path)
    assert code == 1 and "content" in capsys.readouterr().out
    assert not out.exists()
