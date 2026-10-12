"""The shared scorer (#40).

The write-line tests go through the write-line entry point with the scripted fake agent, on
`fixtures/write_line_scoring.yaml`, which has one question per kind of expected response. The
maintenance line's entry point (#42) does not exist yet, so its rules (stale value, silent error)
are tested on the scorer itself until #42 can run them end to end.
"""

import dataclasses

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import AgentOutput, Response, ResponseKind, Usage
from warrant.data.sqlite import query_with_columns
from warrant.scoring.classify import Result, is_silent_error, is_stale_value, score
from warrant.write_line.config import Question, load_config
from warrant.write_line.run import run

QUESTIONS = ("open-order-hours", "open-order-numbers", "open-order-cost", "costly-closed-orders")
RULES = ("empty", "all_person")

OPEN_ORDER_NUMBERS = "SELECT DISTINCT wonum FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)"


def answer(sql):
    return Response(ResponseKind.ANSWER, final_sql=sql)


def refusal(missing, alternative):
    return Response(ResponseKind.REFUSAL, missing=missing, alternative=alternative)


CLARIFICATION = Response(ResponseKind.CLARIFICATION, clarification="Open as of which date?")

# The right response to every question of the fixture.
RIGHT = {
    "open-order-hours": answer("SELECT SUM(hours) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)"),
    "open-order-numbers": answer(OPEN_ORDER_NUMBERS),
    "open-order-cost": refusal(
        missing="The export holds no open work orders, so their cost is not recorded anywhere.",
        alternative="The task hours logged on open work orders.",
    ),
    "costly-closed-orders": answer("SELECT COUNT(*) FROM workorders WHERE status = 'CLOSED' AND total_cost > 2000"),
}


def answering(overrides=None):
    """A fake agent that gives the right response to every question but the ones overridden."""
    responses = {**RIGHT, **(overrides or {})}
    return ScriptedAgent(lambda request, tools: responses[request.question_id])


def scored(result, question_id, rule="empty"):
    """The response class and bucket of a question's one run under a rule."""
    (row,) = [r for r in result.rows if r.question_id == question_id and r.rule == rule]
    return row.response_class, row.bucket


@pytest.fixture
def config(scoring_config):
    return load_config(scoring_config)


# Response classes and accuracy


def test_correct_answers_and_correct_refusals_are_both_accurate(config, tmp_path):
    result = run(config, answering(), tmp_path / "work")

    assert {q: scored(result, q) for q in QUESTIONS} == {
        "open-order-hours": ("correct_answer", None),
        "open-order-numbers": ("correct_answer", None),
        "open-order-cost": ("correct_refusal", None),
        "costly-closed-orders": ("correct_answer", None),
    }
    assert result.accuracy == {"empty": 1.0, "all_person": 1.0}


@pytest.mark.parametrize(
    "missing, alternative",
    [
        ("", ""),  # a bare refusal
        ("I cannot answer that from this database.", "The task hours logged on open work orders."),
        ("Open work orders are not in the export.", ""),
    ],
    ids=["bare", "names-no-recorded-term", "offers-no-alternative"],
)
def test_a_refusal_without_a_recorded_missing_piece_term_and_an_alternative_is_an_inadequate_refusal(
    config, tmp_path, missing, alternative
):
    result = run(config, answering({"open-order-cost": refusal(missing, alternative)}), tmp_path / "work")
    assert scored(result, "open-order-cost") == ("wrong_answer", "inadequate_refusal")


def test_answering_a_question_the_data_cannot_answer_is_a_wrong_answer(config, tmp_path):
    agent = answering({"open-order-cost": answer("SELECT SUM(total_cost) FROM workorders WHERE status = 'OPEN'")})
    result = run(config, agent, tmp_path / "work")
    assert scored(result, "open-order-cost") == ("wrong_answer", "answered_unanswerable")


def test_refusing_a_question_the_data_can_answer_is_an_over_refusal(config, tmp_path):
    # It would pass the refusal check, but the data can answer this question.
    agent = answering({"open-order-hours": refusal("Open work orders are not in the export.", "Closed work orders.")})
    result = run(config, agent, tmp_path / "work")
    assert scored(result, "open-order-hours") == ("over_refusal", None)


class MixedAgent:
    """Right under the person's store. Under the empty store: a wrong answer, a clarification
    request, a correct refusal and a failed call."""

    def answer(self, request, tools):
        if request.store.claims:
            return AgentOutput(RIGHT[request.question_id], Usage())
        if request.question_id == "costly-closed-orders":
            return AgentOutput(None, Usage(), failure="malformed output after 2 attempts")
        empty_store = {"open-order-hours": answer("SELECT 16.25 * 3"), "open-order-numbers": CLARIFICATION}
        return AgentOutput(empty_store.get(request.question_id, RIGHT[request.question_id]), Usage())


