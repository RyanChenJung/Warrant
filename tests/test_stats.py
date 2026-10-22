"""Statistics shared by both lines (#41), computed from stored results with no model call.

The summaries that will call these, the write line's (#53) and the maintenance line's (#48), do not
exist yet, so the statistics are tested on fixture results: records the write-line entry point
stored for a fixture run, or hand-built records shaped like the stored ones.
"""

import dataclasses
import json
from fractions import Fraction

import pytest

from warrant.agent.interface import AgentOutput, Response, ResponseKind, Usage
from warrant.scoring.classify import ResponseClass
from warrant.scoring.stats import (
    ERRORS,
    SignFlip,
    bootstrap_interval,
    flip_rate,
    frontier,
    mcnemar,
    paired_difference,
    plot_frontier,
    question_differences,
    questions_per_100_tasks,
    sign_flip_test,
    silent_error_rate,
    write_line_test,
)
from warrant.store.results import Provenance, append
from warrant.write_line.config import load_config
from warrant.write_line.run import run

PROVENANCE = Provenance(
    config_hash="0" * 64,
    repo_commit="abc1234",
    model="anthropic.claude-model-placeholder",
    prompt_version="1",
)


def answer(sql):
    return Response(ResponseKind.ANSWER, final_sql=sql)


CLARIFICATION = Response(ResponseKind.CLARIFICATION, clarification="Open as of which date?")
WRONG_HOURS = answer("SELECT 16.25 * 3")

# The right response to every question of fixtures/write_line_scoring.yaml.
RIGHT = {
    "open-order-hours": answer("SELECT SUM(hours) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)"),
    "open-order-numbers": answer("SELECT DISTINCT wonum FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)"),
    "open-order-cost": Response(
        ResponseKind.REFUSAL,
        missing="The export holds no open work orders, so their cost is not recorded anywhere.",
        alternative="The task hours logged on open work orders.",
    ),
    "costly-closed-orders": answer("SELECT COUNT(*) FROM workorders WHERE status = 'CLOSED' AND total_cost > 2000"),
}

FAILED = "failed"

# Three runs per question. Under the person's store: right, except a clarification request to
# open-order-numbers in run 0. Under the empty store: as below.
EMPTY_STORE = {
    ("open-order-hours", 0): WRONG_HOURS,
    ("open-order-hours", 1): FAILED,
    ("open-order-numbers", 0): WRONG_HOURS,
    ("open-order-numbers", 1): WRONG_HOURS,
    ("open-order-numbers", 2): WRONG_HOURS,
    ("open-order-cost", 0): CLARIFICATION,
    ("open-order-cost", 1): CLARIFICATION,
    ("open-order-cost", 2): CLARIFICATION,
}


class ThreeRunAgent:
    def answer(self, request, tools):
        if request.store.claims:
            person_store = {("open-order-numbers", 0): CLARIFICATION}
            response = person_store.get((request.question_id, request.run), RIGHT[request.question_id])
        else:
            response = EMPTY_STORE.get((request.question_id, request.run), RIGHT[request.question_id])
        if response == FAILED:
            return AgentOutput(None, Usage(), failure="malformed output after 2 attempts")
        return AgentOutput(response, Usage())


@pytest.fixture
def stored(scoring_config, tmp_path):
    """The records the write-line entry point stores for three runs of the scoring fixture."""
    results = tmp_path / "results.jsonl"
    config = dataclasses.replace(load_config(scoring_config), runs=3)
    run(config, ThreeRunAgent(), tmp_path / "work", PROVENANCE, results)
    return [r for r in map(json.loads, results.read_text().splitlines()) if r["record"] == "answer"]


# Paired differences


