"""The wallet-sum per-question review (#54): each wallet-sum answer is classed by whether the SQL
that produces it reads walletsum, or reaches the answer by summing the balance columns instead. The
balance columns come from the freeze, the questions from the run's configuration. No model is
called and no database is touched."""

from pathlib import Path

import pytest
import yaml

from warrant.write_line.wallet_sum_review import (
    balance_columns,
    classify,
    answer_column_equals_gold,
    normalize_sql,
    read_overrides,
    review,
    review_list,
    summary_rows,
    wallet_sum_questions,
)
from warrant.write_line.config import load_config

REPO = Path(__file__).resolve().parents[1]
FREEZE = REPO / "freeze" / "write_line.yaml"
CONFIG = REPO / "configs" / "write_line_thin.yaml"


@pytest.fixture(scope="module")
def balance():
    return balance_columns(yaml.safe_load(FREEZE.read_text()))


def test_the_balance_columns_are_walletsum_and_the_components_the_freeze_readings_name(balance):
    assert balance.target == "walletsum"
    assert balance.components == frozenset({"availsum", "frozensum", "margsum", "unrealline"})


def test_the_wallet_sum_questions_are_read_from_the_configuration():
    ids = [q.id for q in wallet_sum_questions(load_config(CONFIG))]
    assert len(ids) == 6
    assert "total-held" in ids and "user-wallet-excluding-unrealised" in ids


@pytest.mark.parametrize("sql, category", [
    ("SELECT SUM(walletsum) FROM accountbalances", "reads_walletsum"),
    ("SELECT walletsum - margsum FROM accountbalances WHERE TRIM(usertag) = 'U810391'", "reads_walletsum"),
    ("SELECT availsum + frozensum AS x FROM accountbalances WHERE usertag = 'U810391'", "components_only"),
    # walletsum is only listed beside the answer, not used in it
    ("SELECT ab.availsum, ab.frozensum, ab.margsum, ab.walletsum, ab.availsum + ab.frozensum AS x "
     "FROM accountbalances ab", "components_only"),
    ("SELECT COUNT(*) FROM accountbalances WHERE margsum > 0.5 * walletsum", "reads_walletsum"),
    ("SELECT COUNT(*) FROM accountbalances WHERE margsum > 0.5 * (availsum + frozensum + margsum)",
     "components_only"),
    ("SELECT SUM(x) FROM (SELECT walletsum - margsum AS x FROM accountbalances)", "reads_walletsum"),
    ("SELECT SUM(x) FROM (SELECT availsum + frozensum AS x FROM accountbalances)", "components_only"),
    ("", "no_sql"),
])
def test_an_answer_is_classed_by_the_balance_columns_that_decide_it(balance, sql, category):
    assert classify(sql, balance).category == category


def test_an_alias_is_followed_through_a_cte(balance):
    sql = ("WITH t AS (SELECT availsum + frozensum + margsum AS total FROM accountbalances) "
           "SELECT SUM(total) FROM t")
    c = classify(sql, balance)
    assert c.category == "components_only"
    assert c.deciding_columns == ("availsum", "frozensum", "margsum")


def test_a_cte_column_named_walletsum_but_defined_from_the_components_is_components_only(balance):
    sql = ("WITH t AS (SELECT availsum + frozensum + margsum AS walletsum FROM accountbalances) "
           "SELECT SUM(walletsum) FROM t")
    assert classify(sql, balance).category == "components_only"


def test_an_alias_defined_more_than_once_is_noted_for_the_manual_check(balance):
    sql = ("WITH a AS (SELECT walletsum AS x FROM accountbalances), "
           "b AS (SELECT availsum AS x FROM accountbalances) "
           "SELECT (SELECT SUM(x) FROM a) - (SELECT SUM(x) FROM b)")
    assert "alias defined more than once: x" in classify(sql, balance).note
    assert classify("SELECT SUM(walletsum) AS x FROM accountbalances", balance).note == ""


def test_a_balance_column_in_a_join_condition_decides_the_answer(balance):
    sql = ("SELECT COUNT(*) FROM accountbalances a JOIN accountbalances b "
           "ON a.usertag = b.usertag AND a.walletsum > b.margsum")
    assert classify(sql, balance).category == "reads_walletsum"


def test_a_predicate_with_no_balance_column_adds_nothing(balance):
    c = classify("SELECT COUNT(*) FROM accountbalances WHERE usertag = 'U810391'", balance)
    assert c.category == "unclear"


def test_sql_that_does_not_parse_is_unclear(balance):
    assert classify("SELEKT walletsum FROM", balance).category == "unclear"


def test_several_projections_with_no_single_answer_expression_are_unclear(balance):
    assert classify("SELECT walletsum - margsum, availsum + frozensum FROM accountbalances",
                    balance).category == "unclear"
    assert classify("SELECT availsum, walletsum FROM accountbalances", balance).category == "unclear"


def test_a_missing_final_sql_is_no_sql(balance):
    assert classify(None, balance).category == "no_sql"


def test_normalized_sql_ignores_layout():
    assert normalize_sql("SELECT  SUM(walletsum)\n FROM accountbalances") == \
        normalize_sql("select sum(walletsum) from accountbalances")


