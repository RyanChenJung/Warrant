import json
import sqlite3

from warrant.data.week_one import check_release, render_markdown

GARAGE_SQL = """
    CREATE TABLE workorders (
        wonum TEXT PRIMARY KEY,
        status TEXT,
        priority TEXT,
        labour REAL,
        parts REAL,
        total REAL,
        hours REAL,
        rate REAL
    );
    CREATE TABLE tasks (
        taskid TEXT PRIMARY KEY,
        woref TEXT REFERENCES workorders (wonum),
        note TEXT
    );
    CREATE TABLE invoices (
        invoiceid TEXT PRIMARY KEY,
        wonum TEXT REFERENCES workorders (wonum),
        paid REAL
    );
"""

GARAGE_MEANINGS = {
    "garage|WorkOrders|WoNum": "Full name: 'Work Order Number'. Explanation: Identifies the work order.",
    "garage|WorkOrders|Status": "Full name: 'Work Order Status'. Possible categories: Open, Closed.",
    "garage|WorkOrders|Priority": "Full name: 'Priority Code'. Explanation: How urgent the work is. "
    "Possible categories: P1, P2, P3.",
    "garage|WorkOrders|Total": "Full name: 'Total Cost'.",
}

GARAGE_KB = [
    {"id": 0, "knowledge": "Priority: P1", "description": "The most urgent code.", "definition": "Fix today.",
     "type": "value_illustration", "children_knowledge": -1},
    {"id": 1, "knowledge": "Urgent work order", "description": "Needs a crew now.",
     "definition": "A work order with $\\text{Priority} = 'P1'$.", "type": "domain_knowledge",
     "children_knowledge": -1},
    {"id": 2, "knowledge": "Labour share", "description": "Share of labour in the total.",
     "definition": "$\\text{Labour} / \\text{Total}$", "type": "calculation_knowledge", "children_knowledge": -1},
]


def garage_rows(con):
    """Every row satisfies total = labour + parts; rate = labour / hours is a ratio, not a sum."""
    for i in range(1, 25):
        labour, parts, hours = 10.0 * i + 3, 7.5 * i + 1, 1.0 + 0.25 * i
        con.execute(
            "INSERT INTO workorders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"WO{i:02d}", ("Open", "Closed")[i % 2], f"P{i % 3 + 1}", labour, parts, labour + parts, hours,
             labour / hours),
        )
        con.execute("INSERT INTO tasks VALUES (?, ?, ?)", (f"T{i:02d}", f"WO{i % 3 + 1:02d}", "checked"))
        con.execute("INSERT INTO invoices VALUES (?, ?, ?)", (f"I{i:02d}", f"WO{i:02d}", 5.0 * i))


LIBRARY_SQL = """
    CREATE TABLE books (bookid TEXT PRIMARY KEY, title TEXT);
    INSERT INTO books VALUES ('B1', 'Emma'), ('B2', 'Ulysses'), ('B3', 'Beloved');
"""


def make_database(root, name, sql, meanings, kb, rows=None):
    """One database laid out as in the release: template SQLite file, column meanings, knowledge base."""
    folder = root / name
    folder.mkdir(parents=True)
    con = sqlite3.connect(folder / f"{name}_template.sqlite")
    con.executescript(sql)
    if rows:
        rows(con)
    con.commit()
    con.close()
    (folder / f"{name}_column_meaning_base.json").write_text(json.dumps(meanings))
    (folder / f"{name}_kb.jsonl").write_text("".join(json.dumps(e) + "\n" for e in kb))


def garage_report(tmp_path):
    make_database(tmp_path, "garage", GARAGE_SQL, GARAGE_MEANINGS, GARAGE_KB, garage_rows)
    return check_release(tmp_path, ["garage"])["databases"]["garage"]


def test_finds_a_total_that_is_the_sum_of_two_other_columns(tmp_path):
    identities = garage_report(tmp_path)["column_formula"]["identities"]
    assert [(i["table"], i["target"], i["components"]) for i in identities] == [
        ("workorders", "total", ["labour", "parts"])
    ]
    assert identities[0]["share"] == 1.0
    assert identities[0]["rows"] == 24
    assert identities[0]["positions"] == {"total": 3, "labour": 1, "parts": 2}


def test_does_not_report_a_ratio_as_an_identity(tmp_path):
    identities = garage_report(tmp_path)["column_formula"]["identities"]
    assert "rate" not in {i["target"] for i in identities}


def test_lists_tables_with_three_numeric_columns_as_injectable(tmp_path):
    injectable = garage_report(tmp_path)["column_formula"]["injectable_tables"]
    assert injectable == [{"table": "workorders", "numeric_columns": ["labour", "parts", "total", "hours", "rate"],
                           "declared_keys": []}]


def test_finds_a_coded_column_whose_codes_the_column_meanings_list(tmp_path):
    coded = {(c["table"], c["column"]): c for c in garage_report(tmp_path)["value_meaning"]}
    priority = coded[("workorders", "priority")]
    assert sorted(v["value"] for v in priority["values"]) == ["P1", "P2", "P3"]
    assert priority["documented"] is True
    assert priority["kb_mentions_column"] == [0, 1]
    assert priority["kb_mentions_value"] == {"P1": [0, 1]}
    assert priority["kb_value_illustrations"] == [0]


def test_coded_columns_skip_declared_key_columns_even_with_few_distinct_values(tmp_path):
    coded = {(c["table"], c["column"]) for c in garage_report(tmp_path)["value_meaning"]}
    assert ("tasks", "woref") not in coded
    assert coded == {("workorders", "status"), ("workorders", "priority")}


def test_finds_a_status_column_with_the_tables_related_on_declared_foreign_keys(tmp_path):
    report = garage_report(tmp_path)
    first = report["coverage"][0]
    assert (first["table"], first["column"], first["status_like"]) == ("workorders", "status", True)
    assert report["related_tables"]["workorders"] == [
        {"related_table": "invoices", "direction": "referenced by", "from": "invoices.wonum",
         "to": "workorders.wonum", "same_named": True},
        {"related_table": "tasks", "direction": "referenced by", "from": "tasks.woref",
         "to": "workorders.wonum", "same_named": False},
    ]


def test_pairs_cover_every_kind_when_one_database_offers_all_three(tmp_path):
    make_database(tmp_path, "garage", GARAGE_SQL, GARAGE_MEANINGS, GARAGE_KB, garage_rows)
    make_database(tmp_path, "library", LIBRARY_SQL, {}, [])
    report = check_release(tmp_path, ["garage", "library"])
    assert [r["database"] for r in report["ranking"]] == ["garage", "library"]
    assert [p["databases"] for p in report["pairs"]] == [["garage", "library"]]


def test_report_says_so_when_no_pair_offers_every_kind(tmp_path):
    make_database(tmp_path, "library", LIBRARY_SQL, {}, [])
    make_database(tmp_path, "archive", LIBRARY_SQL, {}, [])
    report = check_release(tmp_path, ["library", "archive"])
    assert report["pairs"] == []
    assert report["suggested_pair"] is None
    assert "No pair of databases offers a candidate of each kind" in render_markdown(report)


def test_markdown_report_notes_the_synthetic_data_caveat_and_the_thresholds(tmp_path):
    make_database(tmp_path, "garage", GARAGE_SQL, GARAGE_MEANINGS, GARAGE_KB, garage_rows)
    text = render_markdown(check_release(tmp_path, ["garage"]))
    assert "more synthetic than BIRD" in text
    assert "0.005" in text and "80%" in text and "first 12" in text