def test_a_paired_mean_difference_leaves_out_clarification_requests_failures_and_unpaired_questions(stored):
    difference = paired_difference(stored, "all_person", "empty", seed=0)

    # Per question, accuracy under the person's store minus accuracy under the empty store:
    # open-order-hours    1 (3 of 3)  - 1/2 (the wrong answer and the right one; the failure is out)
    # open-order-numbers  1 (2 of 2, the clarification request is out) - 0 (0 of 3)
    # costly-closed-orders 1 - 1
    # open-order-cost has no scored run under the empty store, only clarification requests.
    assert difference.differences == {
        "open-order-hours": 0.5,
        "open-order-numbers": 1.0,
        "costly-closed-orders": 0.0,
    }
    assert difference.mean == pytest.approx(0.5)


def test_a_bootstrap_interval_is_reproduced_by_its_seed_and_changes_with_it(stored):
    first = paired_difference(stored, "all_person", "empty", seed=7, resamples=20)
    again = paired_difference(stored, "all_person", "empty", seed=7, resamples=20)
    assert first.interval == again.interval

    by_seed = {paired_difference(stored, "all_person", "empty", seed=s, resamples=20).interval for s in range(10)}
    assert len(by_seed) > 1


@pytest.mark.parametrize("level, interval", [(0.95, (0.0, 1.0)), (0.5, (1 / 3, 2 / 3))])
def test_a_bootstrap_interval_is_a_percentile_interval_of_means_of_questions_drawn_with_replacement(
    stored, level, interval
):
    # Three questions drawn with replacement from the differences 0, 1/2 and 1: their mean is 0 or
    # 1 with probability 1/27 each, more than the 2.5 percent in each tail of a 95 percent interval.
    # Its quartiles are 1/3 (P(mean < 1/3) = 4/27, P(mean <= 1/3) = 10/27) and 2/3, by symmetry.
    difference = paired_difference(stored, "all_person", "empty", seed=0, level=level)
    assert difference.interval == pytest.approx(interval)


def test_a_paired_difference_with_no_paired_question_has_no_mean_and_no_interval(stored):
    only_the_unpaired = [r for r in stored if r["question_id"] == "open-order-cost"]
    difference = paired_difference(only_the_unpaired, "all_person", "empty", seed=0)
    assert (difference.differences, difference.mean, difference.interval) == ({}, None, None)


# The exact McNemar test


def table(both, a_only, b_only, neither):
    """Per task state, an outcome (a silent error, say) under each of two conditions, built to give
    a 2 x 2 table of the given counts."""
    cells = [(True, True)] * both + [(True, False)] * a_only + [(False, True)] * b_only + [(False, False)] * neither
    a = {f"task-{i}": under_a for i, (under_a, _) in enumerate(cells)}
    b = {f"task-{i}": under_b for i, (_, under_b) in enumerate(cells)}
    return a, b


def test_the_exact_mcnemar_test_gives_the_two_sided_binomial_p_value_of_the_discordant_pairs():
    a, b = table(both=3, a_only=1, b_only=8, neither=4)
    result = mcnemar(a, b)

    # Nine discordant pairs, one of them one way: 2 * P(X <= 1) for X ~ Binomial(9, 1/2),
    # 2 * (1 + 9) / 512. The concordant pairs do not enter.
    assert (result.a_only, result.b_only) == (1, 8)
    assert result.p_value == 20 / 512
    assert mcnemar(b, a).p_value == 20 / 512


@pytest.mark.parametrize(
    "a_only, b_only, p_value",
    [(0, 5, 2 / 32), (3, 3, 1.0), (0, 0, 1.0)],
    ids=["all-one-way", "balanced-capped-at-one", "no-discordant-pair"],
)
def test_the_exact_mcnemar_p_value_on_small_tables(a_only, b_only, p_value):
    assert mcnemar(*table(both=2, a_only=a_only, b_only=b_only, neither=2)).p_value == p_value


def test_the_mcnemar_test_refuses_conditions_that_do_not_pair_off_by_task_state():
    a, b = table(both=1, a_only=1, b_only=1, neither=1)
    del b["task-0"]
    with pytest.raises(ValueError, match="task-0"):
        mcnemar(a, b)


# Silent errors and questions to a person. The maintenance run (#45) does not exist yet; its
# records are taken to carry, per run of a task state, the silent-error flag the scorer gave it
# (`is_silent_error`) and its number of escalation calls.


