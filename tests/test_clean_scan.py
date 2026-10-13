import ast
import inspect
import json
import shutil

import pytest
import yaml

import warrant.battery.run
import warrant.data.clean_scan as clean_scan
import warrant.data.export
from warrant.battery.gloss.model import AssertionType
from warrant.data.clean_scan import CLAIM_KINDS, render_markdown, scan_database, scan_release
from warrant.data.release import Release

TODAY = "2026-10-12"


def shop(shop_release, tmp_path):
    return scan_database(shop_release, "shop", TODAY, tmp_path / "work")[0]


@pytest.fixture
def fetched(shop_release, tmp_path, monkeypatch):
    """A configuration naming two databases, both fetched into the data directory."""
    monkeypatch.setenv("WARRANT_DATA_DIR", str(tmp_path / "data"))
    config = tmp_path / "release.yaml"
    config.write_text(yaml.safe_dump({"dataset": "team/fixture", "revision": "abc", "databases": ["shop", "store"]}))
    local = Release.from_yaml(config).local_dir()
    shutil.copytree(shop_release, local)
    shutil.copytree(local / "shop", local / "store")
    for path in (local / "store").iterdir():
        path.rename(path.with_name(path.name.replace("shop", "store")))
    return config


def test_every_assertion_type_has_a_fixed_claim_kind_and_term_boundary_has_none():
    assert CLAIM_KINDS == {
        AssertionType.SCOPE: ("coverage",),
        AssertionType.GRAIN: ("grain",),
        AssertionType.FIELD: ("value_meaning",),
        AssertionType.VALUE: ("value_meaning",),
        AssertionType.LINK: ("coverage", "grain"),
        AssertionType.RULE: ("column_formula",),
        AssertionType.LIMIT: ("coverage",),
    }


def test_findings_are_grouped_by_claim_kind_table_and_column(shop_release, tmp_path):
    report = shop(shop_release, tmp_path)
    grouped, findings = report["by_claim_kind"], report["findings"]

    assert list(grouped) == ["coverage", "grain", "value_meaning", "column_formula", "term_boundary"]
    assert grouped["term_boundary"] == {}
    assert [findings[i]["assertion_type"] for i in grouped["column_formula"]["Orders"]["Total"]] == ["RULE"]
    assert "Status" in grouped["value_meaning"]["Orders"]
    for kind, tables in grouped.items():
        for table, columns in tables.items():
            for column, indexes in columns.items():
                for i in indexes:
                    assert kind in findings[i]["claim_kinds"]
                    assert findings[i]["subject"] == (table if column == "(table)" else f"{table}.{column}")
    assert sum(len(f["claim_kinds"]) for f in findings) == sum(
        len(indexes) for tables in grouped.values() for columns in tables.values() for indexes in columns.values())


def test_a_link_finding_is_listed_under_coverage_and_under_grain(shop_release, tmp_path):
    report = shop(shop_release, tmp_path)
    links = [i for i, f in enumerate(report["findings"]) if f["assertion_type"] == "LINK"]

    assert links
    for i in links:
        finding = report["findings"][i]
        assert finding["claim_kinds"] == ["coverage", "grain"]
        table, _, column = finding["subject"].partition(".")
        assert i in report["by_claim_kind"]["coverage"][table][column]
        assert i in report["by_claim_kind"]["grain"][table][column]


def test_a_finding_about_a_peer_column_is_grouped_under_the_peer_and_keeps_the_table_scanned(shop_release, tmp_path):
    report = shop(shop_release, tmp_path)
    unreferenced = [f for f in report["findings"] if f["subject"] == "Customers.CustRegistry" and f["table"] == "Orders"]

    assert [f["assertion_type"] for f in unreferenced] == ["LINK"]
    assert "never referenced" in unreferenced[0]["statement"]


def test_the_identity_search_relations_are_listed_with_their_reach(shop_release, tmp_path):
    assert shop(shop_release, tmp_path)["identity_relations"] == [{
        "table": "Orders", "target": "Total", "components": ["Net", "Tax", "Shipping"],
        "rows": 24, "holds": 24, "share": 1.0,
        "positions": {"Total": 4, "Net": 1, "Tax": 2, "Shipping": 3},
        "pool": ["Net", "Tax", "Shipping", "Total", "Fee"],
    }]


def test_tables_list_their_peers_and_the_empty_string_cells_are_counted(shop_release, tmp_path):
    report = shop(shop_release, tmp_path)

    assert {t: v["peers"] for t, v in report["tables"].items()} == {
        "Customers": ["Orders"], "Holidays": [], "OrderLines": ["Orders"], "Orders": ["Customers", "OrderLines"]}
    assert report["empty_string_cells"] == 4


def test_two_scans_with_the_same_date_are_byte_identical(shop_release, tmp_path):
    first, _ = scan_release(shop_release, ["shop"], TODAY, tmp_path / "a")
    second, _ = scan_release(shop_release, ["shop"], TODAY, tmp_path / "b")

    assert json.dumps(first) == json.dumps(second)


def test_the_scan_and_the_battery_run_import_no_agent_or_model_client():
    for module in (clean_scan, warrant.data.export, warrant.battery.run):
        tree = ast.parse(inspect.getsource(module))
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not [n for n in names if n.startswith(("anthropic", "warrant.agent", "boto"))]


def test_the_command_scans_every_database_of_the_configuration_and_records_each_runtime(fetched, tmp_path):
    out = tmp_path / "out"
    clean_scan.main(["--config", str(fetched), "--today", TODAY, "--out-dir", str(out)])

    report = json.loads((out / clean_scan.JSON_NAME).read_text())
    runtimes = json.loads((out / clean_scan.RUNTIMES_NAME).read_text())
    markdown = (out / clean_scan.REPORT_NAME).read_text()
    assert list(report["databases"]) == ["shop", "store"]
    assert report["today"] == TODAY and report["revision"] == "abc"
    assert list(runtimes["seconds"]) == ["shop", "store"]
    assert all(seconds > 0 for seconds in runtimes["seconds"].values())
    assert "runtime" not in json.dumps(report)
    assert "| shop |" in markdown and "| store |" in markdown
    assert not list(tmp_path.rglob("*.csv"))


def test_the_command_needs_a_date(fetched, tmp_path):
    with pytest.raises(SystemExit):
        clean_scan.main(["--config", str(fetched), "--out-dir", str(tmp_path / "out")])


def test_the_report_says_term_boundary_has_no_assertion_type_and_counts_empty_strings(shop_release, tmp_path):
    report, runtimes = scan_release(shop_release, ["shop"], TODAY, tmp_path / "work")
    markdown = render_markdown(report, runtimes)

    assert "No assertion type maps to term boundary" in markdown
    assert "Total = Net + Tax + Shipping" in markdown
    assert "2026-10-12" in markdown
    row = next(line for line in markdown.splitlines() if line.startswith("| shop |"))
    assert [c.strip() for c in row.split("|")][-3] == "4"  # empty-string cells


def test_kept_exports_are_refused_inside_the_repository(fetched, tmp_path):
    with pytest.raises(SystemExit):
        clean_scan.main(["--config", str(fetched), "--today", TODAY, "--out-dir", str(tmp_path / "out"),
                         "--keep-export", str(clean_scan.REPO / "docs" / "export")])
