import warrant.battery.run as run
from warrant.battery.gloss.model import AssertionType
from warrant.data.release import load_database

TODAY = "2026-10-12"


def battery(shop_release, tmp_path, today=TODAY):
    return run.run_battery(load_database(shop_release, "shop"), today, tmp_path / "work")


def test_the_detectors_return_findings_on_the_exported_tables(shop_release, tmp_path):
    findings = battery(shop_release, tmp_path)

    assert list(findings) == ["Customers", "Holidays", "OrderLines", "Orders"]
    assert all(findings.values())
    assert {f.assertion.type for f in findings["Orders"]} >= {
        AssertionType.GRAIN, AssertionType.VALUE, AssertionType.LINK, AssertionType.RULE}


def test_the_identity_search_finds_the_planted_sum(shop_release, tmp_path):
    rules = [f.assertion for f in battery(shop_release, tmp_path)["Orders"] if f.assertion.type is AssertionType.RULE]

    assert [(a.subject, a.statement.split(" for ")[0]) for a in rules] == [
        ("Orders.Total", "Total equals Net + Tax + Shipping")]


def test_a_declared_key_between_differently_named_columns_is_read_from_child_to_parent(shop_release, tmp_path):
    findings = battery(shop_release, tmp_path)
    links = lambda table: [f.assertion.statement for f in findings[table] if f.assertion.type is AssertionType.LINK]

    assert any(s.startswith("CustRef joins to Customers.CustRegistry") for s in links("Orders"))
    assert any("'C99'" in s for s in links("Orders"))
    assert links("Customers") == []
    assert links("Holidays") == []


def test_contexts_get_the_declared_key_peers_and_no_documentation(shop_release, tmp_path, monkeypatch):
    built = []

    def spy(*args, **kwargs):
        ctx = build_context(*args, **kwargs)
        built.append(ctx)
        return ctx

    build_context = run.build_context
    monkeypatch.setattr(run, "build_context", spy)
    battery(shop_release, tmp_path)

    assert {ctx.table: sorted(ctx.peers.values()) for ctx in built} == {
        "Customers": ["Orders"], "Holidays": [], "OrderLines": ["Orders"], "Orders": ["Customers", "OrderLines"]}
    assert all(ctx.dictionary is None for ctx in built)
    assert all(ctx.today == TODAY for ctx in built)


def test_two_runs_with_the_same_date_give_the_same_findings(shop_release, tmp_path):
    assert battery(shop_release, tmp_path / "a") == battery(shop_release, tmp_path / "b")


def test_the_date_given_is_the_date_the_evidence_carries(shop_release, tmp_path):
    findings = battery(shop_release, tmp_path, today="2031-01-02")

    assert {e.measured_at for fs in findings.values() for f in fs for e in f.assertion.evidence} == {"2031-01-02"}
