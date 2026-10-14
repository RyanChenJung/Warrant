from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.dictionary import load_dictionary
from warrant.battery.gloss.evidence import verify
from warrant.battery.gloss.model import AssertionType, Tier
from warrant.battery.gloss.probe import OrdinalDirectionProbe, probe_ordinal_direction


def _ctx(mini_conn, mini_paths, tmp_path):
    d = load_dictionary(mini_paths["dict"], "WORKORDER", tmp_path / "c")
    ctx = build_context(mini_conn, "wo_history", "2026-08-23", dictionary=d)
    ctx.grain_filter = "(\"PARENT\" IS NULL OR \"PARENT\" = '')"
    return ctx


def test_documented_direction_is_parsed_from_remarks(mini_paths, tmp_path):
    d = load_dictionary(mini_paths["dict"], "WORKORDER", tmp_path / "c")
    # "from 0-100, where 0 is the lowest priority and 100 is the highest"
    assert d.get("WOPRIORITY").documented_direction() == "higher_is_more"
    assert d.get("STATUS").documented_direction() is None


def test_probe_finds_the_direction_from_behaviour(mini_conn, mini_paths, tmp_path):
    f = probe_ordinal_direction(_ctx(mini_conn, mini_paths, tmp_path), "WOPRIORITY")
    assert f is not None
    assert "lower" in f.assertion.statement.lower()
    assert f.assertion.type is AssertionType.FIELD
    assert f.assertion.tier is Tier.MEASURED


def test_the_statement_reports_effect_size_and_sample_size(mini_conn, mini_paths,
                                                           tmp_path):
    s = probe_ordinal_direction(_ctx(mini_conn, mini_paths, tmp_path),
                                "WOPRIORITY").assertion.statement
    assert "x" in s              # effect size, e.g. "30x"
    assert "n=" in s             # sample size
    assert "ACTSTART" in s       # names the observable correlate it used


def test_the_probe_flags_the_contradiction_with_documentation(mini_conn, mini_paths,
                                                             tmp_path):
    f = probe_ordinal_direction(_ctx(mini_conn, mini_paths, tmp_path), "WOPRIORITY")
    assert "contradicts" in f.assertion.statement
    # Resolved by measurement, so there is nothing to ask a human.
    assert f.question is None


def test_no_probe_result_for_a_column_with_no_behavioural_signal(mini_conn,
                                                                mini_paths, tmp_path):
    assert probe_ordinal_direction(
        _ctx(mini_conn, mini_paths, tmp_path), "PCACTHRS") is None


def test_probe_works_as_a_detector(mini_conn, mini_paths, tmp_path):
    findings = OrdinalDirectionProbe().run(_ctx(mini_conn, mini_paths, tmp_path))
    assert [f.assertion.subject for f in findings] == ["wo_history.WOPRIORITY"]


def test_every_assertion_carries_re_runnable_sql(mini_conn, mini_paths, tmp_path):
    for f in OrdinalDirectionProbe().run(_ctx(mini_conn, mini_paths, tmp_path)):
        assert verify(mini_conn, f.assertion.evidence[0]).status == "PASS"
