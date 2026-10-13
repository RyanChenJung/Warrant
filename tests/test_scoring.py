"""The shared scorer (#40).

The write-line tests go through the write-line entry point with the scripted fake agent, on
`fixtures/write_line_scoring.yaml`, which has one question per kind of expected response. The
maintenance line's entry point (#42) does not exist yet, so its rules (stale value, silent error)
are tested on the scorer itself until #42 can run them end to end.
"""

import dataclasses
import json

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import AgentOutput, Response, ResponseKind, Usage
from warrant.data.sqlite import query_with_columns
from warrant.scoring.classify import Result, is_silent_error, is_stale_value, score
from warrant.store.results import Provenance
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


def with_question(config, question_id, **fields):
    """The configuration with some fields of one question changed."""
    return dataclasses.replace(
        config,
        questions=tuple(dataclasses.replace(q, **fields) if q.id == question_id else q for q in config.questions),
    )


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


@pytest.mark.parametrize(
    "term, missing",
    [
        ("rate", "I cannot generate an accurate figure from this data."),
        ("date", "The database cannot be updated by me."),
    ],
)
def test_a_recorded_term_inside_another_word_does_not_name_the_missing_piece(config, tmp_path, term, missing):
    # A term still counts where a word starts: "open work orders" names "open work order" (RIGHT).
    agent = answering({"open-order-cost": refusal(missing, "The task hours logged on open work orders.")})
    result = run(with_question(config, "open-order-cost", missing_terms=(term,)), agent, tmp_path / "work")
    assert scored(result, "open-order-cost") == ("wrong_answer", "inadequate_refusal")


def test_the_refusal_check_the_run_is_given_decides_which_refusals_are_correct(config, tmp_path):
    result = run(config, answering(), tmp_path / "work", refusal_check=lambda response, terms: False)
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


# A control question whose gold answer is zero up to floating-point noise: the net of a ledger
# whose debits and credits cancel out.
LEDGER = "(VALUES (0.1, 0), (0.2, 0), (0, 0.3))"
NET_BALANCE = Question(
    id="net-balance",
    database="workorders",
    text="What is the net balance of the ledger?",
    gold_sql=f"SELECT SUM(column1 - column2) FROM {LEDGER}",
    defect=None,
)


@pytest.mark.parametrize(
    "sql",
    [f"SELECT SUM(column1) - SUM(column2) FROM {LEDGER}", "SELECT 0"],
    ids=["another-formulation", "exactly-zero"],
)
def test_an_answer_off_by_floating_point_noise_around_zero_is_correct(config, tmp_path, sql):
    config = dataclasses.replace(config, questions=config.questions + (NET_BALANCE,))
    result = run(config, answering({"net-balance": answer(sql)}), tmp_path / "work")

    assert result.gold["net-balance"].rows != [(0,)]  # the noise is there
    assert scored(result, "net-balance") == ("correct_answer", None)


def test_a_gold_answer_of_zero_up_to_floating_point_noise_gives_a_sign_or_zero_mismatch(config, tmp_path):
    config = dataclasses.replace(config, questions=config.questions + (NET_BALANCE,))
    result = run(config, answering({"net-balance": answer("SELECT 0.3")}), tmp_path / "work")
    assert scored(result, "net-balance") == ("wrong_answer", "sign_or_zero_mismatch")


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
        "SELECT DISTINCT wonum AS work_order FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)",
    ],
    ids=["another-row-order", "a-row-per-task", "an-extra-column", "an-aliased-key-column"],
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


class FailingAgent:
    """Right in every run, except that under the empty store every call on one question fails, and
    two of the three on another."""

    def answer(self, request, tools):
        if not request.store.claims and (
            request.question_id == "costly-closed-orders"
            or (request.question_id == "open-order-hours" and request.run < 2)
        ):
            return AgentOutput(None, Usage(), failure="malformed output after 2 attempts")
        return AgentOutput(RIGHT[request.question_id], Usage())


def test_a_question_with_fewer_than_two_scored_runs_under_a_rule_has_no_flip_to_report(config, tmp_path):
    result = run(dataclasses.replace(config, runs=3), FailingAgent(), tmp_path / "work")

    unmeasured = {("costly-closed-orders", "empty"), ("open-order-hours", "empty")}
    assert result.flips == {(q, rule): None if (q, rule) in unmeasured else False for q in QUESTIONS for rule in RULES}


# Stored results

PROVENANCE = Provenance(
    config_hash="0" * 64,
    repo_commit="abc1234",
    model="anthropic.claude-model-placeholder",
    prompt_version="1",
)


