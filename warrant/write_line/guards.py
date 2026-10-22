"""The full run's guards (#54): the spending cap, the check after the first complete pass, and the two
checks #54 asks for before the first claim-writing call: the freeze's judge validation
(`global.judge.validation`) and the predictions check of #53.

These are plain functions over token counts, records and committed files; the run command wires them
in. None of them calls a model.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from warrant.write_line.validate_judge import OPERATION, earlier_runs

# Decided by the lead on #54 (2026-10-21): the whole run may spend at most this much, and the run
# pauses after its first complete pass if that pass cost more than this many times its estimate.
CAP = 100.0
FIRST_PASS_FACTOR = 2.0


@dataclass(frozen=True)
class Prices:
    """Dollars per million input and output tokens."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, input_tokens: float, output_tokens: float) -> float:
        return (input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok) / 1_000_000


# Anthropic's list prices, the estimate's basis on #54, by the model id the run configuration names.
# Bedrock prices Claude separately and its pricing page does not list this model; the lead's bill is
# the check. A model not listed here has no price, so the run refuses it rather than guess.
LIST_PRICES = {"anthropic.claude-sonnet-5": Prices(2.0, 10.0)}


def prices_for(model: str) -> Prices:
    if model not in LIST_PRICES:
        raise ValueError(f"no list price for {model!r}; add it to warrant/write_line/guards.py first")
    return LIST_PRICES[model]


class Spend:
    """What the run has spent so far, from the token usage of every model call, against the cap.

    The next call's cost is not known before it is made. A call is allowed only if the spend so far
    plus a bound on that call stays within the cap; the bound is the largest call so far, or the
    `bound` the caller passes when it knows a larger one for the operation it is about to call. So the
    cap can be crossed by at most the amount by which one call exceeds its bound. With an estimate of
    about $25 to $30 and the pause after the first pass at twice its estimate, that is the residual
    risk #54's cap accepts.
    """

    def __init__(self, prices: Prices, cap: float = CAP):
        self.prices = prices
        self.cap = cap
        self.total = 0.0
        self.largest_call = 0.0

    def add(self, input_tokens: int, output_tokens: int) -> float:
        cost = self.prices.cost(input_tokens, output_tokens)
        self.total += cost
        self.largest_call = max(self.largest_call, cost)
        return cost

    def allows_another_call(self, bound: float = 0.0) -> bool:
        return self.total + max(self.largest_call, bound) <= self.cap

    @classmethod
    def from_records(cls, records: Iterable[Mapping], prices: Prices, cap: float = CAP) -> "Spend":
        """The spend so far from stored records: every record that carries token usage, failed calls
        included, since their tokens were paid for. For the run, pass every record of its results file
        (every run id, since a repeated run was paid for too) and the judge validation's records,
        which #54's cap also covers."""
        spend = cls(prices, cap)
        for record in records:
            if "input_tokens" in record:
                spend.add(record["input_tokens"], record["output_tokens"])
        return spend


def mean_tokens(records: Iterable[Mapping]) -> tuple[float, float]:
    """The mean input and output tokens per record, over the records that carry token usage."""
    usage = [(r["input_tokens"], r["output_tokens"]) for r in records if "input_tokens" in r]
    if not usage:
        raise ValueError("no record carries token usage")
    return sum(i for i, _ in usage) / len(usage), sum(o for _, o in usage) / len(usage)


def answer_estimate(answers: int, mean_input: float, mean_output: float, prices: Prices) -> float:
    """The estimated cost of `answers` answers at the given mean tokens per answer (the pilot's, #49)."""
    return answers * prices.cost(mean_input, mean_output)


def first_pass_cost(records: Iterable[Mapping], prices: Prices) -> float:
    """The cost of the first complete pass's answers (run 0), failed ones and ones paid for but stopped
    before they were stored included: what the estimate covers. Claim writing and judging come before
    it and are left out."""
    return sum(prices.cost(r["input_tokens"], r["output_tokens"]) for r in records
               if r.get("run") == 0 and (r.get("record") == "answer"
                                         or (r.get("record") == "spent" and r.get("operation") == "answer")))


def over_estimate(actual: float, estimate: float, factor: float = FIRST_PASS_FACTOR) -> bool:
    """Whether the first pass's answers (`first_pass_cost`) cost more than `factor` times their
    estimate (`answer_estimate`), which pauses the run for the lead."""
    return actual > factor * estimate