def test_accuracy_leaves_out_clarification_requests_and_failures_and_counts_them_per_rule(config, tmp_path):
    result = run(config, MixedAgent(), tmp_path / "work")

    # Empty store: the correct refusal out of the wrong answer and itself.
    assert result.accuracy == {"empty": 0.5, "all_person": 1.0}
    assert result.counts == {
        "empty": {"wrong_answer": 1, "clarification_request": 1, "correct_refusal": 1, "failed": 1},
        "all_person": {"correct_answer": 3, "correct_refusal": 1},
    }


# Numeric answers. The gold answer to open-order-hours is 16.25.


@pytest.mark.parametrize(
    "sql, bucket",
    [
        ("SELECT 16.25 * 1.5", "within_factor_2"),
        ("SELECT 16.25 / 1.9", "within_factor_2"),
        ("SELECT 16.25 * 2.5", "beyond_factor_2"),
        ("SELECT 16.25 / 3", "beyond_factor_2"),
        ("SELECT -16.25", "sign_or_zero_mismatch"),
        ("SELECT 0", "sign_or_zero_mismatch"),
    ],
)
def test_a_wrong_numeric_answer_lands_in_its_size_bucket(config, tmp_path, sql, bucket):
    result = run(config, answering({"open-order-hours": answer(sql)}), tmp_path / "work")
    assert scored(result, "open-order-hours") == ("wrong_answer", bucket)


def test_a_numeric_answer_within_the_tolerance_is_correct_and_outside_a_tighter_one_is_within_5_percent(
    config, tmp_path
):
    three_percent_off = answering({"open-order-hours": answer("SELECT 16.25 * 1.03")})

    default = run(config, three_percent_off, tmp_path / "default")
    tighter = run(config, three_percent_off, tmp_path / "tighter", tolerance=0.01)

    assert scored(default, "open-order-hours") == ("correct_answer", None)
    assert scored(tighter, "open-order-hours") == ("wrong_answer", "within_5_percent")


def test_a_gold_answer_of_zero_gives_a_sign_or_zero_mismatch(config, tmp_path):
    sql = "SELECT COUNT(*) FROM workorders WHERE status = 'CLOSED' AND total_cost > 200"
    result = run(config, answering({"costly-closed-orders": answer(sql)}), tmp_path / "work")

    assert result.gold["costly-closed-orders"].rows == [(0,)]
    assert scored(result, "costly-closed-orders") == ("wrong_answer", "sign_or_zero_mismatch")


# Set answers


@pytest.mark.parametrize(
    "sql",
    [
        OPEN_ORDER_NUMBERS + " ORDER BY wonum DESC",
        "SELECT wonum FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)",
        (
            "SELECT t.wonum, SUM(t.hours) FROM tasks t LEFT JOIN workorders w USING (wonum) "
            "WHERE w.wonum IS NULL GROUP BY t.wonum"
        ),
    ],
    ids=["another-row-order", "a-row-per-task", "an-extra-column"],
)
def test_a_set_answer_is_compared_as_a_set_of_its_key_values(config, tmp_path, sql):
    result = run(config, answering({"open-order-numbers": answer(sql)}), tmp_path / "work")
    assert scored(result, "open-order-numbers") == ("correct_answer", None)


def test_a_set_answer_missing_a_key_value_is_wrong(config, tmp_path):
    sql = "SELECT DISTINCT wonum FROM tasks WHERE wonum IN ('WO-1002', 'WO-1005', 'WO-1008')"
    result = run(config, answering({"open-order-numbers": answer(sql)}), tmp_path / "work")
    assert scored(result, "open-order-numbers") == ("wrong_answer", None)


# Flip rate


class UnsteadyAgent:
    """Right in every run, except a wrong answer to one question in one run under the empty store,
    and a failed call on another question under the person's store."""

    def answer(self, request, tools):
        if (request.question_id, request.run, bool(request.store.claims)) == ("open-order-hours", 1, False):
            return AgentOutput(answer("SELECT 16.25 * 3"), Usage())
        if (request.question_id, request.run, bool(request.store.claims)) == ("open-order-numbers", 2, True):
            return AgentOutput(None, Usage(), failure="malformed output after 2 attempts")
        return AgentOutput(RIGHT[request.question_id], Usage())


def test_a_question_flips_under_a_rule_when_its_scored_runs_do_not_share_one_response_class(config, tmp_path):
    result = run(dataclasses.replace(config, runs=3), UnsteadyAgent(), tmp_path / "work")

    # The failed call is not a scored run, so it does not make its question flip.
    assert result.flips == {
        (q, rule): (q, rule) == ("open-order-hours", "empty") for q in QUESTIONS for rule in RULES
    }


