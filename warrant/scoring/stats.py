"""Statistics both lines share (#41), computed from stored results with no model call.

A record is one stored result, as the results store keeps it: a mapping with at least the item it
is about (a question or a task state), the condition it ran under (an allocation rule or a
maintenance condition) and its response class. A maintenance run's record also carries its
silent-error and stale-value flags and its number of escalation calls.

The bootstrap method and the write line's confirmatory test belong to the global part of the freeze
(#33): until it is wired in, the bootstrap's choices are parameters, with a percentile bootstrap
over items as the default. The write line's confirmatory test is `write_line_test`, the exact
sign-flip test of global.confirmatory_test in freeze/write_line.yaml, with that file's values as
defaults except the bootstrap seed, which the caller passes. The maintenance line's confirmatory test is `mcnemar` on silent errors, paired by task
state.
"""

import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from matplotlib.figure import Figure

from warrant.scoring.classify import ResponseClass, accuracy, flips

Record = Mapping[str, Any]

RESAMPLES = 10_000
LEVEL = 0.95

# The write line's confirmatory test (global.confirmatory_test). A wrong answer, an inadequate
# refusal and an answered unanswerable question among them, or an over-refusal is an error; a
# failure after retries or a clarification request is not scored, and leaves its pair out.
RUNS_PER_QUESTION = 3
ERRORS = (ResponseClass.WRONG_ANSWER, ResponseClass.OVER_REFUSAL)
UNSCORED = (ResponseClass.FAILED, ResponseClass.CLARIFICATION_REQUEST)
ALPHA = Fraction(1, 20)

# The frontier plot: the frontier in the first categorical colour, single conditions as points in
# ink, each with its own marker and a label beside it, so no identity rests on colour alone.
FRONTIER_COLOUR = "#2a78d6"
INK = "#0b0b0b"
GRID = "#e4e3df"
MARKERS = ("s", "D", "^", "v", "P")


@dataclass(frozen=True)
class PairedDifference:
    # Per item paired in both conditions, its measure under the first minus under the second.
    differences: dict[str, float]
    # Their mean and its bootstrap interval; None when no item is paired.
    mean: float | None
    interval: tuple[float, float] | None


def _percentile(ordered: Sequence[float], q: float) -> float:
    """The q-quantile of sorted values, interpolated linearly between the two nearest."""
    h = (len(ordered) - 1) * q
    below = math.floor(h)
    above = min(below + 1, len(ordered) - 1)
    return ordered[below] + (h - below) * (ordered[above] - ordered[below])


def bootstrap_interval(
    values: Sequence[float], *, seed: int, resamples: int = RESAMPLES, level: float = LEVEL
) -> tuple[float, float] | None:
    """A percentile bootstrap interval for the mean of per-item values: the items are drawn with
    replacement `resamples` times, by Python's Mersenne Twister seeded with `seed`. None when
    there are no values."""
    if not values:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(resamples))
    tail = (1 - level) / 2
    return _percentile(means, tail), _percentile(means, 1 - tail)


def _answers(records: Iterable[Record]) -> Iterable[Record]:
    """The answer records: a write-line run's start and complete records (#54) carry no response,
    and records with no type, such as the maintenance line's, are answers."""
    return (record for record in records if record.get("record", "answer") == "answer")


def _classes(records: Iterable[Record], item: str, condition: str) -> dict[tuple[str, str], list[str]]:
    """Each item's response classes under each condition."""
    classes = defaultdict(list)
    for record in _answers(records):
        classes[(record[item], record[condition])].append(record["response_class"])
    return classes


def paired_difference(
    records: Iterable[Record],
    a: str,
    b: str,
    *,
    seed: int,
    resamples: int = RESAMPLES,
    level: float = LEVEL,
    item: str = "question_id",
    condition: str = "rule",
    measure: Callable[[Iterable[str]], float | None] = accuracy,
) -> PairedDifference:
    """The mean of per-item paired differences, condition `a` minus condition `b`, with a bootstrap
    interval over items.

    An item is paired when its measure exists under both, which for accuracy means at least one
    scored run in both: clarification requests and failures are left out, as accuracy leaves them.
    """
    classes = _classes(records, item, condition)
    items = sorted({i for i, _ in classes})
    differences = {}
    for i in items:
        under_a, under_b = measure(classes.get((i, a), [])), measure(classes.get((i, b), []))
        if under_a is not None and under_b is not None:
            differences[i] = under_a - under_b
    values = list(differences.values())
    return PairedDifference(
        differences,
        sum(values) / len(values) if values else None,
        bootstrap_interval(values, seed=seed, resamples=resamples, level=level),
    )