def predictions_differ(computed: Mapping, committed: Mapping) -> list[str]:
    """Where the predictions recomputed for this run (in the committed file's form,
    `warrant.write_line.predict.record`) differ from the committed ones: each slot's outcome, each
    reading's database, output, differs and holds, each slot's claim kind and subject, each claim
    kind's outcome, each bridge prediction, each normalised output's SHA-256, and the freeze's and
    injection record's SHA-256 when the computed record carries them. Provenance that legitimately
    differs between runs (commit, settings such as the installed DuckDB version) is not compared. The
    stores are composed from the predictions that fixed k, so any difference stops the run before
    claim writing."""
    problems = [f"{field} {computed.get(field)!r}, committed {committed.get(field)!r}"
                for field in ("freeze_sha256", "injection_record_sha256")
                if field in computed and computed.get(field) != committed.get(field)]
    claims, frozen = computed.get("claims", {}), committed.get("claims", {})
    for defect in sorted(claims.keys() | frozen.keys()):
        if defect not in claims:
            problems.append(f"{defect}: a committed slot the recomputed predictions lack")
            continue
        if defect not in frozen:
            problems.append(f"{defect}: a slot the committed predictions lack")
            continue
        ours, theirs = claims[defect], frozen[defect]
        for field in ("claim_kind", "subject", "outcome"):
            if ours.get(field) != theirs.get(field):
                problems.append(f"{defect}: {field} {ours.get(field)!r}, committed {theirs.get(field)!r}")
        readings, frozen_readings = ours.get("readings", {}), theirs.get("readings", {})
        for reading in sorted(readings.keys() | frozen_readings.keys()):
            mine, its = readings.get(reading), frozen_readings.get(reading)
            if mine is None or its is None:
                problems.append(f"{defect}: reading {reading!r} is {'missing' if mine is None else 'not committed'}")
                continue
            for field in ("database", "output", "differs", "holds"):
                if mine.get(field) != its.get(field):
                    problems.append(f"{defect}: reading {reading!r} {field} {mine.get(field)!r}, committed {its.get(field)!r}")
    for kind in sorted(computed.get("kinds", {}).keys() | committed.get("kinds", {}).keys()):
        if computed.get("kinds", {}).get(kind) != committed.get("kinds", {}).get(kind):
            problems.append(f"claim kind {kind}: {computed.get('kinds', {}).get(kind)!r}, "
                            f"committed {committed.get('kinds', {}).get(kind)!r}")
    bridge, frozen_bridge = computed.get("bridge", {}), committed.get("bridge", {})
    for defect in sorted(bridge.keys() | frozen_bridge.keys()):
        if bridge.get(defect) != frozen_bridge.get(defect):
            problems.append(f"{defect}: bridge {bridge.get(defect)!r}, committed {frozen_bridge.get(defect)!r}")
    outputs, frozen_outputs = computed.get("outputs", {}), committed.get("outputs", {})
    for content in sorted(outputs.keys() | frozen_outputs.keys()):
        if (outputs.get(content) or {}).get("sha256") != (frozen_outputs.get(content) or {}).get("sha256"):
            problems.append(f"normalised output of {content[:12]}…: its SHA-256 differs from the committed one")
    return problems


def validation_problems(results: Path, method: Mapping, model: str) -> list[str]:
    """Why the judge's validation in `results` does not clear the first claim-writing call
    (`global.judge.validation`): no file, no complete validation run, or a first complete run made
    with another judge method or model than this run's. Mismatches in the validation itself do not
    block: the freeze reports them and does not fix them."""
    results = Path(results)
    if not results.exists():
        return [f"no judge validation in {results}"]
    _, first = earlier_runs(results)
    if first is None:
        return [f"no complete validation run in {results}"]
    records = [json.loads(line) for line in results.read_text().splitlines()]
    run = [r for r in records if r.get("operation") == OPERATION and r.get("run_id") == first]
    problems = []
    models = {r.get("model") for r in run}
    if models != {model}:
        problems.append(f"the validation ran with model {sorted(models)}, this run uses {model!r}")
    methods = [r["method"] for r in run if r.get("record") == "claim"]
    if not methods or any(m != dict(method) for m in methods):
        problems.append("the validated judge method (rubric, prompt version or calls) differs from this run's")
    return problems