def task_run(task, response_class, *, silent_error=False, escalations=0, condition="main", run=0):
    return {
        "task": task,
        "condition": condition,
        "run": run,
        "response_class": response_class,
        "silent_error": silent_error,
        "escalations": escalations,
    }


TASK_RUNS = [
    task_run("rate-before", "wrong_answer", silent_error=True),
    task_run("rate-before", "failed", escalations=2, run=1),  # asked twice, then failed: recorded, not scored
    task_run("rate-after", "wrong_answer", escalations=2),  # wrong, but it asked: not silent
    task_run("cap-before", "correct_answer", escalations=1),
    task_run("cap-after", "clarification_request"),
]


def test_the_silent_error_rate_is_each_task_states_share_of_scored_runs_that_are_silent_errors_averaged():
    # rate-before 1 (its failed run is out), the others 0 (cap-after's clarification request counts).
    assert silent_error_rate(TASK_RUNS) == 0.25


def test_questions_to_a_person_per_100_tasks_count_every_escalation_call_a_failed_runs_included():
    # Per task state, calls per run: rate-before 2 over 2 runs, rate-after 2, cap-before 1, cap-after 0.
    assert questions_per_100_tasks(TASK_RUNS) == 100.0


def test_the_silent_error_rate_weighs_each_task_state_the_same_whatever_number_of_its_runs_failed():
    # Ten task states whose three runs are silent errors; ten with two failed runs and a right answer.
    classes = {f"silent-{t}": ["wrong_answer"] * 3 for t in range(10)}
    classes |= {f"right-{t}": ["failed", "failed", "correct_answer"] for t in range(10)}
    by_task = {
        task: [task_run(task, c, silent_error=c == "wrong_answer", run=r) for r, c in enumerate(cs)]
        for task, cs in classes.items()
    }
    rate = silent_error_rate([run for runs in by_task.values() for run in runs])
    per_task = [silent_error_rate(runs) for runs in by_task.values()]

    # 1 for each of the first ten and 0 for the others, not 30 silent errors over 40 scored runs: the
    # mean of the per-task rates, which a task-level bootstrap interval is around.
    assert rate == sum(per_task) / len(per_task) == 0.5
    low, high = bootstrap_interval(per_task, seed=0)
    assert low < rate < high


def test_the_silent_error_rate_refuses_a_task_state_with_no_scored_run():
    runs = [
        task_run("rate-before", "wrong_answer", silent_error=True),
        task_run("fee-after", "failed", escalations=1),
    ]
    with pytest.raises(ValueError, match="fee-after"):
        silent_error_rate(runs)
    # Its escalation call is still a question to a person.
    assert questions_per_100_tasks(runs) == 50.0


def test_no_runs_have_no_rates_to_report():
    assert (silent_error_rate([]), questions_per_100_tasks([])) == (None, None)


# The frontier of silent errors against questions to a person

# Per task state, its base run (no escalation tool, so no question to a person) and its asked run.
FRONTIER_RUNS = [
    task_run("rate-after", "wrong_answer", silent_error=True),
    task_run("rate-after", "correct_answer", escalations=1, condition="asked"),
    task_run("cap-after", "wrong_answer", silent_error=True),
    task_run("cap-after", "wrong_answer", escalations=2, condition="asked"),
    task_run("rate-before", "wrong_answer", silent_error=True),
    task_run("rate-before", "wrong_answer", silent_error=True, condition="asked"),  # told to ask, did not
    task_run("fee-after", "correct_answer"),
    task_run("fee-after", "correct_answer", escalations=1, condition="asked"),
]
# The escalation order, first to escalate first: for confidence-escalate, the matched-asks
# selector's ranking (#51) of the task states by the agreement of their base runs.
ORDER = ["rate-after", "cap-after", "rate-before", "fee-after"]


