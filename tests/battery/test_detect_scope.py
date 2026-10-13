from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.scope import ScopeDetector, date_expression
from warrant.battery.gloss.evidence import verify
from warrant.battery.gloss.model import AssertionType


def _run(mini_conn):
    return ScopeDetector().run(build_context(mini_conn, "wo_history", "2026-08-23"))


def test_reports_the_covered_period(mini_conn):
    got = [f for f in _run(mini_conn) if "covers" in f.assertion.statement]
    subjects = {f.assertion.subject for f in got}
    assert "wo_history.SCHEDSTART" in subjects
    s = [f for f in got if f.assertion.subject == "wo_history.SCHEDSTART"][0]
    assert "2023-08-01" in s.assertion.statement
    assert "2023-08-10" in s.assertion.statement
    assert s.assertion.type is AssertionType.SCOPE


def test_flags_the_skewed_status_column_as_possibly_pre_filtered(mini_conn):
    got = [f for f in _run(mini_conn) if "pre-filtered" in f.assertion.statement]
    assert [f.assertion.subject for f in got] == ["wo_history.STATUS"]
    assert "95.0%" in got[0].assertion.statement
    assert "CLOSE" in got[0].assertion.statement


def test_the_skew_question_is_answerable_in_seconds(mini_conn):
    q = [f for f in _run(mini_conn)
         if "pre-filtered" in f.assertion.statement][0].question
    assert q is not None
    assert q.cost_seconds <= 15
    assert set(q.options) >= {"yes", "no", "unsure"}


def test_date_expression_recognises_the_oracle_format(mini_conn):
    expr = date_expression("SCHEDSTART")
    got = mini_conn.sql(f"SELECT MIN({expr}) FROM wo_history").fetchone()[0]
    assert str(got) == "2023-08-01 00:00:00"


def test_date_expression_returns_none_for_a_non_date_column(mini_conn):
    assert date_expression("WORKTYPE", conn=mini_conn, table="wo_history") is None


def test_every_assertion_carries_re_runnable_sql(mini_conn):
    for f in _run(mini_conn):
        assert verify(mini_conn, f.assertion.evidence[0]).status == "PASS"


def test_skew_is_measured_over_the_whole_table_not_the_grain_filter(mini_conn):
    # Restricted to parent rows, ISTASK is trivially all '0' and WOCLASS all
    # 'WORKORDER'. Applying our own filter before asking "is this extract
    # pre-filtered?" manufactures the answer.
    ctx = build_context(mini_conn, "wo_history", "2026-08-23")
    ctx.grain_filter = "(\"PARENT\" IS NULL OR \"PARENT\" = '')"
    subjects = {f.assertion.subject for f in ScopeDetector().run(ctx)
                if "pre-filtered" in f.assertion.statement}
    assert "wo_history.ISTASK" not in subjects
    assert "wo_history.WOCLASS" not in subjects
    assert subjects == {"wo_history.STATUS"}   # the one real finding survives