def flip_rate(records: Iterable[Record], *, item: str = "question_id", condition: str = "rule") -> float | None:
    """The share of items that flip under at least one condition (`flips`), over the items whose
    flip is measured under every condition in the records.

    An item with fewer than two scored runs under some condition, or no record at all, is left out
    whatever it did under the others, so whether an item counts does not depend on whether it
    flips. None when no item is left.
    """
    classes = _classes(records, item, condition)
    conditions = {c for _, c in classes}
    measured = []
    for i in {i for i, _ in classes}:
        under = [flips(classes.get((i, c), [])) for c in conditions]
        if None not in under:
            measured.append(any(under))
    return sum(measured) / len(measured) if measured else None


@dataclass(frozen=True)
class McNemar:
    # The discordant pairs: items whose outcome holds under the first condition only, and under the
    # second only.
    a_only: int
    b_only: int
    p_value: float


def mcnemar(a: Mapping[str, bool], b: Mapping[str, bool]) -> McNemar:
    """The exact McNemar test of a binary outcome under two conditions, paired by item: the two-sided
    exact binomial test of the discordant pairs against even odds, its p-value capped at 1."""
    if a.keys() != b.keys():
        unpaired = sorted(a.keys() ^ b.keys())
        raise ValueError(f"items outside one of the two conditions: {', '.join(unpaired)}")
    a_only = sum(a[i] and not b[i] for i in a)
    b_only = sum(b[i] and not a[i] for i in a)
    n = a_only + b_only
    tail = sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2**n
    return McNemar(a_only, b_only, min(1.0, 2 * tail))


def question_differences(
    records: Iterable[Record],
    questions: Collection[str],
    *,
    confidence: str,
    settlement: str,
    runs: int = RUNS_PER_QUESTION,
    errors: Collection[str] = ERRORS,
    unscored: Collection[str] = UNSCORED,
) -> dict[str, Fraction]:
    """Per question of `questions` with a kept pair, d_q: the mean over its kept pairs of
    e_confidence - e_settlement, as an exact fraction, where e is 1 for an error and 0 otherwise.

    Run r under the confidence rule is paired with run r under the settlement rule, and a pair is
    kept only if both responses were scored. A question with no kept pair drops out. Each question
    must have runs 0 to `runs` - 1 once each under both rules; records of other questions and other
    rules are ignored. `errors` and `unscored` default to the freeze's coding; its descriptive
    sensitivity analyses pass others: failures as wrong (`errors` plus FAILED, only clarification
    requests unscored) and clarifications as wrong (`errors` plus CLARIFICATION_REQUEST, only
    failures unscored).
    """
    rules = (confidence, settlement)
    classes = defaultdict(dict)  # (question, rule) -> {run: response class}
    repeated = set()
    for record in _answers(records):
        key = (record["question_id"], record["rule"])
        if key[0] in questions and key[1] in rules:
            if record["run"] in classes[key]:
                repeated.add(key)
            classes[key][record["run"]] = record["response_class"]
    incomplete = [
        f"{q} under {rule}"
        for q in sorted(questions)
        for rule in rules
        if (q, rule) in repeated or classes[(q, rule)].keys() != set(range(runs))
    ]
    if incomplete:
        raise ValueError(f"questions without runs 0 to {runs - 1} once each: {', '.join(incomplete)}")
    differences = {}
    for q in sorted(questions):
        pairs = [(classes[(q, confidence)][r], classes[(q, settlement)][r]) for r in range(runs)]
        kept = [(c, s) for c, s in pairs if c not in unscored and s not in unscored]
        if kept:
            differences[q] = Fraction(sum((c in errors) - (s in errors) for c, s in kept), len(kept))
    return differences


@dataclass(frozen=True)
class SignFlip:
    # T, the sum of the non-zero differences, and n, their number.
    statistic: Fraction
    n: int
    # The one-sided upper p and the two-sided p.
    p_value: Fraction
    two_sided_p: Fraction