def test_every_stored_result_carries_its_response_class_and_bucket(config, tmp_path):
    results = tmp_path / "results.jsonl"
    run(config, answering({"open-order-hours": answer("SELECT 16.25 * 1.5")}), tmp_path / "work", PROVENANCE, results)

    records = [json.loads(line) for line in results.read_text().splitlines()]
    stored = {(r["question_id"], r["rule"]): (r["response_class"], r["bucket"]) for r in records}
    assert stored[("open-order-hours", "empty")] == ("wrong_answer", "within_factor_2")
    assert stored[("open-order-numbers", "empty")] == ("correct_answer", None)


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


@pytest.mark.parametrize(
    "question_id, field, value",
    [
        ("open-order-cost", "missing_terms", "open work order"),
        ("open-order-cost", "missing_terms", ["open work order", ""]),
        ("open-order-numbers", "key", "wonum"),
    ],
    ids=["terms-not-a-list", "a-blank-term", "key-not-a-list"],
)
def test_missing_piece_terms_and_key_columns_are_lists_of_names(scoring_config, question_id, field, value):
    raw = yaml.safe_load(scoring_config.read_text())
    (question,) = [q for q in raw["questions"] if q["id"] == question_id]
    question[field] = value
    scoring_config.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValueError, match=question_id):
        load_config(scoring_config)


@pytest.mark.parametrize("key", [(), ("work_order",)], ids=["no-key", "a-column-the-gold-result-lacks"])
def test_a_set_question_without_a_key_its_gold_result_has_is_rejected_before_any_agent_call(config, tmp_path, key):
    agent = answering()

    with pytest.raises(ValueError, match="open-order-numbers"):
        run(with_question(config, "open-order-numbers", key=key), agent, tmp_path / "work")
    assert agent.requests == []


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
    post_drift = result_of(workorders_db, POST_DRIFT_GOLD)
    after_drift = score(answer(STALE_SQL), executed, post_drift)

    assert is_stale_value(executed, result_of(workorders_db, PRE_DRIFT_GOLD), post_drift)
    assert is_silent_error(after_drift, executed, escalations=0)


def test_the_same_stale_answer_in_a_run_with_an_escalation_is_not_a_silent_error(workorders_db):
    executed = result_of(workorders_db, STALE_SQL)
    post_drift = result_of(workorders_db, POST_DRIFT_GOLD)
    after_drift = score(answer(STALE_SQL), executed, post_drift)

    assert is_stale_value(executed, result_of(workorders_db, PRE_DRIFT_GOLD), post_drift)
    assert not is_silent_error(after_drift, executed, escalations=1)


def test_the_right_post_drift_answer_is_not_a_stale_value(workorders_db):
    executed = post_drift = result_of(workorders_db, POST_DRIFT_GOLD)
    assert not is_stale_value(executed, result_of(workorders_db, PRE_DRIFT_GOLD), post_drift)


def test_the_right_post_drift_answer_is_not_a_stale_value_even_when_the_drift_is_within_the_tolerance(
    workorders_db,
):
    # The smallest cost counted goes from 60 to 70, which drops one order of 64.25 out of a total
    # of 5,440.50: the gold results differ, so the task is valid, but by 1.2 percent.
    pre_drift = result_of(workorders_db, "SELECT SUM(total_cost) FROM workorders WHERE total_cost > 60")
    post_drift_sql = "SELECT SUM(total_cost) FROM workorders WHERE total_cost > 70"
    executed = post_drift = result_of(workorders_db, post_drift_sql)

    assert pre_drift.rows != post_drift.rows
    assert score(answer(post_drift_sql), executed, post_drift).response_class == "correct_answer"
    assert not is_stale_value(executed, pre_drift, post_drift)


# Without a key, as the maintenance line compares them, results match as sets of rows within the
# tolerance.


def table(rows):
    return Result(tuple(f"c{i}" for i in range(len(rows[0]))), rows)


@pytest.mark.parametrize(
    "executed_rows, gold_rows",
    [
        ([(116,), (117,), (111,)], [(111,), (116,), (117,)]),
        ([(86.0,), (90.0,)], [(90.0,), (91.0,)]),  # 86 pairs with 90, and 90 with 91
        ([("NORTH", 103.0), ("NORTH", 97.0)], [("NORTH", 100.0), ("NORTH", 106.0)]),
    ],
    ids=["the-same-rows-in-another-order", "a-pairing-a-greedy-match-misses", "a-repeated-label"],
)
def test_rows_compared_without_a_key_match_when_they_pair_off_one_to_one_within_the_tolerance(
    executed_rows, gold_rows
):
    # Each gold value lies within 5 percent of another, so a row could pair with the wrong twin.
    executed, gold = table(executed_rows), table(gold_rows)
    unrelated = table([("a result the answer does not match",)])

    assert score(answer("SELECT ..."), executed, gold).response_class == "correct_answer"
    assert is_stale_value(executed, gold, unrelated)


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
