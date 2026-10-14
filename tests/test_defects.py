import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import Response, ResponseKind
from warrant.data.release import sha256
from warrant.defects.audit import Recoding
from warrant.defects.inject import Defect, inject
from warrant.store.claims import ClaimKind, Slot
from warrant.write_line.config import load_config
from warrant.write_line.run import run

FIXTURES = Path(__file__).parent / "fixtures"

SWAP_SITES = "UPDATE workorders SET site = CASE site WHEN 'NORTH' THEN 'SOUTH' WHEN 'SOUTH' THEN 'NORTH' END"
TOTAL_IS_LABOR_AND_PARTS = {
    "table": "workorders", "target": "total_cost", "form": "sum", "operands": ["labor_cost", "parts_cost"],
}


def value_meaning(*transformation):
    return Defect("recode", "workorders", Slot(ClaimKind.VALUE_MEANING, "workorders.site"), transformation, "claim")


def column_formula(*transformation):
    return Defect(
        "formula",
        "workorders",
        Slot(ClaimKind.COLUMN_FORMULA, "workorders.total_cost"),
        transformation,
        "claim",
        relation=TOTAL_IS_LABOR_AND_PARTS,
    )


def table(path, name):
    con = sqlite3.connect(path)
    try:
        cursor = con.execute(f"SELECT * FROM {name} ORDER BY rowid")
        return [column[0] for column in cursor.description], cursor.fetchall()
    finally:
        con.close()


def test_a_swapped_code_leaves_row_counts_and_every_other_column_unchanged_and_audits_the_mapping(
    workorders_db, tmp_path
):
    copy = tmp_path / "work" / "workorders.sqlite"
    (audit,) = inject(workorders_db, copy, [value_meaning(SWAP_SITES)])

    columns, before = table(workorders_db, "workorders")
    _, after = table(copy, "workorders")
    site = columns.index("site")
    assert len(after) == len(before)
    assert [row[:site] + row[site + 1 :] for row in after] == [row[:site] + row[site + 1 :] for row in before]
    assert table(copy, "tasks") == table(workorders_db, "tasks")
    assert audit.rows == {"workorders": (12, 12)}
    assert audit.recoding == (
        Recoding("workorders", "site", "NORTH", "SOUTH", 7),
        Recoding("workorders", "site", "SOUTH", "NORTH", 5),
    )


def test_a_recoding_to_new_codes_audits_each_code_it_replaced(workorders_db, tmp_path):
    recode = "UPDATE workorders SET site = CASE site WHEN 'NORTH' THEN '1' WHEN 'SOUTH' THEN '2' END"
    (audit,) = inject(workorders_db, tmp_path / "work" / "workorders.sqlite", [value_meaning(recode)])
    assert audit.recoding == (
        Recoding("workorders", "site", "NORTH", "1", 7),
        Recoding("workorders", "site", "SOUTH", "2", 5),
    )
    assert audit.changed == 12


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE workorders SET site = 'NORTH'",  # two codes merged into one
        "UPDATE workorders SET site = site || wonum",  # one code split into many
        "DELETE FROM workorders WHERE site = 'SOUTH'",  # rows removed
    ],
)
def test_a_value_meaning_defect_that_does_not_recode_one_to_one_is_refused(workorders_db, tmp_path, statement):
    with pytest.raises(ValueError, match="one-to-one"):
        inject(workorders_db, tmp_path / "work" / "workorders.sqlite", [value_meaning(statement)])


def test_a_column_formula_data_change_makes_the_declared_relation_hold_and_the_audit_says_so(workorders_db, tmp_path):
    change = "UPDATE workorders SET total_cost = ROUND(labor_cost + parts_cost, 2)"
    (audit,) = inject(workorders_db, tmp_path / "work" / "workorders.sqlite", [column_formula(change)])
    assert audit.relation == "total_cost = labor_cost + parts_cost"
    assert audit.holds == (12, 12)
    assert audit.changed == 12
    assert audit.rows == {"workorders": (12, 12)}


def test_a_stipulated_column_formula_convention_leaves_the_database_unchanged(workorders_db, tmp_path):
    copy = tmp_path / "work" / "workorders.sqlite"
    (audit,) = inject(workorders_db, copy, [column_formula()])
    assert sha256(copy) == sha256(workorders_db)
    assert audit.rows == {}
    assert audit.changed == 0
    # The convention is stipulated, not made true in the data: the release's total carries overhead.
    assert audit.holds == (0, 12)


def test_every_injected_defect_leaves_its_audit_record_beside_the_copy(workorders_db, tmp_path):
    copy = tmp_path / "work" / "workorders.sqlite"
    coverage = Defect(
        "short-tasks-cut", "workorders", Slot(ClaimKind.COVERAGE, "tasks"), ("DELETE FROM tasks WHERE hours < 1",), "claim"
    )
    inject(workorders_db, copy, [coverage, value_meaning(SWAP_SITES)])
    records = json.loads(copy.with_suffix(".audit.json").read_text())
    assert [r["defect"] for r in records] == ["short-tasks-cut", "recode"]
    assert records[0]["rows"] == {"tasks": [23, 17]}
    assert records[1]["recoding"][0] == {"table": "workorders", "column": "site", "old": "NORTH", "new": "SOUTH", "rows": 7}


# Behaviour at the write-line entry point. Per configuration, the SQL an agent writes for the probe
# without the reference claim in its store, and with it; the control question is answered alike.
PROBES = {
    "write_line_value_meaning.yaml": (
        {"north-orders": "SELECT COUNT(*) FROM workorders WHERE site = 'NORTH'"},
        {"north-orders": "SELECT COUNT(*) FROM workorders WHERE site = 'SOUTH'"},
    ),
    "write_line_column_formula.yaml": (
        {"closed-cost-with-parts": "SELECT SUM(total_cost + parts_cost) FROM workorders WHERE status = 'CLOSED'"},
        {"closed-cost-with-parts": "SELECT SUM(total_cost) FROM workorders WHERE status = 'CLOSED'"},
    ),
}
CONTROL = {"task-hours": "SELECT SUM(hours) FROM tasks"}


@pytest.mark.parametrize("name", PROBES)
def test_the_reference_claim_raises_accuracy_over_the_empty_store_at_the_entry_point(name, workorders_db, tmp_path):
    config = load_config(Path(shutil.copy(FIXTURES / name, workorders_db.parent)))
    (defect,) = config.defects
    without_claim, with_claim = PROBES[name]

    def script(request, tools):
        knows = any(claim.slot == defect.slot for claim in request.store.claims)
        sql = {**CONTROL, **(with_claim if knows else without_claim)}[request.question_id]
        return Response(ResponseKind.ANSWER, final_sql=sql, value=tools["sql"](sql))

    result = run(config, ScriptedAgent(script), tmp_path / "work")
    assert result.accuracy == {"empty": 0.5, "all_person": 1.0}
    assert result.audits[defect.id].rows == {"workorders": (12, 12)}