def _check(sql, executed, gold=100.5, balance=None):
    return answer_column_equals_gold({"executed": executed}, classify(sql, balance), gold, tolerance=0.01)


def test_the_answer_column_is_compared_with_the_gold_value(balance):
    sql = "SELECT walletsum, margsum, walletsum - margsum AS x FROM accountbalances WHERE usertag = 'U1'"
    # the gold value is in a listed column, not in the answer column
    assert _check(sql, [[100.0, 7.0, 93.0]], balance=balance) is False
    assert _check(sql, [[107.0, 7.0, 100.0]], balance=balance) is True
    assert _check("SELECT SUM(walletsum) FROM accountbalances", [[100.0]], balance=balance) is True
    assert _check("SELECT SUM(walletsum) FROM accountbalances", [], balance=balance) is False
    # the star of COUNT(*) is not a star projection
    assert _check("SELECT COUNT(*) FROM accountbalances WHERE margsum > 0.5 * walletsum", [[100]],
                  gold=100, balance=balance) is True


def test_the_answer_column_is_undetermined_without_a_single_answer_expression(balance):
    assert _check("SELECT SUM(walletsum) AS a, SUM(margsum) AS b FROM accountbalances", [[100.0, 1.0]],
                  balance=balance) == "undetermined"
    assert _check(None, [], balance=balance) == "undetermined"
    assert _check("SELECT * FROM accountbalances", [[100.0, 1.0]], balance=balance) == "undetermined"


def _answer(question, rule, run, sql, response_class="correct_answer", executed=((1.0,),)):
    return {"record": "answer", "question_id": question, "rule": rule, "run": run, "final_sql": sql,
            "response_class": response_class, "executed": [list(r) for r in executed]}


def test_a_manual_override_replaces_the_category_of_every_answer_with_that_sql(balance, tmp_path):
    overrides = tmp_path / "manual_overrides.csv"
    overrides.write_text("normalized_sql,category,reason\n"
                         "select sum(walletsum) from accountbalances,unclear,checked by hand\n")
    records = [_answer("total-held", "empty", 0, "SELECT SUM(walletsum) FROM accountbalances"),
               _answer("total-held", "empty", 1, "SELECT  SUM(walletsum) FROM accountbalances")]
    rows = review(records, {"total-held"}, {}, balance, read_overrides(overrides), tolerance=0.01)
    assert [r["category"] for r in rows] == ["unclear", "unclear"]
    assert rows[0]["note"] == "override: checked by hand"


def test_only_wallet_sum_answers_are_reviewed(balance):
    records = [_answer("total-held", "empty", 0, "SELECT SUM(walletsum) FROM accountbalances"),
               _answer("orders-placed", "empty", 0, "SELECT COUNT(*) FROM orders"),
               {"record": "store", "rule": "empty"}]
    rows = review(records, {"total-held"}, {}, balance, {}, tolerance=0.01)
    assert [r["question"] for r in rows] == ["total-held"]


def test_the_summary_counts_correct_wrong_and_other_per_question_and_category(balance):
    records = [_answer("total-held", "empty", 0, "SELECT SUM(walletsum) FROM accountbalances"),
               _answer("total-held", "settlement", 0, "SELECT SUM(availsum + frozensum + margsum) FROM accountbalances"),
               _answer("total-held", "settlement", 1, "SELECT SUM(walletsum) FROM accountbalances", "wrong_answer"),
               _answer("total-held", "empty", 1, None, "failed")]
    rows = summary_rows(review(records, {"total-held"}, {"total-held": 1.0}, balance, {}, tolerance=0.01))
    answer_column = {r["category"]: r for r in rows if r["view"] == "question_answer_column"}
    assert (answer_column["true"]["correct"], answer_column["true"]["wrong"]) == (2, 1)
    assert answer_column["undetermined"]["other"] == 1
    by_category = {r["category"]: r for r in rows if r["view"] == "question_category"}
    assert (by_category["reads_walletsum"]["correct"], by_category["reads_walletsum"]["wrong"]) == (1, 1)
    assert by_category["components_only"]["correct"] == 1
    assert by_category["no_sql"]["other"] == 1
    settlement = [r for r in rows if r["view"] == "question_rule" and r["rule"] == "settlement"]
    assert {(r["category"], r["correct"], r["wrong"]) for r in settlement} == \
        {("reads_walletsum", 0, 1), ("components_only", 1, 0)}


def test_the_review_list_holds_each_distinct_sql_once_sorted_unclear_then_components_then_walletsum(balance):
    records = [_answer("total-held", "empty", 0, "SELECT SUM(walletsum) FROM accountbalances"),
               _answer("total-held", "empty", 1, "select sum(walletsum) from accountbalances"),
               _answer("total-held", "empty", 2, "SELECT SUM(availsum + frozensum + margsum) FROM accountbalances"),
               _answer("total-held", "all_agent", 0, "SELECT COUNT(*) FROM accountbalances"),
               _answer("total-held", "all_agent", 1, None, "failed")]
    entries = review_list(review(records, {"total-held"}, {}, balance, {}, tolerance=0.01))
    assert [(e["category"], e["count"]) for e in entries] == \
        [("unclear", 1), ("components_only", 1), ("reads_walletsum", 2)]
    assert (entries[2]["example_rule"], entries[2]["example_run"]) == ("empty", 0)
