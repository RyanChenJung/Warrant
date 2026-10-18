import csv
import re

import pytest

from warrant.battery.gloss.source import columns, open_workspace, row_count
from warrant.data.export import export_database, format_cell, peers_of
from warrant.data.release import load_database, sha256

SCIENTIFIC = re.compile(r"^-?\d+(\.\d+)?[eE][-+]?\d+$")


def read(table):
    with open(table.path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def exported(shop_release, tmp_path):
    return export_database(load_database(shop_release, "shop").path, tmp_path / "csv")


def test_every_table_is_exported_under_its_declared_name_with_its_declared_columns(shop_release, tmp_path):
    tables = {t.name: t for t in exported(shop_release, tmp_path).tables}

    assert list(tables) == ["Customers", "Holidays", "OrderLines", "Orders"]
    assert tables["Orders"].path.name == "Orders.csv"
    assert read(tables["Orders"])[0] == [
        "OrderId", "CustRef", "Status", "Net", "Tax", "Shipping", "Total", "Fee", "Note"]
    assert read(tables["Customers"])[0] == ["CustRegistry", "Region", "Tier"]


def test_the_detectors_workspace_sees_the_declared_names_and_every_row(shop_release, tmp_path):
    conn = open_workspace(exported(shop_release, tmp_path).tables, cache_dir=tmp_path / "cache")

    assert columns(conn, "OrderLines") == ["LineId", "OrderRef", "Qty"]
    assert {t: row_count(conn, t) for t in ("Customers", "Holidays", "OrderLines", "Orders")} == {
        "Customers": 8, "Holidays": 3, "OrderLines": 48, "Orders": 24}


def test_no_exported_number_is_in_scientific_notation(shop_release, tmp_path):
    tables = {t.name: t for t in exported(shop_release, tmp_path).tables}
    rows = read(tables["Orders"])

    assert rows[1][7] == "0.00001"  # stored as 1e-05
    assert not [cell for t in tables.values() for row in read(t) for cell in row if SCIENTIFIC.match(cell)]


@pytest.mark.parametrize("value, text", [
    (1e-05, "0.00001"), (1.5e-07, "0.00000015"), (1e22, "10000000000000000000000"), (-2.5e-06, "-0.0000025"),
    (5.0, "5.0"), (0.1, "0.1"), (42, "42"), ("1e-05", "1e-05"), (None, ""), ("", ""),
])
def test_a_cell_is_written_positionally_and_text_is_left_alone(value, text):
    assert format_cell(value) == text


def test_a_positional_float_reads_back_as_the_same_number():
    for value in (1e-05, 1.5e-07, 1e22, 0.1 + 0.2, 123456.789):
        assert float(format_cell(value)) == value


def test_a_blob_is_refused():
    with pytest.raises(TypeError):
        format_cell(b"\x00")


def test_empty_strings_export_like_null_and_are_counted(shop_release, tmp_path):
    export = exported(shop_release, tmp_path)
    notes = [row[8] for row in read({t.name: t for t in export.tables}["Orders"])[1:]]

    assert export.empty_string_cells == 4
    assert notes.count("") == 8  # four '' and four NULL


def test_exporting_leaves_the_clean_copy_unchanged(shop_release, tmp_path):
    path = load_database(shop_release, "shop").path
    before = sha256(path)
    export_database(path, tmp_path / "csv")
    assert sha256(path) == before


def test_peers_are_the_tables_linked_by_a_declared_foreign_key_in_either_direction(shop_release):
    keys = load_database(shop_release, "shop").foreign_keys

    assert peers_of(keys, "Orders") == {"Customers": "Customers", "OrderLines": "OrderLines"}
    assert peers_of(keys, "Customers") == {"Orders": "Orders"}
    assert peers_of(keys, "OrderLines") == {"Orders": "Orders"}
    assert peers_of(keys, "Holidays") == {}