def stored_task_runs(records, tmp_path):
    """The records as the results store keeps and gives them back."""
    path = tmp_path / "maintenance.jsonl"
    for record in records:
        append(path, PROVENANCE, record)
    return [json.loads(line) for line in path.read_text().splitlines()]


def runs_of(records, condition):
    by_task = {}
    for record in records:
        if record["condition"] == condition:
            by_task.setdefault(record["task"], []).append(record)
    return by_task


def test_the_frontier_escalates_the_first_k_tasks_of_the_order_for_every_k_from_none_to_all(tmp_path):
    records = stored_task_runs(FRONTIER_RUNS, tmp_path)
    points = frontier(runs_of(records, "main"), runs_of(records, "asked"), ORDER)

    # Escalated in the order rate-after, cap-after, rate-before, fee-after; four tasks, so each
    # question to a person is 25 per 100 tasks and each silent error a quarter of the tasks.
    assert [(p.escalated, p.questions_per_100_tasks, p.silent_error_rate) for p in points] == [
        (0, 0.0, 0.75),
        (1, 25.0, 0.5),  # rate-after asked once and got it right
        (2, 75.0, 0.25),  # cap-after asked twice: still wrong, but not silent
        (3, 75.0, 0.25),  # rate-before was told to ask and did not: still a silent error
        (4, 100.0, 0.25),
    ]


def test_the_frontier_escalates_in_the_order_it_is_given():
    base = {task: [task_run(task, "wrong_answer", silent_error=True)] for task in ("rate", "cap")}
    asked = {
        "rate": [task_run("rate", "correct_answer", escalations=1, condition="asked")],
        "cap": [task_run("cap", "correct_answer", escalations=2, condition="asked")],
    }
    # Escalating rate first costs one question over two tasks, cap first two.
    assert frontier(base, asked, ["rate", "cap"])[1].questions_per_100_tasks == 50.0
    assert frontier(base, asked, ["cap", "rate"])[1].questions_per_100_tasks == 100.0


def test_the_frontier_counts_the_questions_of_an_asked_run_that_then_failed():
    base = {
        "rate": [task_run("rate", "wrong_answer", silent_error=True, run=r) for r in range(3)],
        "fee": [task_run("fee", "correct_answer", run=r) for r in range(3)],
    }
    asked = {
        # Asked the person in every run, then failed in two of them.
        "rate": [
            task_run("rate", "failed", escalations=1, condition="asked", run=0),
            task_run("rate", "failed", escalations=1, condition="asked", run=1),
            task_run("rate", "wrong_answer", escalations=1, condition="asked", run=2),
        ],
        "fee": [task_run("fee", "correct_answer", escalations=1, condition="asked", run=r) for r in range(3)],
    }
    points = frontier(base, asked, ["rate", "fee"])

    # Escalating rate costs one question per run of rate: 50 per 100 tasks over two, not free.
    assert [(p.questions_per_100_tasks, p.silent_error_rate) for p in points] == [
        (0.0, 0.5),
        (50.0, 0.0),
        (100.0, 0.0),
    ]


def test_the_frontier_refuses_a_task_state_missing_from_the_order():
    base = {task: [task_run(task, "wrong_answer", silent_error=True)] for task in ("rate", "cap")}
    asked = {task: [task_run(task, "correct_answer", escalations=1, condition="asked")] for task in ("rate", "cap")}
    with pytest.raises(ValueError, match="cap"):
        frontier(base, asked, ["rate"])


def test_the_frontier_plot_is_written_to_a_file_from_stored_results_with_no_model_call(tmp_path):
    records = stored_task_runs(FRONTIER_RUNS, tmp_path)
    points = frontier(runs_of(records, "main"), runs_of(records, "asked"), ORDER)
    path = tmp_path / "plots" / "frontier.png"

    plot_frontier(points, path, marks={"warrant-routed": (25.0, 0.5), "version link": (0.0, 0.75)})

    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


# Flip rates


