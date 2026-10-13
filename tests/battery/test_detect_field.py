from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.field import FieldDetector
from warrant.battery.gloss.dictionary import load_dictionary
from warrant.battery.gloss.evidence import verify
from warrant.battery.gloss.model import AssertionType, Tier


def _run(mini_conn, mini_paths, tmp_path):
    d = load_dictionary(mini_paths["dict"], "WORKORDER", tmp_path / "c")
    return FieldDetector().run(
        build_context(mini_conn, "wo_history", "2026-08-23", dictionary=d))


def test_declared_datetime_with_date_only_values(mini_conn, mini_paths, tmp_path):
    got = [f for f in _run(mini_conn, mini_paths, tmp_path)
           if f.assertion.subject == "wo_history.SCHEDSTART"]
    assert len(got) == 1
    s = got[0].assertion.statement
    assert "DATETIME" in s and "day" in s
    assert got[0].assertion.type is AssertionType.FIELD
    assert got[0].assertion.tier is Tier.MEASURED


def test_documented_range_contradicted_by_observed_range(mini_conn, mini_paths,
                                                         tmp_path):
    got = [f for f in _run(mini_conn, mini_paths, tmp_path)
           if f.assertion.subject == "wo_history.WOPRIORITY"]
    assert len(got) == 1
    s = got[0].assertion.statement
    assert "0-100" in s          # what the vendor documents
    assert "1 to 6" in s         # what the fixture actually holds


def test_detects_non_breaking_spaces(mini_conn, mini_paths, tmp_path):
    got = [f for f in _run(mini_conn, mini_paths, tmp_path)
           if f.assertion.subject == "wo_history.DESCRIPTION"]
    assert len(got) == 1
    assert "non-breaking space" in got[0].assertion.statement
    assert got[0].question is None  # agents normalise; no human decision needed


def test_clean_text_column_produces_nothing(mini_conn, mini_paths, tmp_path):
    assert not [f for f in _run(mini_conn, mini_paths, tmp_path)
                if f.assertion.subject == "wo_history.STATUS"]


def test_no_dictionary_still_finds_encoding_problems(mini_conn):
    findings = FieldDetector().run(
        build_context(mini_conn, "wo_history", "2026-08-23"))
    subjects = {f.assertion.subject for f in findings}
    assert subjects == {"wo_history.DESCRIPTION"}


def test_every_assertion_carries_re_runnable_sql(mini_conn, mini_paths, tmp_path):
    for f in _run(mini_conn, mini_paths, tmp_path):
        assert verify(mini_conn, f.assertion.evidence[0]).status == "PASS"
