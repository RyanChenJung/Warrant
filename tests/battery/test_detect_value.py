from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.value import ValueDetector
from warrant.battery.gloss.dictionary import load_dictionary
from warrant.battery.gloss.evidence import verify
from warrant.battery.gloss.model import AssertionType


def _run(mini_conn, mini_paths, tmp_path, table="wo_history"):
    d = load_dictionary(mini_paths["dict"], "WORKORDER", tmp_path / "c")
    return ValueDetector().run(
        build_context(mini_conn, table, "2026-08-23", dictionary=d))


def _for(findings, subject):
    return [f for f in findings if f.assertion.subject == subject]


def test_enumerates_a_low_cardinality_column(mini_conn, mini_paths, tmp_path):
    got = _for(_run(mini_conn, mini_paths, tmp_path), "wo_history.WORKTYPE")
    enum = [f for f in got if "distinct values" in f.assertion.statement]
    assert len(enum) == 1
    s = enum[0].assertion.statement
    assert "CM" in s and "RCHK" in s and "9" in s   # value and its row count
    assert enum[0].assertion.type is AssertionType.VALUE


def test_asks_one_batched_question_for_the_whole_column(mini_conn, mini_paths,
                                                        tmp_path):
    got = _for(_run(mini_conn, mini_paths, tmp_path), "wo_history.WORKTYPE")
    questions = [f.question for f in got if f.question]
    assert len(questions) == 1              # not one per code
    assert "RCHK" in questions[0].text
    assert questions[0].proposed_answer     # P4


def test_proposes_a_gloss_measured_from_the_description_column(mini_conn, mini_paths,
                                                               tmp_path):
    # RCHK rows are described "ROUTE CHECK CHILLER" / "ROUTE CHECK BOILER". The modal
    # prefix is a measured proposal, not a model's guess.
    got = _for(_run(mini_conn, mini_paths, tmp_path), "wo_history.WORKTYPE")
    q = [f.question for f in got if f.question][0]
    assert "ROUTE CHECK" in q.proposed_answer


def test_flags_format_heterogeneity_at_any_cardinality(mini_conn, mini_paths,
                                                       tmp_path):
    got = _for(_run(mini_conn, mini_paths, tmp_path), "wo_history.LOCATION")
    shapes = [f for f in got if "format" in f.assertion.statement]
    assert len(shapes) == 1
    s = shapes[0].assertion.statement
    assert "GARAGE" in s or "SHOPS" in s
    assert shapes[0].question is not None


def test_prose_columns_are_excluded_from_format_analysis(mini_conn, mini_paths,
                                                         tmp_path):
    # "DESCRIPTION has many format classes" is not a finding, it is a
    # restatement of the fact that free text is free.
    got = _for(_run(mini_conn, mini_paths, tmp_path), "wo_history.DESCRIPTION")
    assert not [f for f in got if "format classes" in f.assertion.statement]


def test_finds_variant_families_in_a_free_text_column(mini_conn, mini_paths, tmp_path):
    got = _for(_run(mini_conn, mini_paths, tmp_path, table="assets"),
               "assets.description")
    fam = [f for f in got if "variant" in f.assertion.statement]
    assert len(fam) == 1
    assert "Pump" in fam[0].assertion.statement
    assert fam[0].question is not None


def test_every_assertion_carries_re_runnable_sql(mini_conn, mini_paths, tmp_path):
    for f in _run(mini_conn, mini_paths, tmp_path):
        assert verify(mini_conn, f.assertion.evidence[0]).status == "PASS"