def sign_flip_test(differences: Iterable[Fraction]) -> SignFlip | None:
    """The exact sign-flip test of paired differences, on the non-zero ones.

    The one-sided p is the share of the 2^n assignments of signs to the n non-zero differences whose
    sum T* is at least their sum T; the two-sided p is the share whose |T*| is at least |T|. Sums
    are exact fractions, so a T* equal to T is counted however it is reached. None when no
    difference is non-zero: there is nothing to flip, so no test, rather than a p of 1.
    """
    values = [Fraction(d) for d in differences if d != 0]
    if not values:
        return None
    # Each signed sum and the number of assignments that reach it, built one difference at a time.
    sums = Counter({Fraction(0): 1})
    for d in values:
        signed = Counter()
        for total, count in sums.items():
            signed[total + d] += count
            signed[total - d] += count
        sums = signed
    t = sum(values)
    return SignFlip(
        t,
        len(values),
        Fraction(sum(count for total, count in sums.items() if total >= t), 2 ** len(values)),
        Fraction(sum(count for total, count in sums.items() if abs(total) >= abs(t)), 2 ** len(values)),
    )


@dataclass(frozen=True)
class WriteLineTest:
    # d_q per question of the set with a kept pair.
    differences: dict[str, Fraction]
    # The sign-flip test on the non-zero d_q, and whether its one-sided p is at most alpha; None and
    # False when no d_q is non-zero.
    test: SignFlip | None
    significant: bool
    # The mean d_q over every question with a kept pair, zeros included, and its bootstrap interval
    # over those questions; None when no question has a kept pair.
    mean: Fraction | None
    interval: tuple[float, float] | None


def write_line_test(
    records: Iterable[Record],
    questions: Collection[str],
    *,
    confidence: str,
    settlement: str,
    seed: int,
    runs: int = RUNS_PER_QUESTION,
    alpha: Fraction = ALPHA,
    resamples: int = RESAMPLES,
    level: float = LEVEL,
    errors: Collection[str] = ERRORS,
    unscored: Collection[str] = UNSCORED,
) -> WriteLineTest:
    """The write line's confirmatory test: the confidence rule against the settlement rule on
    `questions`, the question set Q*, by `question_differences` and `sign_flip_test`.

    The test is one-sided: a small p means more errors under the confidence rule. The mean d_q's
    interval is the outcome rule's bootstrap, over questions with runs averaged within each; `seed`
    is the freeze's bootstrap seed, which the caller passes. An empty `questions` is the freeze's
    rules_coincide case, which the caller reports in the frozen wording; a set whose differences are
    all zero, or that has no kept pair, also has no test.
    """
    differences = question_differences(
        records, questions, confidence=confidence, settlement=settlement, runs=runs, errors=errors, unscored=unscored
    )
    values = list(differences.values())
    test = sign_flip_test(values)
    return WriteLineTest(
        differences,
        test,
        test is not None and test.p_value <= alpha,
        sum(values) / len(values) if values else None,
        bootstrap_interval([float(d) for d in values], seed=seed, resamples=resamples, level=level),
    )


def _scored(runs: Iterable[Record]) -> list[Record]:
    """The runs a response was scored for: a failed call is recorded, not scored."""
    return [run for run in runs if run["response_class"] != ResponseClass.FAILED]


def _by_task(runs: Iterable[Record], item: str) -> dict[str, list[Record]]:
    by_task = defaultdict(list)
    for run in runs:
        by_task[run[item]].append(run)
    return by_task


def _rate_per_task(by_task: Mapping[str, Sequence[Record]], flag: str = "silent_error") -> float | None:
    """Each task's share of scored runs whose `flag` is set, averaged over tasks."""
    scored = {task: _scored(runs) for task, runs in by_task.items()}
    unscored = sorted(task for task, runs in scored.items() if not runs)
    if unscored:
        raise ValueError(f"tasks with no scored run: {', '.join(unscored)}")
    shares = [sum(bool(run[flag]) for run in runs) / len(runs) for runs in scored.values()]
    return sum(shares) / len(shares) if shares else None


def _questions_per_100_tasks(by_task: Mapping[str, Sequence[Record]]) -> float | None:
    per_task = [sum(run["escalations"] for run in runs) / len(runs) for runs in by_task.values()]
    return 100 * sum(per_task) / len(per_task) if per_task else None


