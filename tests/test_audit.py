"""The blind audit's sheet and its agreement with the judge (#123, `global.judge.audit`): the sheet
shows each distinct agent claim on a slot with the slot's readings in the frozen reading order, and
never the judge's labels, the true reading or the defect; agreement is computed afterwards from the
filled sheet, the key the lead keeps and the judgement records. No model is called."""

import json
from pathlib import Path

import pytest

from warrant.write_line.audit import (
    FIELDS,
    agreement,
    audit_items,
    main,
    read_sheet,
    sheet_rows,
    write_key,
    write_sheet,
)
from warrant.write_line.config import load_config
from warrant.write_line.judging import reading_orders_for
from warrant.store.results import append, Provenance

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "write_line_pilot.yaml"
PROVENANCE = Provenance(config_hash="0" * 64, repo_commit="abc1234", model="anthropic.claude-sonnet-5", prompt_version="1")
ORDERS_CLAIM = "The orders table is missing orders whose executions and fees are still recorded."
SEEING_CLAIM = "In observatories.seeingprofile, '1' marks the best seeing and '3' the worst."


@pytest.fixture
def config():
    return load_config(CONFIG)


def judgement(config, defect, sample, index, claim, labels=None, **extra):
    order = reading_orders_for(config)[defect]
    slot = next(d.slot for d in config.defects if d.id == defect)
    return {
        "record": "judgement", "defect": defect, "sample": sample, "index": index, "complete": True,
        "error": "", "slot": {"claim_kind": slot.claim_kind, "subject": slot.subject}, "claim": claim,
        "reading_order": list(order), "labels": labels or {reading: "fails" for reading in order},
        "without_a_call": sample > 1, **extra,
    }


@pytest.fixture
def judgements(config):
    orders = {reading: "holds" for reading in reading_orders_for(config)["orders-cut"]}
    seeing = reading_orders_for(config)["seeing-recode"]
    return [
        judgement(config, "orders-cut", 1, 1, ORDERS_CLAIM, orders),
        judgement(config, "orders-cut", 2, 0, ORDERS_CLAIM, orders),  # the same claim string again
        judgement(config, "seeing-recode", 1, 0, SEEING_CLAIM, {seeing[0]: "holds", seeing[1]: "fails"}),
        judgement(config, "wallet-sum", 3, 0, "walletsum is availsum plus frozensum.", complete=False, error="timed out"),
    ]


def test_each_distinct_complete_claim_on_a_slot_is_one_item_with_all_its_occurrences(judgements):
    items = audit_items(judgements)
    assert [(i.defect, i.claim) for i in items] == [("orders-cut", ORDERS_CLAIM), ("seeing-recode", SEEING_CLAIM)]
    assert items[0].occurrences == ((1, 1), (2, 0))
    assert [i.id for i in items] == ["C01", "C02"]


def test_the_sheet_shows_claims_and_readings_in_the_frozen_order_and_nothing_that_gives_the_answer(config, judgements):
    rows = sheet_rows(audit_items(judgements), config)
    orders = reading_orders_for(config)["orders-cut"]
    statements = {r["id"]: r["statement"].strip() for d in config.defects for r in d.readings}
    first = [row for row in rows if row["item"] == "C01"]
    assert [row["letter"] for row in first] == list("ABCDEFG")
    assert [row["reading"] for row in first] == [statements[reading] for reading in orders]
    assert {row["subject"] for row in first} == {"orders"} and {row["claim"] for row in first} == {ORDERS_CLAIM}
    assert all(row["label"] == "" and row["notes"] == "" for row in rows)
    assert tuple(rows[0]) == FIELDS
    text = repr(rows)
    assert "orders-cut" not in text and "cancelled-cut" not in text and "is_true" not in text
    assert not [value for row in rows for value in row.values() if value in ("holds", "fails", "not_addressed")]


def test_agreement_counts_each_claim_and_reading_pair_against_the_judges_label(config, judgements, tmp_path):
    items = audit_items(judgements)
    rows = sheet_rows(items, config)
    for row in rows:
        if row["item"] == "C01":
            row["label"] = "holds" if row["letter"] != "A" else "fails"  # one disagreement
        elif row["letter"] == "A":
            row["label"] = " Holds "  # case and spaces are forgiven
        else:
            row["label"] = ""  # left blank
    write_sheet(tmp_path / "sheet.csv", rows)
    report = agreement(read_sheet(tmp_path / "sheet.csv"), items, judgements)
    assert (report.pairs, report.labelled, report.agree, report.missing, report.invalid) == (9, 8, 7, 1, 0)
    assert report.by_defect == {"orders-cut": (6, 7), "seeing-recode": (1, 1)}
    assert report.confusion[("holds", "fails")] == 1


def test_a_label_outside_the_three_is_reported_not_counted(config, judgements):
    items = audit_items(judgements)
    rows = sheet_rows(items, config)
    rows[0]["label"] = "maybe"
    report = agreement(rows, items, judgements)
    assert report.invalid == 1 and report.labelled == 0


def test_the_command_writes_a_blind_sheet_and_a_key_and_then_reports_agreement(config, judgements, tmp_path, capsys):
    results = tmp_path / "results.jsonl"
    for record in judgements:
        append(results, PROVENANCE, record)
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.json"
    assert main(["sheet", "--config", str(CONFIG), "--results", str(results), "--sheet", str(sheet), "--key", str(key)]) == 0
    assert all(row["label"] == "" for row in read_sheet(sheet)) and "orders-cut" not in sheet.read_text()
    assert "orders-cut" in key.read_text()
    rows = read_sheet(sheet)
    for row in rows:
        row["label"] = "fails"
    write_sheet(sheet, rows)
    assert main(["agreement", "--results", str(results), "--sheet", str(sheet), "--key", str(key)]) == 0
    assert "agree on" in capsys.readouterr().out


def test_the_key_names_every_occurrence_and_letter(config, judgements, tmp_path):
    items = audit_items(judgements)
    write_key(tmp_path / "key.json", items)
    key = json.loads((tmp_path / "key.json").read_text())
    assert key["C01"]["defect"] == "orders-cut" and key["C01"]["occurrences"] == [[1, 1], [2, 0]]
    assert list(key["C01"]["letters"].values()) == list(reading_orders_for(config)["orders-cut"])