def test_the_flip_rate_is_the_share_of_questions_that_flip_under_at_least_one_rule(stored):
    # open-order-hours flips under the empty store (a wrong answer and a right one, the failure
    # aside), open-order-numbers under the person's (a clarification request and two right answers);
    # the other two give one response class per rule.
    assert flip_rate(stored) == 0.5


def question_runs(question_id, rule, *classes):
    """Stored records of a question's runs under a rule, one per response class."""
    return [{"question_id": question_id, "rule": rule, "run": i, "response_class": c} for i, c in enumerate(classes)]


def test_the_flip_rate_counts_only_questions_measured_under_every_rule_whether_they_flip_or_not():
    measured = [
        *question_runs("flips", "empty", "correct_answer", "wrong_answer"),
        *question_runs("flips", "all_person", "correct_answer", "correct_answer"),
        *question_runs("steady", "empty", "over_refusal", "over_refusal"),
        *question_runs("steady", "all_person", "correct_answer", "correct_answer"),
    ]
    # Fewer than two scored runs under one rule: left out, whether it flips under the other or not.
    unmeasured = [
        *question_runs("flips-unmeasured", "empty", "correct_answer", "wrong_answer"),
        *question_runs("flips-unmeasured", "all_person", "failed", "failed", "correct_answer"),
        *question_runs("steady-unmeasured", "empty", "correct_answer", "correct_answer"),
        *question_runs("steady-unmeasured", "all_person", "failed", "correct_answer"),
    ]
    # No record at all under one rule: unmeasured there, not steady.
    absent = question_runs("absent", "empty", "correct_answer", "correct_answer")

    assert flip_rate(measured) == 0.5
    assert flip_rate(measured + unmeasured) == 0.5
    assert flip_rate(measured + absent) == 0.5
    assert flip_rate(unmeasured) is None


# The write line's confirmatory test (global.confirmatory_test in freeze/write_line.yaml)


def test_the_sign_flip_p_value_is_the_share_of_sign_assignments_whose_sum_is_at_least_the_observed_one():
    # Three differences of 1: of the 8 ways to sign them, only all plus reaches T = 3, and only all
    # plus and all minus are as far from zero.
    assert sign_flip_test([1, 1, 1]) == SignFlip(statistic=3, n=3, p_value=Fraction(1, 8), two_sided_p=Fraction(1, 4))


def test_a_zero_difference_drops_out_of_the_sign_flip_test():
    assert sign_flip_test([1, 0, 1, 0, 1]) == sign_flip_test([1, 1, 1])


def test_sign_assignments_that_tie_the_observed_sum_are_counted_exactly():
    # T = 2/3. In thirds, the signed sums of 1, 2, 2 and 3 are 8, 6, 4 twice, 2 three times, 0 twice
    # and their negatives: 7 of the 16 are at least T, three of them equal to it, and 14 are as far
    # from zero. In floating point, 1/3 + 2/3 + 2/3 - 1 falls short of -1/3 + 2/3 - 2/3 + 1.
    result = sign_flip_test([Fraction(-1, 3), Fraction(2, 3), Fraction(-2, 3), Fraction(1)])
    assert result == SignFlip(Fraction(2, 3), 4, Fraction(7, 16), Fraction(7, 8))


@pytest.mark.parametrize(
    "differences, p_value, two_sided_p",
    [([-1, -1, -1], 1, Fraction(1, 4)), ([1, -1], Fraction(3, 4), 1)],
    ids=["all-the-other-way", "balanced"],
)
def test_the_two_sided_p_is_the_share_of_sign_assignments_whose_sum_is_as_far_from_zero(
    differences, p_value, two_sided_p
):
    # Every signing of three -1s sums to at least T = -3, two of the 8 to as far from zero; 1 and -1
    # sum to 2, 0, 0 and -2, against T = 0.
    result = sign_flip_test(differences)
    assert (result.p_value, result.two_sided_p) == (p_value, two_sided_p)


@pytest.mark.parametrize("differences", [[], [0, 0]], ids=["none", "all-zero"])
def test_no_non_zero_difference_gives_no_sign_flip_test(differences):
    assert sign_flip_test(differences) is None