# Validation before any agent call


def test_a_control_question_whose_gold_answer_differs_on_the_injected_copy_is_rejected_before_any_agent_call(
    config, tmp_path
):
    touched = Question(
        id="all-orders",
        database="workorders",
        text="How many work orders are there?",
        gold_sql="SELECT COUNT(*) FROM workorders",
        defect=None,
    )
    agent = answering()

    with pytest.raises(ValueError, match="all-orders"):
        run(dataclasses.replace(config, questions=config.questions + (touched,)), agent, tmp_path / "work")
    assert agent.requests == []


@pytest.mark.parametrize(
    "fields",
    [{"gold_sql": "SELECT 1", "missing_terms": ["open work order"]}, {}],
    ids=["both", "neither"],
)
def test_a_question_has_either_a_gold_sql_or_missing_piece_terms(scoring_config, fields):
    raw = yaml.safe_load(scoring_config.read_text())
    question = {k: v for k, v in raw["questions"][2].items() if k not in ("gold_sql", "missing_terms")}
    raw["questions"][2] = {**question, **fields}
    scoring_config.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValueError, match="open-order-cost"):
        load_config(scoring_config)


# The maintenance line's rules, on the scorer until the maintenance run (#42) exists.
#
# A constant-change drift task on the work-order fixture: large work orders cost more than 500
# before drift and more than 800 after it. The drift is a convention drift, so the database stays
# the same and only the gold result changes.

PRE_DRIFT_GOLD = "SELECT site, SUM(total_cost) FROM workorders WHERE total_cost > 500 GROUP BY site"
POST_DRIFT_GOLD = "SELECT site, SUM(total_cost) FROM workorders WHERE total_cost > 800 GROUP BY site"
# The old threshold, in another row order and with another column name.
STALE_SQL = (
    "SELECT site, SUM(total_cost) AS spend FROM workorders WHERE total_cost > 500 GROUP BY site ORDER BY site DESC"
)


def result_of(db, sql):
    return Result(*query_with_columns(db, sql))


def test_an_answer_is_scored_against_the_gold_result_of_its_task_state(workorders_db):
    executed = result_of(workorders_db, STALE_SQL)
    before_drift = score(answer(STALE_SQL), executed, result_of(workorders_db, PRE_DRIFT_GOLD))
    after_drift = score(answer(STALE_SQL), executed, result_of(workorders_db, POST_DRIFT_GOLD))

    assert before_drift.response_class == "correct_answer"
    assert after_drift.response_class == "wrong_answer"


def test_a_post_drift_answer_matching_the_pre_drift_gold_result_is_a_stale_value_and_a_silent_error(workorders_db):
    executed = result_of(workorders_db, STALE_SQL)
    after_drift = score(answer(STALE_SQL), executed, result_of(workorders_db, POST_DRIFT_GOLD))

    assert is_stale_value(executed, result_of(workorders_db, PRE_DRIFT_GOLD))
    assert is_silent_error(after_drift, executed, escalations=0)


def test_the_same_stale_answer_in_a_run_with_an_escalation_is_not_a_silent_error(workorders_db):
    executed = result_of(workorders_db, STALE_SQL)
    after_drift = score(answer(STALE_SQL), executed, result_of(workorders_db, POST_DRIFT_GOLD))

    assert is_stale_value(executed, result_of(workorders_db, PRE_DRIFT_GOLD))
    assert not is_silent_error(after_drift, executed, escalations=1)


def test_the_right_post_drift_answer_is_not_a_stale_value(workorders_db):
    executed = result_of(workorders_db, POST_DRIFT_GOLD)
    assert not is_stale_value(executed, result_of(workorders_db, PRE_DRIFT_GOLD))


@pytest.mark.parametrize(
    "response, refusal_expected",
    [
        (refusal("", ""), True),  # an inadequate refusal is a wrong answer, but still a refusal
        (answer("SELECT no_such_column FROM workorders"), False),  # its final SQL failed with an error
    ],
    ids=["inadequate-refusal", "failing-sql"],
)
def test_a_wrong_answer_given_with_a_refusal_or_an_error_is_not_a_silent_error(
    workorders_db, response, refusal_expected
):
    executed = None  # a refusal has no result, and neither has SQL that failed to run
    gold = None if refusal_expected else result_of(workorders_db, POST_DRIFT_GOLD)
    scored_run = score(response, executed, gold, missing_terms=("threshold",))

    assert scored_run.response_class == "wrong_answer"
    assert not is_silent_error(scored_run, executed, escalations=0)
