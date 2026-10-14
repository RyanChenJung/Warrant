import dataclasses
import json
import math
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

import warrant.battery.normalise as normalise
from warrant.battery.gloss.model import (
    Assertion, AssertionType, Finding, Question, QuoteEvidence, SqlEvidence, Tier)
from warrant.battery.normalise import EXACT, Normalisation, normalise_database, normalised_bytes, record
from warrant.data.release import load_database

FIXTURES = Path(__file__).parent / "fixtures"
FREEZE = FIXTURES / "freeze_valid.yaml"
TODAY = "2026-10-12"


def finding(statement, expected, sql="SELECT 1", measured_at=TODAY, question=None, impact=0.0, type=AssertionType.LINK):
    assertion = Assertion(type=type, subject="Orders.CustRef", statement=statement, tier=Tier.MEASURED,
                          evidence=(SqlEvidence(sql=sql, expected=expected, measured_at=measured_at),))
    return Finding(assertion=assertion, question=question, impact=impact)


def question(text, cost_seconds, priority):
    return Question(subject="Orders.CustRef", text=text, proposed_answer="a typo", options=("a typo", "a new customer"),
                    basis="the link check", cost_seconds=cost_seconds, priority=priority)


def lines(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


def shop(shop_release):
    return load_database(shop_release, "shop")


def change_one_order(path):
    con = sqlite3.connect(path)
    con.execute("UPDATE Orders SET Status = 'Cancelled' WHERE OrderId = 'O01'")
    con.commit()
    con.close()


# Determinism --------------------------------------------------------------------------------------


def test_two_runs_on_the_same_database_give_byte_identical_output(shop_release, tmp_path):
    first = normalise_database(shop(shop_release), TODAY, tmp_path / "a")
    second = normalise_database(shop(shop_release), TODAY, tmp_path / "b")

    assert first and first == second


def test_measured_at_and_other_timestamps_are_dropped_from_the_output(shop_release, tmp_path):
    # In the vendored detectors the run date reaches only the evidence's measured_at, so two dates
    # give the same output once timestamps are dropped. A detector that reads the date (a SCOPE check
    # on how recent the data is, say) could legitimately change its findings with it; that is why
    # the freeze fixes the date (global.fixed_date) and the command reads it from there.
    assert (normalise_database(shop(shop_release), TODAY, tmp_path / "a")
            == normalise_database(shop(shop_release), "2031-01-02", tmp_path / "b"))


def test_records_are_sorted_by_their_canonical_json_and_duplicates_are_kept():
    a, b = finding("b statement", 2), finding("a statement", 1)
    data = normalised_bytes([a, b, a])

    assert [r["statement"] for r in lines(data)] == ["a statement", "b statement", "b statement"]
    canonical = [json.dumps(record(f), sort_keys=True, separators=(",", ":"), ensure_ascii=False) for f in (b, a, a)]
    assert data == ("\n".join(canonical) + "\n").encode("utf-8")


# The record form -----------------------------------------------------------------------------------


def test_a_record_is_check_subject_statement_and_evidence_pairs():
    f = finding("1 rows (4.17%) reference a value that does not exist, for example 'C99'.", [1, "C99"],
                sql="SELECT COUNT(*),\n       MIN(c.\"CustRef\")\n  FROM \"Orders\" c  ")

    assert record(f) == {
        "check": "LINK",
        "subject": "Orders.CustRef",
        "statement": "1 rows (4.17%) reference a value that does not exist, for example 'C99'.",
        "evidence": [["SELECT COUNT(*), MIN(c.\"CustRef\") FROM \"Orders\" c", [1, "C99"]]],
    }


def test_output_drops_timestamps_question_text_costs_priorities_and_impact():
    plain = finding("Holds 2 distinct values: Filled (18), Cancelled (6).", [["Filled", 18], ["Cancelled", 6]])
    asked = finding("Holds 2 distinct values: Filled (18), Cancelled (6).", [["Filled", 18], ["Cancelled", 6]],
                    measured_at="2031-01-02", question=question("What does Cancelled mean?", 45, 0.9), impact=0.25)
    data = normalised_bytes([asked])

    assert set(lines(data)[0]) == {"check", "subject", "statement", "evidence"}
    assert normalised_bytes([plain]) == data
    for dropped in ("2031-01-02", "What does Cancelled mean?", "45", "0.9", "0.25", "MEASURED", "gloss", plain.assertion.id):
        assert dropped not in data.decode("utf-8")


def test_the_battery_output_on_a_database_carries_no_date_and_no_question(shop_release, tmp_path):
    text = normalise_database(shop(shop_release), "2031-01-02", tmp_path / "work").decode("utf-8")

    assert "2031-01-02" not in text
    assert "What do" not in text and "no definition in any available documentation" not in text
    assert all(set(r) == {"check", "subject", "statement", "evidence"} for r in map(json.loads, text.splitlines()))


def test_evidence_results_are_written_as_json_values():
    f = finding("Mixed.", [None, True, 3, 95.83, 1e-05, "2026-01-01", "naïve", math.nan, math.inf, -math.inf])
    data = normalised_bytes([f])

    assert lines(data)[0]["evidence"][0][1] == [
        None, True, 3, 95.83, 1e-05, "2026-01-01", "naïve", "NaN", "Infinity", "-Infinity"]
    assert "naïve".encode("utf-8") in data


def test_quote_evidence_is_refused_rather_than_dropped():
    assertion = Assertion(type=AssertionType.RULE, subject="Orders.Total", statement="Documented.", tier=Tier.MEASURED,
                          evidence=(SqlEvidence(sql="SELECT 1", expected=1, measured_at=TODAY),
                                    QuoteEvidence(quote="Net plus tax", source="shop_dictionary", locator="x")))
    with pytest.raises(TypeError):
        record(Finding(assertion=assertion))


# Counts and percentages ----------------------------------------------------------------------------

STATEMENT = ("963 of 1,000 rows (95.83%) join, 1 rows (4.17%) do not, for example 'C99'; "
             "codes C99 and O24 from 2026-01-01, fee 0.25.")
EXPECTED = [963, 95.83, True, "C99", None, 1]


@pytest.mark.parametrize("settings, statement, expected", [
    (Normalisation(counts="keep", percentages="keep"), STATEMENT, EXPECTED),
    (Normalisation(counts="round", percentages="keep"),
     "960 of 1000 rows (95.83%) join, 1 rows (4.17%) do not, for example 'C99'; "
     "codes C99 and O24 from 2026-01-01, fee 0.25.",
     [960, 95.83, True, "C99", None, 1]),
    (Normalisation(counts="drop", percentages="keep"),
     "# of # rows (95.83%) join, # rows (4.17%) do not, for example 'C99'; "
     "codes C99 and O24 from 2026-01-01, fee 0.25.",
     ["#", 95.83, True, "C99", None, "#"]),
    (Normalisation(counts="keep", percentages="round"),
     "963 of 1,000 rows (96%) join, 1 rows (4%) do not, for example 'C99'; "
     "codes C99 and O24 from 2026-01-01, fee 0.25.",
     [963, 96.0, True, "C99", None, 1]),
    (Normalisation(counts="keep", percentages="drop"),
     "963 of 1,000 rows (#%) join, 1 rows (#%) do not, for example 'C99'; "
     "codes C99 and O24 from 2026-01-01, fee 0.25.",
     [963, "#", True, "C99", None, 1]),
], ids=["keep", "counts-round", "counts-drop", "percentages-round", "percentages-drop"])
def test_counts_and_percentages_are_kept_rounded_or_dropped_as_configured(settings, statement, expected):
    r = record(finding(STATEMENT, EXPECTED), settings)

    assert r["statement"] == statement
    assert r["evidence"][0][1] == expected


def test_exact_keeps_every_number_and_is_the_default():
    f = finding(STATEMENT, EXPECTED)

    assert EXACT == Normalisation(counts="keep", percentages="keep")
    assert record(f) == record(f, EXACT)
    assert record(f)["statement"] == STATEMENT and record(f)["evidence"][0][1] == EXPECTED


def test_per_code_frequencies_are_counts():
    f = finding("Holds 2 distinct values: Filled (18), Cancelled (6).", [["Filled", 18], ["Cancelled", 6]])

    assert record(f, Normalisation(counts="drop"))["statement"] == "Holds # distinct values: Filled (#), Cancelled (#)."
    assert record(f, Normalisation(counts="round"))["evidence"][0][1] == [["Filled", 18], ["Cancelled", 6]]


def test_rounding_lets_two_close_counts_agree_and_dropping_lets_any_two_agree():
    near = finding("1,000 rows.", 1000), finding("998 rows.", 998)
    far = finding("1,000 rows.", 1000), finding("12 rows.", 12)

    assert normalised_bytes([near[0]]) != normalised_bytes([near[1]])
    assert normalised_bytes([near[0]], Normalisation(counts="round")) == normalised_bytes([near[1]], Normalisation(counts="round"))
    assert normalised_bytes([far[0]], Normalisation(counts="round")) != normalised_bytes([far[1]], Normalisation(counts="round"))
    assert normalised_bytes([far[0]], Normalisation(counts="drop")) == normalised_bytes([far[1]], Normalisation(counts="drop"))


# The setting ---------------------------------------------------------------------------------------


def test_the_setting_is_read_from_the_global_part_of_the_freeze():
    raw = yaml.safe_load(FREEZE.read_text())

    assert Normalisation.from_freeze(raw) == EXACT
    raw["global"]["battery"]["normalisation"] = {"counts": "round", "percentages": "drop"}
    assert Normalisation.from_freeze(raw) == Normalisation(counts="round", percentages="drop")


@pytest.mark.parametrize("value", ["rounded", None, {"counts": "keep"}, {"counts": "keep", "percentages": "half"},
                                   {"counts": "keep", "percentages": "keep", "codes": "drop"}])
def test_an_unknown_setting_is_refused(value):
    with pytest.raises(ValueError):
        Normalisation.parse(value)


# Databases -----------------------------------------------------------------------------------------


def test_two_databases_that_differ_in_the_rows_of_one_table_give_different_output(shop_release, tmp_path):
    db = shop(shop_release)
    copy = tmp_path / "readings" / "shop-r2.sqlite"
    copy.parent.mkdir()
    shutil.copy(db.path, copy)
    change_one_order(copy)

    clean = normalise_database(db, TODAY, tmp_path / "a")
    changed = normalise_database(dataclasses.replace(db, path=copy), TODAY, tmp_path / "b")

    assert clean != changed
    assert "Filled (17), Cancelled (7)" in changed.decode("utf-8")


def test_an_unchanged_copy_at_another_path_gives_the_clean_output(shop_release, tmp_path):
    db = shop(shop_release)
    copy = tmp_path / "elsewhere" / "deeper" / "copy.sqlite"
    copy.parent.mkdir(parents=True)
    shutil.copy(db.path, copy)

    assert (normalise_database(dataclasses.replace(db, path=copy), TODAY, tmp_path / "b")
            == normalise_database(db, TODAY, tmp_path / "a"))


# The command ---------------------------------------------------------------------------------------


def test_the_command_reads_the_setting_and_the_date_from_the_freeze(shop_release, tmp_path, monkeypatch):
    raw = yaml.safe_load(FREEZE.read_text())
    raw["global"]["fixed_date"] = "2030-05-06"
    raw["global"]["battery"]["normalisation"] = {"counts": "drop", "percentages": "drop"}
    freeze = tmp_path / "freeze.yaml"
    freeze.write_text(yaml.safe_dump(raw))
    dates = []
    run_battery = normalise.run_battery
    monkeypatch.setattr(normalise, "run_battery", lambda db, today, work_dir: dates.append(today) or run_battery(db, today, work_dir))
    out = tmp_path / "out" / "shop.jsonl"

    assert normalise.main(["--freeze", str(freeze), "--release-dir", str(shop_release), "--database", "shop",
                           "--out", str(out)]) == 0
    assert dates == ["2030-05-06"]
    assert out.read_bytes() == normalise_database(shop(shop_release), TODAY, tmp_path / "w",
                                                  Normalisation(counts="drop", percentages="drop"))


def test_the_command_runs_on_a_copy_at_another_path(shop_release, tmp_path):
    db = shop(shop_release)
    copy = tmp_path / "copy.sqlite"
    shutil.copy(db.path, copy)
    change_one_order(copy)
    out = tmp_path / "copy.jsonl"

    assert normalise.main(["--freeze", str(FREEZE), "--release-dir", str(shop_release), "--database", "shop",
                           "--sqlite", str(copy), "--out", str(out)]) == 0
    assert out.read_bytes() == normalise_database(dataclasses.replace(db, path=copy), TODAY, tmp_path / "w")