def test_runs_are_paired_by_index_and_a_pair_is_kept_only_if_both_rules_scored():
    records = [
        # Run 2 is the only pair both rules scored: 0 - 1. Pairing the scored runs in order, or
        # subtracting the two rules' error rates, would give 0.
        *question_runs("hours", "confidence", "failed", "wrong_answer", "correct_answer"),
        *question_runs("hours", "settlement", "correct_answer", "failed", "wrong_answer"),
        # Three kept pairs: (1 - 0 + 1 - 1 + 0 - 0) / 3.
        *question_runs("numbers", "confidence", "wrong_answer", "wrong_answer", "correct_answer"),
        *question_runs("numbers", "settlement", "correct_answer", "wrong_answer", "correct_answer"),
        # A clarification request leaves its pair out too; an over-refusal is an error, a correct
        # refusal is not: (1 - 0 + 1 - 0) / 2.
        *question_runs("cost", "confidence", "clarification_request", "wrong_answer", "over_refusal"),
        *question_runs("cost", "settlement", "wrong_answer", "correct_answer", "correct_refusal"),
        # No pair both rules scored: it drops out.
        *question_runs("fees", "confidence", "failed", "correct_answer", "clarification_request"),
        *question_runs("fees", "settlement", "wrong_answer", "failed", "wrong_answer"),
    ]
    differences = question_differences(
        reversed(records), {"hours", "numbers", "cost", "fees"}, confidence="confidence", settlement="settlement"
    )
    assert differences == {"cost": 1, "hours": -1, "numbers": Fraction(1, 3)}


@pytest.mark.parametrize(
    "errors, unscored, expected",
    [
        # Failures as wrong: hours keeps all three pairs, 1 - 0 + 1 - 1 + 0 - 1; fees keeps runs 0
        # and 1, 1 - 1 + 0 - 1, and drops the clarification request.
        pytest.param(
            ERRORS + (ResponseClass.FAILED,), (ResponseClass.CLARIFICATION_REQUEST,),
            {"hours": 0, "cost": Fraction(1, 1), "fees": Fraction(-1, 2)}, id="failures-as-wrong",
        ),
        # Clarifications as wrong: cost keeps all three pairs, 1 - 1 + 1 - 0 + 1 - 0; fees keeps run
        # 2 only, 1 - 1.
        pytest.param(
            ERRORS + (ResponseClass.CLARIFICATION_REQUEST,), (ResponseClass.FAILED,),
            {"hours": -1, "cost": Fraction(2, 3), "fees": 0}, id="clarifications-as-wrong",
        ),
    ],
)
def test_the_frozen_sensitivity_analyses_count_failures_or_clarifications_as_errors(errors, unscored, expected):
    records = [
        *question_runs("hours", "confidence", "failed", "wrong_answer", "correct_answer"),
        *question_runs("hours", "settlement", "correct_answer", "failed", "wrong_answer"),
        *question_runs("cost", "confidence", "clarification_request", "wrong_answer", "over_refusal"),
        *question_runs("cost", "settlement", "wrong_answer", "correct_answer", "correct_refusal"),
        *question_runs("fees", "confidence", "failed", "correct_answer", "clarification_request"),
        *question_runs("fees", "settlement", "wrong_answer", "failed", "wrong_answer"),
    ]
    differences = question_differences(
        records, set(expected), confidence="confidence", settlement="settlement", errors=errors, unscored=unscored
    )
    assert differences == expected


@pytest.mark.parametrize(
    "settlement_runs",
    [["correct_answer"] * 2, ["correct_answer"] * 4, []],
    ids=["a-run-missing", "a-fourth-run", "no-run"],
)
def test_the_confirmatory_test_refuses_a_question_without_each_of_its_runs_under_both_rules(settlement_runs):
    records = [
        *question_runs("hours", "confidence", *["correct_answer"] * 3),
        *question_runs("hours", "settlement", *settlement_runs),
    ]
    with pytest.raises(ValueError, match="hours under settlement"):
        question_differences(records, {"hours"}, confidence="confidence", settlement="settlement")


