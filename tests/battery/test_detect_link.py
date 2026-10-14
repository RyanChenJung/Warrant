import duckdb

from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.link import LinkDetector
from warrant.battery.gloss.evidence import verify
from warrant.battery.gloss.model import AssertionType


def _run(mini_conn):
    ctx = build_context(mini_conn, "wo_history", "2026-08-23",
                        peers={"assets": "assets"})
    return LinkDetector().run(ctx)


def _joins(mini_conn):
    return {f.assertion.subject: f for f in _run(mini_conn)
            if "joins to" in f.assertion.statement}


def test_finds_join_pairs_despite_case_difference(mini_conn):
    # wo_history has ASSETNUM and LOCATION; assets has assetnum and location.
    # Both are real join paths, so both are reported.
    joins = _joins(mini_conn)
    assert set(joins) == {"wo_history.ASSETNUM", "wo_history.LOCATION"}
    a = joins["wo_history.ASSETNUM"]
    assert "assets" in a.assertion.statement
    assert a.assertion.type is AssertionType.LINK


def test_reports_the_match_rate_and_cardinality(mini_conn):
    a = _joins(mini_conn)["wo_history.ASSETNUM"]
    s = a.assertion.statement
    assert "100.0%" in s
    assert "many-to-one" in s      # assets.assetnum is unique; wo repeats it
    assert "fan out" in s          # explicitly states sums will not inflate


def test_reports_reverse_coverage(mini_conn):
    got = [f for f in _run(mini_conn) if "never referenced" in f.assertion.statement]
    assert len(got) == 1
    assert "1 of 4" in got[0].assertion.statement   # A400 has no work orders


def test_unmatched_keys_produce_a_question():
    conn = duckdb.connect()
    conn.execute("CREATE TABLE child AS SELECT * FROM (VALUES ('A1'),('A2'),('A9')) "
                 "t(ASSETNUM)")
    conn.execute("CREATE TABLE master AS SELECT * FROM (VALUES ('A1'),('A2')) "
                 "t(assetnum)")
    ctx = build_context(conn, "child", "2026-08-23", peers={"master": "master"})
    got = [f for f in LinkDetector().run(ctx) if f.question]
    assert got, "an unmatched key should be worth one question"
    assert "A9" in got[0].assertion.statement or "33" in got[0].assertion.statement
    assert got[0].question.proposed_answer


def test_no_peers_means_no_findings(mini_conn):
    assert LinkDetector().run(
        build_context(mini_conn, "wo_history", "2026-08-23")) == []


def test_every_assertion_carries_re_runnable_sql(mini_conn):
    for f in _run(mini_conn):
        assert verify(mini_conn, f.assertion.evidence[0]).status == "PASS"