def silent_error_rate(runs: Iterable[Record], *, item: str = "task") -> float | None:
    """The silent-error rate per task: each task's share of scored runs that are silent errors (its
    runs' `silent_error`, as the scorer decided it with `is_silent_error`), averaged over tasks.

    Failed runs are left out, as accuracy leaves them out, and each task weighs the same whatever
    number of its runs failed, so the rate is the mean that a task-level bootstrap interval of the
    per-task rates is around. A task with no scored run raises rather than dropping out unseen.
    None when there are no runs.
    """
    return _rate_per_task(_by_task(runs, item))


def stale_value_rate(runs: Iterable[Record], *, item: str = "task") -> float | None:
    """The stale-value rate per task, by the rule of `silent_error_rate`: each task's share of scored
    runs whose answer is a stale value (its runs' `stale_value`, as the scorer decided it with
    `is_stale_value`), averaged over tasks. Before drift no answer is one."""
    return _rate_per_task(_by_task(runs, item), "stale_value")


def questions_per_100_tasks(runs: Iterable[Record], *, item: str = "task") -> float | None:
    """Questions to a person per 100 tasks: each task's escalation calls per run, averaged over
    tasks, times 100. Each call is one question, a failed run's included, since the person was
    asked. None when there are no runs."""
    return _questions_per_100_tasks(_by_task(runs, item))


@dataclass(frozen=True)
class FrontierPoint:
    escalated: int
    questions_per_100_tasks: float
    silent_error_rate: float


def frontier(
    base: Mapping[str, Sequence[Record]], asked: Mapping[str, Sequence[Record]], order: Sequence[str]
) -> list[FrontierPoint]:
    """Silent errors against questions to a person, both per task, when the first k tasks of
    `order` take their asked runs and the rest their base runs, for every k from none to all.

    `base` and `asked` hold each task's runs. `order` is the escalation order, first to escalate
    first: for confidence-escalate, the matched-asks selector's ranking (#51), least confident
    first. It must hold every task of `base` and `asked` once, so that no task drops out unseen.
    """
    tasks = base.keys() | asked.keys() | set(order)
    mismatched = sorted(t for t in tasks if t not in base or t not in asked or order.count(t) != 1)
    if mismatched:
        raise ValueError(f"tasks not once in each of base, asked and the order: {', '.join(mismatched)}")
    points = []
    for k in range(len(order) + 1):
        runs = {task: asked[task] for task in order[:k]} | {task: base[task] for task in order[k:]}
        points.append(FrontierPoint(k, _questions_per_100_tasks(runs), _rate_per_task(runs)))
    return points


def plot_frontier(
    points: Sequence[FrontierPoint],
    path: Path,
    *,
    label: str = "confidence-escalate",
    marks: Mapping[str, tuple[float, float]] | None = None,
) -> None:
    """Draw silent errors against questions to a person, both per 100 tasks, and write the plot to
    `path` in the format its suffix names.

    The frontier is one line; each mark is one condition's questions per 100 tasks and silent-error
    rate, drawn as a labelled point.
    """
    figure = Figure(figsize=(5, 3.5), layout="constrained")
    axes = figure.subplots()
    axes.plot(
        [p.questions_per_100_tasks for p in points],
        [100 * p.silent_error_rate for p in points],
        color=FRONTIER_COLOUR,
        linewidth=2,
        marker="o",
        markersize=4,
        label=label,
    )
    marks = marks or {}
    for i, (name, (questions, rate)) in enumerate(marks.items()):
        marker = MARKERS[i % len(MARKERS)]
        axes.plot(questions, 100 * rate, linestyle="none", marker=marker, markersize=8, color=INK, label=name)
    middle = sum(axes.get_xlim()) / 2
    for name, (questions, rate) in marks.items():
        left = questions > middle  # a label in the right half goes on the left, inside the plot
        axes.annotate(
            name,
            (questions, 100 * rate),
            xytext=(-6 if left else 6, 6),
            textcoords="offset points",
            ha="right" if left else "left",
            color=INK,
        )
    axes.set_ylim(bottom=0)
    axes.set_xlabel("Questions to a person per 100 tasks")
    axes.set_ylabel("Silent errors per 100 tasks")
    axes.grid(color=GRID, linewidth=0.8)
    axes.set_axisbelow(True)
    axes.spines[["top", "right"]].set_visible(False)
    axes.legend(frameon=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)
