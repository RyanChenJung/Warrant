"""The link detector also pairs key columns on declared foreign keys, child to parent only (#28).

The fixture has the shape of the release's `alien` database: `signals.telescref` references
`telescopes.telescregistry` under a different name, and `telescopes.observstation` references
`observatories.observstation` under the same name.
"""

import types
from pathlib import Path

import duckdb
import pytest

from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.link import LinkDetector
from warrant.battery.gloss.evidence import verify

TODAY = "2026-10-13"
RELEASED_LINK = Path(__file__).parent / "fixtures" / "gloss_release" / "gloss" / "detect" / "link.py.txt"

SIGNALS_TO_TELESCOPES = ("signals", "telescref", "telescopes", "telescregistry")
TELESCOPES_TO_OBSERVATORIES = ("telescopes", "observstation", "observatories", "observstation")
PEERS = {"observatories": "observatories", "telescopes": "telescopes", "signals": "signals"}


@pytest.fixture
def conn():
    """Three tables in memory. Signal S4 references telescope T9, which does not exist, and
    telescope T3 references observatory O9, which does not exist."""
    conn = duckdb.connect()
    conn.execute(
        "CREATE TABLE observatories AS SELECT * FROM (VALUES ('O1'), ('O2')) t(observstation)"
    )
    conn.execute(
        "CREATE TABLE telescopes AS SELECT * FROM "
        "(VALUES ('T1', 'O1'), ('T2', 'O2'), ('T3', 'O9')) t(telescregistry, observstation)"
    )
    conn.execute(
        "CREATE TABLE signals AS SELECT * FROM "
        "(VALUES ('S1', 'T1'), ('S2', 'T1'), ('S3', 'T2'), ('S4', 'T9')) t(signalregistry, telescref)"
    )
    return conn


@pytest.fixture
def released_detector():
    """The link detector exactly as released, run from the committed reference with only its
    import path pointed at the vendored modules."""
    source = RELEASED_LINK.read_text(encoding="utf-8").replace("from gloss.", "from warrant.battery.gloss.")
    module = types.ModuleType("released_link")
    exec(compile(source, str(RELEASED_LINK), "exec"), module.__dict__)
    return module.LinkDetector


def run(conn, table, detector):
    return detector.run(build_context(conn, table, TODAY, peers=PEERS))


def statements(findings):
    return [f.assertion.statement for f in findings]


def test_an_orphan_on_a_differently_named_declared_key_is_reported(conn):
    findings = run(conn, "signals", LinkDetector(declared_keys=[SIGNALS_TO_TELESCOPES]))

    orphans = [f for f in findings if "does not exist there" in f.assertion.statement]
    assert len(orphans) == 1
    assert orphans[0].assertion.subject == "signals.telescref"
    assert "1 rows (25.00%) reference a telescopes.telescregistry value" in orphans[0].assertion.statement
    assert "'T9'" in orphans[0].assertion.statement
    assert orphans[0].question is not None


def test_a_declared_pair_gets_the_checks_a_same_named_pair_gets(conn):
    findings = run(conn, "signals", LinkDetector(declared_keys=[SIGNALS_TO_TELESCOPES]))

    join, orphan, unreferenced = statements(findings)
    assert "telescref joins to telescopes.telescregistry for 75.0% of the 4 rows" in join
    assert "many-to-one" in join
    assert "does not exist there" in orphan
    assert "1 of 3 telescopes.telescregistry values are never referenced by signals.telescref" in unreferenced
    for finding in findings:
        assert verify(conn, finding.assertion.evidence[0]).status == "PASS"


def test_without_declared_keys_the_output_is_the_released_detector_s(conn, released_detector):
    for table in PEERS:
        released = run(conn, table, released_detector())
        assert run(conn, table, LinkDetector()) == released
        assert run(conn, table, LinkDetector(declared_keys=[])) == released
    assert run(conn, "signals", LinkDetector()) == []


def test_same_named_pairing_still_works_beside_a_declared_key(conn, released_detector):
    keys = [SIGNALS_TO_TELESCOPES]
    released = run(conn, "telescopes", released_detector())

    assert any("observstation joins to observatories.observstation" in s for s in statements(released))
    assert any("'O9'" in s for s in statements(released))
    assert run(conn, "telescopes", LinkDetector(declared_keys=keys)) == released


def test_the_parent_is_not_paired_to_its_child(conn):
    findings = run(conn, "telescopes", LinkDetector(declared_keys=[SIGNALS_TO_TELESCOPES]))

    assert not any("signals" in s for s in statements(findings))
    assert not any(f.assertion.subject.startswith("signals.") for f in findings)


def test_a_declared_key_that_is_also_same_named_is_paired_once(conn, released_detector):
    declared = run(conn, "telescopes", LinkDetector(declared_keys=[TELESCOPES_TO_OBSERVATORIES]))

    assert declared == run(conn, "telescopes", released_detector())


def test_a_declared_key_to_a_table_that_is_not_a_peer_is_ignored(conn):
    ctx = build_context(conn, "signals", TODAY, peers={"observatories": "observatories"})

    assert LinkDetector(declared_keys=[SIGNALS_TO_TELESCOPES]).run(ctx) == []
