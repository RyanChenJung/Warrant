"""Statistics shared by both lines (#41), computed from stored results with no model call.

The summaries that will call these, the write line's (#53) and the maintenance line's (#48), do not
exist yet, so the statistics are tested on fixture results: records the write-line entry point
stored for a fixture run, or hand-built records shaped like the stored ones.
"""

import dataclasses
import json

import pytest

from warrant.agent.interface import AgentOutput, Response, ResponseKind, Usage
from warrant.scoring.stats import (
    flip_rate,
    frontier,
    mcnemar,
    paired_difference,
    plot_frontier,
    questions_per_100_tasks,
    silent_error_rate,
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
    return [json.loads(line) for line in results.read_text().splitlines()]


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
    task_run("rate-after", "wrong_answer", escalations=2),  # wrong, but it asked: not silent
    task_run("cap-before", "correct_answer", escalations=1),
    task_run("cap-after", "clarification_request"),
    task_run("fee-after", "failed", escalations=1),  # recorded, not scored
]


def test_the_silent_error_rate_is_the_share_of_scored_runs_that_are_silent_errors():
    # One silent error out of four scored runs: the clarification request counts, the failure not.
    assert silent_error_rate(TASK_RUNS) == 0.25


def test_questions_to_a_person_per_100_tasks_count_every_escalation_call_of_the_scored_runs():
    # Three escalation calls over four scored runs.
    assert questions_per_100_tasks(TASK_RUNS) == 75.0


def test_runs_that_all_failed_have_no_rates_to_report():
    failed = [task_run("fee-after", "failed", escalations=1)]
    assert (silent_error_rate(failed), questions_per_100_tasks(failed)) == (None, None)


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
# The agreement of each task state's base runs: the least confident are escalated first.
CONFIDENCE = {"rate-after": 0.25, "cap-after": 0.5, "rate-before": 0.75, "fee-after": 1.0}


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


def test_the_frontier_escalates_the_k_least_confident_tasks_for_every_k_from_none_to_all(tmp_path):
    records = stored_task_runs(FRONTIER_RUNS, tmp_path)
    points = frontier(runs_of(records, "main"), runs_of(records, "asked"), CONFIDENCE, seed=0)

    # Escalated in the order rate-after, cap-after, rate-before, fee-after; four tasks, so each
    # question to a person is 25 per 100 tasks and each silent error a quarter of the runs.
    assert [(p.escalated, p.questions_per_100_tasks, p.silent_error_rate) for p in points] == [
        (0, 0.0, 0.75),
        (1, 25.0, 0.5),  # rate-after asked once and got it right
        (2, 75.0, 0.25),  # cap-after asked twice: still wrong, but not silent
        (3, 75.0, 0.25),  # rate-before was told to ask and did not: still a silent error
        (4, 100.0, 0.25),
    ]


def test_tied_confidence_is_broken_by_the_seed_whatever_order_the_tasks_come_in():
    base = {
        "rate": [task_run("rate", "wrong_answer", silent_error=True)],
        "cap": [task_run("cap", "wrong_answer", silent_error=True)],
    }
    asked = {
        "rate": [task_run("rate", "correct_answer", escalations=1, condition="asked")],
        "cap": [task_run("cap", "correct_answer", escalations=2, condition="asked")],
    }
    tied = {"rate": 0.5, "cap": 0.5}
    reordered = {"cap": 0.5, "rate": 0.5}

    def first_escalation(confidence, seed):
        return frontier(base, asked, confidence, seed=seed)[1].questions_per_100_tasks

    for seed in range(20):
        assert first_escalation(tied, seed) == first_escalation(tied, seed) == first_escalation(reordered, seed)
    # Escalating rate first costs one question over two tasks, cap first two.
    assert {first_escalation(tied, seed) for seed in range(20)} == {50.0, 100.0}


def test_the_frontier_plot_is_written_to_a_file_from_stored_results_with_no_model_call(tmp_path):
    records = stored_task_runs(FRONTIER_RUNS, tmp_path)
    points = frontier(runs_of(records, "main"), runs_of(records, "asked"), CONFIDENCE, seed=0)
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


def test_the_flip_rate_leaves_out_questions_whose_flip_could_not_be_measured():
    records = [
        # Flips under one rule: it flips, whatever the other rule could not show.
        *question_runs("flips", "empty", "correct_answer", "wrong_answer"),
        *question_runs("flips", "all_person", "failed", "failed", "correct_answer"),
        # Steady under one rule, unmeasured under the other: whether it flips is unknown.
        *question_runs("unknown", "empty", "correct_answer", "correct_answer"),
        *question_runs("unknown", "all_person", "failed", "correct_answer"),
        *question_runs("steady", "empty", "wrong_answer", "wrong_answer"),
        *question_runs("steady", "all_person", "correct_answer", "correct_answer"),
        *question_runs("also-steady", "empty", "over_refusal", "over_refusal"),
        *question_runs("also-steady", "all_person", "correct_answer", "correct_answer"),
    ]
    assert flip_rate(records) == pytest.approx(1 / 3)
    assert flip_rate(question_runs("unknown", "empty", "failed", "correct_answer")) is None
