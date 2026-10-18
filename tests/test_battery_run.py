import sqlite3

import warrant.battery.run as run
from warrant.battery.gloss.detect import build_context, run_all
from warrant.battery.gloss.model import AssertionType
from warrant.data.export import peers_of
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


def add_tickets(shop_release):
    """A table the ordinal-direction probe has something to say about: the higher the priority
    number, the longer a ticket stays open."""
    con = sqlite3.connect(shop_release / "shop" / "shop_template.sqlite")
    con.executescript("""
        CREATE TABLE Tickets (TicketId TEXT PRIMARY KEY, Priority INTEGER, Opened TEXT, Closed TEXT);
        INSERT INTO Tickets WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 30)
            SELECT printf('T%02d', i), i % 3 + 1, date('2026-03-01', '+' || i || ' days'),
                   date('2026-03-01', '+' || (i + CASE i % 3 WHEN 0 THEN 1 WHEN 1 THEN 6 ELSE 30 END) || ' days')
            FROM n;
    """)
    con.commit()
    con.close()


def contexts(shop_release, tmp_path):
    """The database opened as the battery reads it, and a fresh context per table with its peers."""
    db = load_database(shop_release, "shop")
    conn, export = run.open_database(db, tmp_path / "work")
    context = lambda table: build_context(conn, table, TODAY, peers=peers_of(db.foreign_keys, table))
    return db, conn, [t.name for t in export.tables], context


def test_the_run_includes_the_ordinal_direction_probe_as_run_all_does(shop_release, tmp_path):
    add_tickets(shop_release)
    probed = [f.assertion for f in battery(shop_release, tmp_path)["Tickets"]
              if f.assertion.statement.startswith("Direction established by behavioural probe")]

    assert [(a.type, a.subject) for a in probed] == [(AssertionType.FIELD, "Tickets.Priority")]
    assert "lower numbers are acted on sooner" in probed[0].statement
    assert battery(shop_release, tmp_path / "again")["Tickets"][-1].assertion == probed[0]  # the probe runs last


def test_with_no_declared_keys_the_run_equals_run_all_exactly(shop_release, tmp_path):
    add_tickets(shop_release)
    _, _, tables, context = contexts(shop_release, tmp_path)

    assert "Tickets" in tables
    for table in tables:
        released = run_all(context(table))
        assert released
        assert run.run_checks(context(table), declared_keys=()) == released


def test_the_run_equals_run_all_apart_from_the_findings_on_declared_key_pairs(shop_release, tmp_path):
    add_tickets(shop_release)
    db, conn, tables, context = contexts(shop_release, tmp_path)
    extra = {}
    for table in tables:
        ours = run.run_detectors(conn, table, TODAY, db.foreign_keys)
        released = run_all(context(table))
        assert [f for f in ours if f in released] == released  # same findings, same order
        extra[table] = [f.assertion for f in ours if f not in released]

    assert {table: len(found) for table, found in extra.items()} == {
        "Customers": 0, "Holidays": 0, "OrderLines": 1, "Orders": 3, "Tickets": 0}
    assert all(a.type is AssertionType.LINK for found in extra.values() for a in found)
    assert extra["OrderLines"][0].statement.startswith("OrderRef joins to Orders.OrderId")
    assert [a.subject for a in extra["Orders"]] == ["Orders.CustRef", "Orders.CustRef", "Customers.CustRegistry"]