def test_the_confirmatory_test_refuses_a_run_recorded_twice():
    # As when the records of two runs of the write line are read together.
    records = [
        *question_runs("hours", "confidence", *["correct_answer"] * 3) * 2,
        *question_runs("hours", "settlement", *["correct_answer"] * 3),
    ]
    with pytest.raises(ValueError, match="hours under confidence"):
        question_differences(records, {"hours"}, confidence="confidence", settlement="settlement")


def test_the_write_line_test_is_the_sign_flip_test_on_the_question_set_with_the_mean_difference(stored):
    # The fixture's rules stand in for the confidence rule (the person's store) and the settlement
    # rule (the empty store). Per question, the same-index pairs both rules scored:
    # open-order-hours     runs 0 and 2: (0 - 1 + 0 - 0) / 2; run 1 failed under the empty store
    # open-order-numbers   runs 1 and 2: (0 - 1 + 0 - 1) / 2; run 0 a clarification request
    # costly-closed-orders 0
    # open-order-cost has only clarification requests under the empty store: it drops out.
    questions = {r["question_id"] for r in stored}
    result = write_line_test(stored, questions, confidence="all_person", settlement="empty", seed=0)

    assert result.differences == {
        "costly-closed-orders": 0,
        "open-order-hours": Fraction(-1, 2),
        "open-order-numbers": -1,
    }
    # T = -3/2 on the two non-zero d_q: every signing sums to at least it, two of four as far from
    # zero.
    assert result.test == SignFlip(Fraction(-3, 2), 2, Fraction(1), Fraction(1, 2))
    assert not result.significant
    # The mean is over every question with a kept pair, zeros included, and its interval is the
    # outcome rule's bootstrap: three questions drawn with replacement from 0, -1/2 and -1 all give
    # -1 or all give 0 with probability 1/27 each, more than a 2.5 percent tail.
    assert result.mean == Fraction(-1, 2)
    assert result.interval == pytest.approx((-1.0, 0.0))


@pytest.mark.parametrize(
    "n, erring, p_value, significant",
    [(5, "confidence", Fraction(1, 32), True), (4, "confidence", Fraction(1, 16), False), (5, "settlement", 1, False)],
    ids=["five-one-way", "four-one-way", "five-the-other-way"],
)
def test_the_write_line_test_is_significant_when_its_one_sided_p_is_at_most_alpha(n, erring, p_value, significant):
    # One rule errs on every run and the other on none, so each d_q is 1 if the confidence rule errs
    # and p = 1 / 2^n, below 0.05 from five questions on; the settlement rule erring is the other
    # tail.
    probes = [f"probe-{i}" for i in range(n)]
    records = [
        record
        for q in probes
        for rule in ("confidence", "settlement")
        for record in question_runs(q, rule, *["wrong_answer" if rule == erring else "correct_answer"] * 3)
    ]
    # Records of another rule, and of a question outside the set, do not enter.
    records += question_runs("probe-0", "empty", "wrong_answer")
    records += question_runs("control", "confidence", "wrong_answer")

    result = write_line_test(records, probes, confidence="confidence", settlement="settlement", seed=0)

    assert (result.test.n, result.test.p_value, result.significant) == (n, p_value, significant)


@pytest.mark.parametrize(
    "questions, differences, mean, interval",
    [
        ({"costly-closed-orders"}, {"costly-closed-orders": 0}, 0, (0.0, 0.0)),
        ({"open-order-cost"}, {}, None, None),
        (set(), {}, None, None),
    ],
    ids=["no-difference", "no-kept-pair", "no-question"],
)
def test_a_question_set_with_no_non_zero_difference_has_no_test(stored, questions, differences, mean, interval):
    result = write_line_test(stored, questions, confidence="all_person", settlement="empty", seed=0)
    assert (result.differences, result.test, result.significant, result.mean, result.interval) == (
        differences,
        None,
        False,
        mean,
        interval,
    )
