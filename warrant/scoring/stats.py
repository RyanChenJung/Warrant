"""Statistics both lines share (#41), computed from stored results with no model call.

A record is one stored result, as the results store keeps it: a mapping with at least the item it
is about (a question or a task state), the condition it ran under (an allocation rule or a
maintenance condition) and its response class. A maintenance run's record also carries its
silent-error flag and its number of escalation calls.

The bootstrap method and the write line's confirmatory test belong to the global part of the freeze
(#33): until it is wired in, the bootstrap's choices are parameters, with a percentile bootstrap
over items as the default, and the confirmatory test is left to be built from these pieces. The
maintenance line's confirmatory test is `mcnemar` on silent errors, paired by task state.
"""

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from matplotlib.figure import Figure

from warrant.scoring.classify import ResponseClass, accuracy, flips

Record = Mapping[str, Any]

RESAMPLES = 10_000
LEVEL = 0.95

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


def _classes(records: Iterable[Record], item: str, condition: str) -> dict[tuple[str, str], list[str]]:
    """Each item's response classes under each condition."""
    classes = defaultdict(list)
    for record in records:
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
    """The share of items that flip under at least one condition (`flips`).

    An item is left out when that cannot be measured: it flips under no condition, and under some
    condition it had fewer than two scored runs. None when no item is left.
    """
    by_item = defaultdict(list)
    for (i, _), classes in _classes(records, item, condition).items():
        by_item[i].append(flips(classes))
    measured = [True in f for f in by_item.values() if True in f or None not in f]
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


def _scored(runs: Iterable[Record]) -> list[Record]:
    """The runs a response was scored for: a failed call is recorded, not scored."""
    return [run for run in runs if run["response_class"] != ResponseClass.FAILED]


def silent_error_rate(runs: Iterable[Record]) -> float | None:
    """The share of scored runs that are silent errors, each run's `silent_error` as the scorer
    decided it (`is_silent_error`). None when no run was scored."""
    scored = _scored(runs)
    return sum(bool(run["silent_error"]) for run in scored) / len(scored) if scored else None


def questions_per_100_tasks(runs: Iterable[Record]) -> float | None:
    """Escalation calls per 100 scored runs, each call one question to a person: per 100 tasks,
    averaged over runs when each task has as many. None when no run was scored."""
    scored = _scored(runs)
    return 100 * sum(run["escalations"] for run in scored) / len(scored) if scored else None


def least_confident(confidence: Mapping[str, float], k: int, *, seed: int) -> list[str]:
    """The k items of lowest confidence, least confident first, ties broken by `seed`.

    Confidence may be anything that sorts, such as an agreement and then a mean self-reported
    confidence. Items are put in a seeded random order before the stable sort by confidence, so the
    tie-break does not depend on the order they come in.
    """
    items = sorted(confidence)
    random.Random(seed).shuffle(items)
    return sorted(items, key=confidence.__getitem__)[:k]


@dataclass(frozen=True)
class FrontierPoint:
    escalated: int
    questions_per_100_tasks: float
    silent_error_rate: float


def frontier(
    base: Mapping[str, Sequence[Record]],
    asked: Mapping[str, Sequence[Record]],
    confidence: Mapping[str, float],
    *,
    seed: int,
) -> list[FrontierPoint]:
    """Silent errors against questions to a person when the k least confident tasks take their
    asked runs and the rest their base runs, for every k from none to all.

    `base` and `asked` hold each task's runs, all of which enter the two rates; `confidence` ranks
    the tasks, ties broken by `seed`.
    """
    order = least_confident(confidence, len(confidence), seed=seed)
    points = []
    for k in range(len(order) + 1):
        runs = [run for task in order[:k] for run in asked[task]]
        runs += [run for task in order[k:] for run in base[task]]
        points.append(FrontierPoint(k, questions_per_100_tasks(runs), silent_error_rate(runs)))
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
