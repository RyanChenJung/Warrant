"""The blind audit's sheet and its agreement with the judge (#123, `global.judge.audit`): the sheet
shows each distinct agent claim on a slot with the slot's readings in the frozen reading order, and
never the judge's labels, the true reading or the defect; agreement is computed afterwards from the
filled sheet, the key the lead keeps and the judgement records of the run the freeze uses. No model
is called."""

import json
from pathlib import Path

import pytest

from warrant.store.results import Provenance, append
from warrant.write_line.audit import (
    FIELDS,
    SheetError,
    agreement,
    audit_items,
    main,
    read_key,
    read_sheet,
    sheet_rows,
    used_run,
    write_key,
    write_sheet,
)
from warrant.write_line.config import load_config
from warrant.write_line.judging import reading_orders_for

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "write_line_pilot.yaml"
PROVENANCE = Provenance(config_hash="0" * 64, repo_commit="abc1234", model="anthropic.claude-sonnet-5", prompt_version="1")
ORDERS_CLAIM = "The orders table is missing orders whose executions and fees are still recorded."
SEEING_CLAIM = "In observatories.seeingprofile, '1' marks the best seeing and '3' the worst."
RUN = "r2"


@pytest.fixture
def config():
    return load_config(CONFIG)


@pytest.fixture
def orders(config):
    return reading_orders_for(config)


def judgement(config, defect, sample, index, claim, labels=None, run=RUN, **extra):
    order = reading_orders_for(config)[defect]
    slot = next(d.slot for d in config.defects if d.id == defect)
    return {
        "run_id": run, "record": "judgement", "defect": defect, "sample": sample, "index": index,
        "complete": True, "error": "", "slot": {"claim_kind": slot.claim_kind, "subject": slot.subject},
        "claim": claim, "reading_order": list(order),
        "labels": labels or {reading: "fails" for reading in order}, "without_a_call": sample > 1, **extra,
    }


@pytest.fixture
def records(config, orders):
    holds = {reading: "holds" for reading in orders["orders-cut"]}
    seeing = orders["seeing-recode"]
    return [
        # An abandoned first run, never complete: the audit leaves it out.
        {"run_id": "r1", "record": "start"},
        judgement(config, "orders-cut", 1, 0, "A claim only the abandoned run wrote.", run="r1"),
        {"run_id": RUN, "record": "start"},
        judgement(config, "orders-cut", 1, 1, ORDERS_CLAIM, holds),
        judgement(config, "orders-cut", 2, 0, ORDERS_CLAIM, holds),  # the same claim string again
        judgement(config, "seeing-recode", 1, 0, SEEING_CLAIM, {seeing[0]: "holds", seeing[1]: "fails"}),
        judgement(config, "wallet-sum", 3, 0, "walletsum is availsum plus frozensum.", complete=False, error="timed out"),
        {"run_id": RUN, "record": "complete"},
        {"run_id": "v1", "operation": "judge_validation", "record": "complete"},
    ]


def filled(config, records, label_for):
    items = audit_items(records, used_run(records))
    rows = sheet_rows(items, config)
    for row in rows:
        row["label"] = label_for(row)
    return items, rows


def test_the_audit_uses_the_first_run_with_a_complete_record(records):
    assert used_run(records) == RUN


def test_results_with_no_complete_run_have_nothing_to_audit(records):
    with pytest.raises(ValueError, match="no run"):
        used_run([r for r in records if r.get("record") != "complete" or r.get("operation")])


def test_each_distinct_complete_claim_on_a_slot_of_the_run_is_one_item_with_all_its_occurrences(records):
    items = audit_items(records, RUN)
    assert [(i.defect, i.claim) for i in items] == [("orders-cut", ORDERS_CLAIM), ("seeing-recode", SEEING_CLAIM)]
    assert items[0].occurrences == ((1, 1), (2, 0))
    assert [i.id for i in items] == ["C01", "C02"]


def test_the_sheet_shows_claims_and_readings_in_the_frozen_order_and_nothing_that_gives_the_answer(config, records, orders):
    rows = sheet_rows(audit_items(records, RUN), config)
    statements = {r["id"]: r["statement"].strip() for d in config.defects for r in d.readings}
    first = [row for row in rows if row["item"] == "C01"]
    assert [row["letter"] for row in first] == list("ABCDEFG")
    assert [row["reading"] for row in first] == [statements[reading] for reading in orders["orders-cut"]]
    assert {row["subject"] for row in first} == {"orders"} and {row["claim"] for row in first} == {ORDERS_CLAIM}
    assert all(row["label"] == "" and row["notes"] == "" for row in rows)
    assert tuple(rows[0]) == FIELDS
    text = repr(rows)
    assert "orders-cut" not in text and "cancelled-cut" not in text and "is_true" not in text
    assert not [value for row in rows for value in row.values() if value in ("holds", "fails", "not_addressed")]


def test_agreement_counts_each_claim_and_reading_pair_of_the_key_against_the_judges_label(config, records, tmp_path):
    def label(row):
        if row["item"] == "C01":
            return "holds" if row["letter"] != "A" else "fails"  # one disagreement
        return " Holds " if row["letter"] == "A" else ""  # case and spaces forgiven; one blank
    items, rows = filled(config, records, label)
    write_sheet(tmp_path / "sheet.csv", rows)
    report = agreement(read_sheet(tmp_path / "sheet.csv"), items, records, RUN)
    assert (report.pairs, report.labelled, report.agree) == (9, 8, 7)
    assert report.missing == [("C02", "B")] and report.invalid == []
    assert report.by_defect == {"orders-cut": (6, 7), "seeing-recode": (1, 1)}
    assert report.confusion[("holds", "fails")] == 1


@pytest.mark.parametrize("typed", ["not addressed", "Not-Addressed", " not_addressed "])
def test_not_addressed_is_read_however_its_separator_is_typed(config, records, typed):
    items, rows = filled(config, records, lambda row: typed)
    report = agreement(rows, items, records, RUN)
    assert report.labelled == 9 and report.invalid == []


def test_a_label_outside_the_three_is_reported_by_item_and_letter_not_counted(config, records):
    items, rows = filled(config, records, lambda row: "maybe" if (row["item"], row["letter"]) == ("C01", "A") else "fails")
    report = agreement(rows, items, records, RUN)
    assert report.invalid == [("C01", "A")] and report.labelled == 8


def test_a_row_missing_from_the_sheet_counts_as_missing(config, records):
    items, rows = filled(config, records, lambda row: "fails")
    report = agreement([r for r in rows if (r["item"], r["letter"]) != ("C01", "C")], items, records, RUN)
    assert report.pairs == 9 and report.missing == [("C01", "C")]


@pytest.mark.parametrize("change", ["duplicate", "unknown item", "unknown letter"])
def test_a_duplicate_or_unknown_row_is_refused_with_its_row_number(config, records, change):
    items, rows = filled(config, records, lambda row: "fails")
    if change == "duplicate":
        rows.append(dict(rows[0]))
    elif change == "unknown item":
        rows.append({**rows[0], "item": "C99"})
    else:
        rows.append({**rows[0], "letter": "Z"})
    with pytest.raises(SheetError, match=f"sheet row {len(rows) + 1}"):
        agreement(rows, items, records, RUN)


def test_a_sheet_saved_by_a_spreadsheet_with_a_byte_order_mark_and_blank_rows_reads_back(config, records, tmp_path):
    items, rows = filled(config, records, lambda row: "fails")
    path = tmp_path / "sheet.csv"
    write_sheet(path, rows)
    path.write_bytes(path.read_bytes().rstrip(b"\r\n") + b"\r\n,,,,,,,\r\n")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert read_sheet(path) == rows


def test_a_sheet_with_other_columns_is_refused(tmp_path):
    (tmp_path / "sheet.csv").write_text("item,label\nC01,holds\n")
    with pytest.raises(SheetError, match="columns"):
        read_sheet(tmp_path / "sheet.csv")


def test_notes_are_kept_per_item_and_agreement_is_also_given_without_noted_items(config, records):
    items, rows = filled(config, records, lambda row: "holds")
    for row in rows:
        if (row["item"], row["letter"]) == ("C02", "A"):
            row["notes"] = "used an assistant to rephrase the claim"
    report = agreement(rows, items, records, RUN)
    assert report.notes == {"C02": "used an assistant to rephrase the claim"}
    assert report.without_noted == (7, 7) and (report.agree, report.labelled) == (8, 9)


def test_the_key_names_the_run_every_occurrence_and_letter(records, orders, tmp_path):
    items = audit_items(records, RUN)
    write_key(tmp_path / "key.json", RUN, items)
    key = json.loads((tmp_path / "key.json").read_text())
    assert key["run_id"] == RUN
    assert key["items"]["C01"]["defect"] == "orders-cut" and key["items"]["C01"]["occurrences"] == [[1, 1], [2, 0]]
    assert list(key["items"]["C01"]["letters"].values()) == list(orders["orders-cut"])
    run, back = read_key(tmp_path / "key.json")
    assert run == RUN and [(i.id, i.defect, i.occurrences, i.letters) for i in back] == [
        (i.id, i.defect, i.occurrences, i.letters) for i in items]


def test_the_command_writes_a_blind_sheet_and_a_key_then_reports_and_records_agreement(records, tmp_path, capsys):
    results = tmp_path / "results.jsonl"
    for record in records:
        append(results, PROVENANCE, record)
    sheet, key, out = tmp_path / "sheet.csv", tmp_path / "key.json", tmp_path / "audit.jsonl"
    assert main(["sheet", "--config", str(CONFIG), "--results", str(results), "--sheet", str(sheet), "--key", str(key)]) == 0
    assert all(row["label"] == "" for row in read_sheet(sheet)) and "orders-cut" not in sheet.read_text()
    rows = read_sheet(sheet)
    for row in rows:
        row["label"] = "fails"
    write_sheet(sheet, rows)
    capsys.readouterr()
    assert main(["agreement", "--results", str(results), "--sheet", str(sheet), "--key", str(key),
                 "--auditor", "juan-de-haro", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "auditor and judge agree on 1 of 9 labelled pairs (9 in the key, 0 blank or absent, 0 invalid)" in printed
    audits = [json.loads(line) for line in out.read_text().splitlines()]
    assert [a["item"] for a in audits] == ["C01", "C02"] and {a["auditor"] for a in audits} == {"juan-de-haro"}
    assert {a["run_id"] for a in audits} == {RUN} and set(audits[0]["labels"].values()) == {"fails"}


def test_audit_records_need_the_auditors_name(records, tmp_path):
    results = tmp_path / "results.jsonl"
    for record in records:
        append(results, PROVENANCE, record)
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.json"
    main(["sheet", "--config", str(CONFIG), "--results", str(results), "--sheet", str(sheet), "--key", str(key)])
    with pytest.raises(SystemExit):
        main(["agreement", "--results", str(results), "--sheet", str(sheet), "--key", str(key), "--out", str(tmp_path / "a.jsonl")])
