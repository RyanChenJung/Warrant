"""The write line's summary (#53), recomputed from stored results with no model call.

    uv run python -m warrant.write_line.summary --config <run config> --results <results.jsonl> --judge-validation <judge_validation.jsonl> [--without <question id>]... [--out <summary.json, default summary.json beside the results>] [--replace]

It reads the run's records in the format of #53's comments: one complete run, the first whose
`complete` record is in the file for this configuration (`run_ids`); within it, each claim's first
complete judgement and each (variant, database)'s first sample 1 without a failure. Other runs are
reported as repeated runs and never used. `spent` records add cost and are never responses.

- **Confirmatory**: the settlement rule against the confidence rule of the `confident` variant (ADR
  0012) at the frozen k, by `write_line_test` (global.confirmatory_test) on Q*, the probes of the slots
  the two stores fill from different sources; "rules coincide" when there are none. Each rule's
  accuracy and wrong answers are over Q*, with the same figures over all defect probes beside them,
  labelled descriptive.
- **Descriptive**: per variant, the per-kind contributions by `paired_difference` (global.outcome_rule),
  the allocation outcomes and their agreement with the committed predictions (H1), and the curve of
  wrong writes against person asks (global.matched_asks, global.judge.wrong_write); the per-slot
  breakdown of Q* and the sensitivity analyses; the flip rate; slot and judge counts; and cost and
  time per rule in three classes (#53, 2026-10-22).

Neither function here builds a model client.
"""

import argparse
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from warrant.scoring.classify import ResponseClass, accuracy
from warrant.scoring.stats import ERRORS, UNSCORED, flip_rate, paired_difference, write_line_test
from warrant.store.claims import PredictedOutcome
from warrant.store.results import config_hash
from warrant.write_line.confidence import allocation, settlement_ask_count, slot_claim_index
from warrant.write_line.config import Config, load_config
from warrant.write_line.guards import prices_for, validation_problems
from warrant.write_line.run import committed_predictions_for, run_ids
from warrant.write_line.stores import RULES

CONFIRMATORY, DESCRIPTIVE = "confirmatory", "descriptive"
# The freeze's wording (global.confirmatory_test.rules_coincide).
COINCIDE = "rules coincide; H3 not tested at write time"
NOT_ADDITIVE = ("each rule's method cost holds everything that rule needs, so a call two rules need (sample 1) "
                "is in both, and the method costs do not add up across rules")
NO_CONTRIBUTION = "no_measurable_contribution"
ALL_PROBES = "all defect probes, descriptive"
VARIANTS = ("confident", "abstain")


def _rule(base: str, variant: str) -> str:
    return base if variant == "confident" else f"{base}_abstain"


def _exact(value: Fraction) -> str:
    return str(Fraction(value))


def _test(found) -> dict:
    """`write_line_test`'s result as written: exact fractions as strings, beside their floats."""
    test = found.test
    return {
        "differences": {q: _exact(d) for q, d in found.differences.items()},
        "statistic": None if test is None else _exact(test.statistic),
        "n": 0 if test is None else test.n,
        "p": None if test is None else float(test.p_value),
        "p_exact": None if test is None else _exact(test.p_value),
        "two_sided_p": None if test is None else float(test.two_sided_p),
        "two_sided_p_exact": None if test is None else _exact(test.two_sided_p),
        "significant": found.significant,
        "mean_difference": None if found.mean is None else float(found.mean),
        "interval": None if found.interval is None else list(found.interval),
    }


PROVENANCE = ("config_hash", "repo_commit", "model", "prompt_version", "timestamp", "run_id", "record")
OUTPUTS = {"samples": "sample", "judgements": "judgement", "stores": "store", "spent": "spent", "answers": "answer"}


def _outputs(records: Iterable[Mapping]) -> list[dict]:
    """The records without the provenance fields every record carries."""
    return [{k: v for k, v in r.items() if k not in PROVENANCE} for r in records]


def _by_record(records: Iterable[Mapping]) -> dict[str, list[Mapping]]:
    found = defaultdict(list)
    for r in records:
        found[r.get("record")].append(r)
    return found


class Selected:
    """The records of the run the summary uses."""

    def __init__(self, records: Sequence[Mapping], config_hash: str):
        started, complete, _ = run_ids(list(records), config_hash)
        self.run_id = next((r for r in started if r in complete), None)
        if self.run_id is None:
            raise ValueError("no complete run of this configuration in the results")
        self.other_runs = {}
        for r in started:
            if r != self.run_id:
                mine = [x for x in records if x.get("run_id") == r and x.get("config_hash") == config_hash]
                self.other_runs[r] = _by_record(mine)
        # Each other run with every record it wrote, in full (global.judge.runs): its claim sets, which a
        # new run draws afresh, the judge's outputs, its stores, spent records and responses. Never used
        # in any figure.
        self.repeated = [{"run_id": r, "complete": r in complete, "records": sum(x.get("run_id") == r for x in records),
                          **{key: _outputs(of[record]) for key, record in OUTPUTS.items()}}
                         for r, of in self.other_runs.items()]
        mine = [r for r in records if r.get("run_id") == self.run_id and r.get("config_hash") == config_hash]
        self.records = mine
        self.of = _by_record(mine)
        self.answers = self.of["answer"]
        self.stores = {}
        for r in self.of["store"]:
            if r["rule"] in self.stores:
                raise ValueError(f"two store records of {r['rule']} in run {self.run_id}")
            self.stores[r["rule"]] = r
        self.sample_one, self.samples = {}, {}
        for r in self.of["sample"]:
            key = (r.get("variant", "confident"), r["database"], r["sample"])
            if r["sample"] == 1:
                if not r.get("failure"):
                    self.sample_one.setdefault(key[:2], r)
            elif key in self.samples:
                raise ValueError(f"sample {key[2]} of {key[0]} on {key[1]} is stored twice")
            else:
                self.samples[key] = r
        self.judgements = {}
        for r in self.of["judgement"]:
            if r.get("complete"):
                self.judgements.setdefault((r.get("variant", "confident"), r["defect"], r["sample"], r["index"]), r)
        # Every record with tokens, whatever its run or configuration: what the spending cap counts.
        self.paid = [r for r in records if "input_tokens" in r]
        self.model = next((r["model"] for r in mine if r.get("model")), None)


def _probes(config: Config) -> dict[str, str]:
    """Each probe's defect; controls are left out."""
    return {q.id: q.defect for q in config.questions if q.defect is not None}


def _sources(store: Mapping) -> dict[str, str | None]:
    return {d: None if s is None else s["source"] for d, s in store["slots"].items()}


def _store(selected: Selected, rule: str) -> Mapping:
    if rule not in selected.stores:
        raise ValueError(f"no store record of {rule} in run {selected.run_id}")
    return selected.stores[rule]


def _per_rule(answers: Sequence[Mapping], store: Mapping) -> dict:
    classes = [a["response_class"] for a in answers]
    return {
        "answers": len(classes),
        "accuracy": accuracy(classes),
        "wrong_answers": sum(c in ERRORS for c in classes),
        "failure_rate": classes.count(ResponseClass.FAILED) / len(classes) if classes else None,
        "clarification_rate": classes.count(ResponseClass.CLARIFICATION_REQUEST) / len(classes) if classes else None,
        "person_asks": sum(store["person_asks"].values()),
    }


def _comparison(selected: Selected, config: Config, variant: str, k: int, seed: int, settings: Mapping) -> dict:
    """The settlement rule against the confidence rule of one variant, at k asks."""
    settlement, confidence = (_store(selected, _rule(r, variant)) for r in ("settlement", "confidence"))
    for store in (settlement, confidence):
        if sum(store["person_asks"].values()) != k:
            raise ValueError(f"the {store['rule']} store's person asks sum to {sum(store['person_asks'].values())}, "
                             f"not the frozen k = {k}")
    probes = _probes(config)
    s, c = _sources(settlement), _sources(confidence)
    slots = sorted(d for d in s.keys() | c.keys() if s.get(d) != c.get(d))
    questions = sorted(q for q, d in probes.items() if d in slots)

    def per_rule(on: Iterable[str]) -> dict:
        on = set(on)
        return {base: _per_rule([a for a in selected.answers if a["question_id"] in on and a["rule"] == _rule(base, variant)],
                                store)
                for base, store in (("settlement", settlement), ("confidence", confidence))}

    found = {
        "k": k,
        # Over Q*, the test's question set; and over every defect probe, beside it but not part of it.
        "rules": per_rule(questions),
        "all_defect_probes": {"label": ALL_PROBES, "rules": per_rule(probes)},
        "slots": slots,
        "questions": questions,
        "result": None,
        "test": None,
    }
    rules = dict(confidence=_rule("confidence", variant), settlement=_rule("settlement", variant))

    def test(on, **coding):
        return _test(write_line_test(selected.answers, on, seed=seed, runs=settings["runs"], alpha=settings["alpha"],
                                     resamples=settings["resamples"], level=settings["level"], **rules, **coding))

    if not slots:
        return {**found, "result": COINCIDE, "ranking": confidence.get("ranking"), "scores": confidence.get("scores"),
                "per_slot": {}, "sensitivity": {}}  # the freeze: no test runs when the rules coincide
    overall = write_line_test(selected.answers, questions, seed=seed, runs=settings["runs"], alpha=settings["alpha"],
                              resamples=settings["resamples"], level=settings["level"], **rules)
    per_slot = defaultdict(list)
    for q, d in overall.differences.items():
        per_slot[probes[q]].append(d)
    return {
        **found,
        "test": _test(overall),
        "per_slot": {d: {"questions": len(ds), "sum": _exact(sum(ds)), "mean": float(sum(ds) / len(ds))}
                     for d, ds in sorted(per_slot.items())},
        "sensitivity": {
            "failures_as_wrong": test(questions, errors=(*ERRORS, ResponseClass.FAILED),
                                      unscored=(ResponseClass.CLARIFICATION_REQUEST,)),
            "clarifications_as_wrong": test(questions, errors=(*ERRORS, ResponseClass.CLARIFICATION_REQUEST),
                                            unscored=(ResponseClass.FAILED,)),
            "all_defect_probes": test(sorted(probes)),
        },
    }


def _exact_accuracy(classes: Iterable[str]) -> Fraction | None:
    """`accuracy` as an exact fraction, so the outcome rule compares exact means with the cutoff."""
    counted = [c for c in classes if c not in UNSCORED]
    if not counted:
        return None
    return Fraction(sum(c in (ResponseClass.CORRECT_ANSWER, ResponseClass.CORRECT_REFUSAL) for c in counted), len(counted))


def _float(value: Fraction | None) -> float | None:
    return None if value is None else float(value)  # Fraction(0) is falsy, so no `value and`


def _outcome(a: Fraction | None, p: Fraction | None, cutoff: Fraction) -> str | None:
    """The frozen outcome rule on the point estimates; None when a contribution is not measured."""
    if a is None or p is None:
        return None
    if a >= cutoff:
        return PredictedOutcome.BOTH.value if p >= cutoff else PredictedOutcome.AGENT_ALONE.value
    return PredictedOutcome.PERSON_ONLY.value if p >= cutoff else NO_CONTRIBUTION


def _contributions(selected: Selected, config: Config, predictions: Mapping, variant: str, seed: int,
                   settings: Mapping) -> dict:
    """Per claim kind: A = everything from the agent - empty, P = everything from a person - everything
    from the agent, over the kind's probes, the outcome by the cutoff, and agreement with the
    predicted outcome (H1)."""
    agent, cutoff = _rule("all_agent", variant), Fraction(str(settings["cutoff"]))
    kinds = {d.id: d.slot.claim_kind.value for d in config.defects}
    found = {}
    for kind in dict.fromkeys(kinds[q.defect] for q in config.questions if q.defect is not None):
        probes = {q.id for q in config.questions if q.defect is not None and kinds[q.defect] == kind}
        answers = [a for a in selected.answers if a["question_id"] in probes]
        a, p = (paired_difference(answers, first, second, seed=seed, resamples=settings["resamples"],
                                  level=settings["level"], measure=_exact_accuracy)
                for first, second in ((agent, "empty"), ("all_person", agent)))
        outcome = _outcome(a.mean, p.mean, cutoff)
        predicted = predictions["kinds"].get(kind)
        found[kind] = {
            "label": DESCRIPTIVE,
            "agent": {"mean": _float(a.mean), "interval": a.interval and list(a.interval),
                      "differences": {q: float(d) for q, d in a.differences.items()}},
            "person": {"mean": _float(p.mean), "interval": p.interval and list(p.interval),
                       "differences": {q: float(d) for q, d in p.differences.items()}},
            "outcome": outcome,
            "near_cutoff": any(i is not None and i[0] <= cutoff <= i[1] for i in (a.interval, p.interval)),
            "predicted": predicted,
            # A mixed kind is not compared (global.per_kind_combination), nor one with no outcome.
            "agrees": None if predicted in (None, "mixed") or outcome is None else outcome == predicted,
        }
    return found


def _true_reading(defect) -> str:
    return next(r["id"] for r in defect.readings if r.get("is_true"))


def _slot_judgements(selected: Selected, config: Config, variant: str) -> dict[str, Mapping]:
    """Each slot sample 1 wrote a claim on, and that claim's first complete judgement."""
    found = {}
    for d in config.defects:
        sample = selected.sample_one.get((variant, d.database))
        index = None if sample is None else slot_claim_index(sample, d)
        if index is None:
            continue
        judgement = selected.judgements.get((variant, d.id, 1, index))
        if judgement is None:
            raise ValueError(f"sample 1's claim on {d.id} ({variant}) has no complete judgement")
        found[d.id] = judgement
    return found


def _writes(agent_slots: Iterable[str], judged: Mapping[str, Mapping], true: Mapping[str, str]) -> dict:
    """Wrong writes among the agent's slots (global.judge.wrong_write), the split variant
    (global.judge.combination) and the incomplete claims."""
    wrong = split = incomplete = 0
    for d in agent_slots:
        j, reading = judged[d], true[d]
        label = j["labels"].get(reading)
        fails = label == "fails"
        wrong += fails
        split += fails or (reading in j.get("splits", ()) and any(v.get(reading) == "fails" for v in j["valid"]))
        incomplete += label == "not_addressed"
    return {"wrong_writes": wrong, "wrong_writes_with_splits": split, "incomplete": incomplete}


def _curve(selected: Selected, config: Config, variant: str) -> dict:
    """Wrong writes at every k from 0 to all slots, the confidence rule's ranking sending its k least
    confident slots to a person, and the settlement rule as one point."""
    judged = _slot_judgements(selected, config, variant)
    true = {d.id: _true_reading(d) for d in config.defects}
    ranking = _store(selected, _rule("confidence", variant))["ranking"]
    points = []
    for k in range(len(ranking) + 1):
        sources = allocation(ranking, k, set(judged))
        points.append({"k": k, **_writes([d for d, s in sources.items() if s == "agent"], judged, true)})
    settlement = _store(selected, _rule("settlement", variant))
    agent = [d for d, s in _sources(settlement).items() if s == "agent"]
    return {"label": DESCRIPTIVE, "points": points,
            "settlement": {"asks": sum(settlement["person_asks"].values()), **_writes(agent, judged, true)}}


def _slots(selected: Selected, config: Config, predictions: Mapping, variant: str) -> dict:
    settlement = _sources(_store(selected, _rule("settlement", variant)))
    found = {}
    for d in config.defects:
        samples = [selected.sample_one.get((variant, d.database))] + [
            selected.samples.get((variant, d.database, n)) for n in range(2, 11)]
        found[d.id] = {
            "samples_filling": sum(s is not None and not s.get("failure") and slot_claim_index(s, d) is not None
                                   for s in samples),
            "settled_left_empty": predictions["claims"][d.id]["outcome"] == PredictedOutcome.AGENT_ALONE.value
                                  and settlement.get(d.id) is None,
        }
    return found


def _judge(selected: Selected, config: Config, variant: str) -> dict:
    """The judge's repeat instability on agent claims (global.judge.combination): (claim, reading)
    pairs, over judgements made with a call, with fewer than three valid calls or calls that do not
    all agree; and splits on the true reading."""
    true = {d.id: _true_reading(d) for d in config.defects}
    pairs = unstable = true_splits = 0
    for (v, defect, _, _), j in selected.judgements.items():
        if v != variant or j.get("without_a_call"):
            continue
        true_splits += true[defect] in j.get("splits", ())
        for reading in j["labels"]:
            pairs += 1
            unstable += len(j["valid"]) < 3 or len({call.get(reading) for call in j["valid"]}) > 1
    mine = [j for j in selected.of["judgement"] if j.get("variant", "confident") == variant]
    complete = {(j["defect"], j["sample"], j["index"]) for j in mine if j.get("complete")}
    cut_short = [{"defect": j["defect"], "sample": j["sample"], "index": j["index"], "error": j.get("error", ""),
                  "resent": j.get("resent", 0), "paid_answers": len(j.get("answers", ())), "valid": j.get("valid", []), "answers": j.get("answers", []),
                  "judged_again": (j["defect"], j["sample"], j["index"]) in complete}
                 for j in mine if not j.get("complete")]
    return {"pairs": pairs, "unstable": unstable, "share": unstable / pairs if pairs else None,
            "true_reading_splits": true_splits, "resent": sum(j.get("resent", 0) for j in mine), "cut_short": cut_short}


def _calls(records: Iterable[Mapping], prices) -> dict:
    records = [r for r in records if not r.get("without_a_call")]
    # A record with no duration_s (the judge validation's) leaves the time unknown, not zero.
    seconds = [r.get("duration_s") for r in records]
    known = None not in seconds
    tokens_in, tokens_out = sum(r["input_tokens"] for r in records), sum(r["output_tokens"] for r in records)
    return {"calls": len(records), "input_tokens": tokens_in, "output_tokens": tokens_out,
            "dollars": prices.cost(tokens_in, tokens_out), "seconds_total": float(sum(seconds)) if known else None,
            "seconds_median": statistics.median(seconds) if seconds and known else None}


def _cost(selected: Selected, config: Config, validation: list[Mapping] | None, tokens: Mapping) -> dict:
    """Cost and time per rule in three classes (#53, 2026-10-22): method, answering and evaluation."""
    prices = prices_for(selected.model)
    spent = selected.of["spent"]

    def samples(variant: str, first_only: bool) -> list[Mapping]:
        def wanted(r):
            return r.get("variant", "confident") == variant and (not first_only or r["sample"] == 1)
        return ([r for r in selected.of["sample"] if wanted(r)]
                + [r for r in spent if r.get("operation") == "write_claims" and wanted(r)])

    def judgements(variant: str) -> list[Mapping]:
        return [r for r in selected.of["judgement"] if r.get("variant", "confident") == variant]

    start = selected.of["start"][0] if selected.of["start"] else {}
    battery = float(sum(start["battery_s"].values())) if start.get("battery_s") else None
    method = {}
    for rule in config.rules:
        variant, base = RULES[rule], rule.removesuffix("_abstain")
        if variant is None:
            method[rule] = None
        elif base == "confidence":
            method[rule] = _calls(samples(variant, False) + judgements(variant), prices)
        else:
            method[rule] = _calls(samples(variant, True), prices)
            if base == "settlement":
                total = method[rule]["seconds_total"]
                method[rule] = {**method[rule], "battery_s": battery,
                                "seconds_total": None if None in (total, battery) else total + battery}
    answering = {rule: _calls([r for r in selected.answers if r["rule"] == rule]
                              + [r for r in spent if r.get("operation") == "answer" and r.get("rule") == rule], prices)
                 for rule in config.rules}
    # A variant's judgements are method cost of its confidence rule; without that rule the judge runs
    # only for the analysis, so they are evaluation cost (#53, 2026-10-23), as is the validation file.
    paid_validation = [r for r in validation or () if "input_tokens" in r]
    evaluation = {
        "judge_validation": None if validation is None else _calls([r for r in validation if "input_tokens" in r], prices),
        "judgements": {v: _calls(judgements(v), prices) for v in VARIANTS
                       if _rule("confidence", v) not in config.rules and judgements(v)},
    }

    def spend(by_operation: Mapping) -> dict:
        tokens_in = sum(t["input_tokens"] for t in by_operation.values())
        tokens_out = sum(t["output_tokens"] for t in by_operation.values())
        return {"input_tokens": tokens_in, "output_tokens": tokens_out, "dollars": prices.cost(tokens_in, tokens_out)}

    others = [{"run_id": r, "spend": spend(_tokens(of))} for r, of in selected.other_runs.items()]
    # The cap counts every paid call in the file, of any configuration, and the judge's validation.
    everything = spend({"file": {"input_tokens": sum(r["input_tokens"] for r in selected.paid + paid_validation),
                                 "output_tokens": sum(r["output_tokens"] for r in selected.paid + paid_validation)}})
    return {
        "label": DESCRIPTIVE,
        "note": NOT_ADDITIVE,
        "method": method,
        "answering": answering,
        "evaluation": evaluation,
        # What the run paid, each call once; the judge's validation file is not in it.
        "total_spend": spend(tokens),
        # The runs set aside, and every paid call in the file, which is what the spending cap counts.
        "repeated_runs_spend": others,
        "file_spend": everything,
        # The person is simulated by the written reference claims: asks only, no money or time.
        "person_asks": {rule: sum(_store(selected, rule)["person_asks"].values()) for rule in config.rules},
    }


def _tokens(of: Mapping[str, Sequence[Mapping]]) -> dict:
    """One run's tokens per operation, each call once: the answer, write-claims and judge records, and the
    spent records of calls paid for and stopped."""
    by = {"answer": of["answer"], "write_claims": of["sample"],
          "judge": [r for r in of["judgement"] if not r.get("without_a_call")]}
    for r in of["spent"]:
        by[r["operation"]] = [*by.get(r["operation"], []), r]
    return {op: {"input_tokens": sum(r["input_tokens"] for r in rs), "output_tokens": sum(r["output_tokens"] for r in rs)}
            for op, rs in by.items()}


def _settings(global_part: Mapping) -> dict:
    outcome, test = global_part["outcome_rule"], global_part["confirmatory_test"]
    bootstrap = outcome.get("bootstrap") or {}
    return {
        "cutoff": float(outcome["cutoff"]),
        "resamples": int(bootstrap.get("resamples", 10_000)),
        "level": float(bootstrap.get("level", 0.95)),
        "runs": int(test["pairing"]["runs_per_question"]),
        "alpha": Fraction(str(test["statistic"]["alpha"])),
    }


def summarise(config: Config, records: Sequence[Mapping], predictions: Mapping, *, config_hash: str,
              validation: Path | None = None, without: Sequence[str] = ()) -> dict:
    """The summary of the first complete run of the configuration `config_hash` names in `records`, with
    the committed `predictions`; `validation` is the judge's validation file, which must clear the
    run's judge method and model on the configuration's freeze (#147) and is the evaluation cost. A question found unscorable during the run
    stays in the confirmatory analysis (ADR 0011); `without` names the questions to leave out of a second
    analysis, given as `descriptive.without`."""
    if unknown := [q for q in without if q not in {x.id for x in config.questions}]:
        raise ValueError(f"no such question to leave out: {', '.join(unknown)}")
    selected = Selected(records, config_hash)
    methods = {json.dumps(r.get("method"), sort_keys=True) for r in selected.of["judgement"]}
    if len(methods) > 1:
        raise ValueError("the run's judgements were made with more than one judge method")
    validated = None
    if validation is not None:
        if methods and (problems := validation_problems(validation, json.loads(methods.pop()), selected.model,
                                                        config.defects)):
            raise ValueError("; ".join(problems))
        validated = [json.loads(line) for line in Path(validation).read_text().splitlines()]
    tokens = _tokens(selected.of)
    settings = _settings(config.global_part)
    seed = config.global_part["seeds"]["bootstrap"]
    k = settlement_ask_count(predictions)
    variants = [v for v in VARIANTS if _rule("settlement", v) in config.rules and _rule("confidence", v) in config.rules]
    comparisons = {v: _comparison(selected, config, v, k, seed, settings) for v in variants}
    primary = comparisons.get("confident")
    if primary is None:
        raise ValueError("the configuration has no settlement and confidence rules of the confident variant")
    descriptive_variants = {}
    for v in VARIANTS:
        if _rule("all_agent", v) not in config.rules:
            continue
        found = {"label": DESCRIPTIVE,
                 "contributions": _contributions(selected, config, predictions, v, seed, settings)}
        if v in comparisons:
            found["curve"] = _curve(selected, config, v)
            found["rules_coincide"] = comparisons[v]["result"] == COINCIDE
            if v != "confident":
                found["comparison"] = comparisons[v]
        descriptive_variants[v] = found
    found = {
        "run_id": selected.run_id,
        "config_hash": config_hash,
        "model": selected.model,
        "repeated_runs": selected.repeated,
        "confirmatory": {"label": CONFIRMATORY,
                         **{key: value for key, value in primary.items() if key not in ("per_slot", "sensitivity")}},
        "descriptive": {
            "label": DESCRIPTIVE,
            "per_slot": {"label": DESCRIPTIVE, "slots": primary["per_slot"]},
            "sensitivity": {"label": DESCRIPTIVE, **primary["sensitivity"]},
            "variants": descriptive_variants,
            # Every configured rule over every defect probe, not only the two compared ones.
            "rules": {"label": ALL_PROBES,
                      "rules": {rule: _per_rule([a for a in selected.answers
                                                 if a["rule"] == rule and a["question_id"] in _probes(config)],
                                                _store(selected, rule))
                                for rule in config.rules}},
            "flip_rate": flip_rate([a for a in selected.answers if a["question_id"] in {q.id for q in config.questions}]),
            "slots": {v: _slots(selected, config, predictions, v) for v in variants},
            "judge": {v: _judge(selected, config, v) for v in variants},
            "cost": _cost(selected, config, validated, tokens),
            "tokens": tokens,
        },
    }
    if without:
        reduced = summarise(replace(config, questions=tuple(q for q in config.questions if q.id not in without)),
                            records, predictions, config_hash=config_hash, validation=validation)
        found["descriptive"]["without"] = {**reduced, "questions": list(without),
                                           "confirmatory": {**reduced["confirmatory"], "label": DESCRIPTIVE}}
    return found


def _report(summary: Mapping) -> str:
    c = summary["confirmatory"]
    lines = [f"run {summary['run_id']}, {len(summary['repeated_runs'])} other runs set aside",
             f"confirmatory: settlement against confidence at k = {c['k']}"]
    if c["result"] == COINCIDE:
        lines.append(f"  {COINCIDE}")
    else:
        t = c["test"]
        lines.append(f"  Q*: {len(c['questions'])} probes on {', '.join(c['slots'])}; T = {t['statistic']}, n = {t['n']}, "
                     f"p = {t['p_exact']} (two-sided {t['two_sided_p_exact']}), significant: {t['significant']}")
    for rule, r in c["rules"].items():
        a = c["all_defect_probes"]["rules"][rule]
        lines.append(f"  {rule} on Q*: accuracy {r['accuracy']}, {r['wrong_answers']} wrong answers, {r['person_asks']} asks; "
                     f"{ALL_PROBES}: accuracy {a['accuracy']}, {a['wrong_answers']} wrong answers")
    cost = summary["descriptive"]["cost"]
    lines.append(f"total spend (each call once, validation file apart): ${cost['total_spend']['dollars']:.4f}; "
                 f"per-rule method cost: {cost['note']}")
    lines.append("descriptive:")
    for variant, v in summary["descriptive"]["variants"].items():
        for kind, k in v["contributions"].items():
            lines.append(f"  {variant} {kind}: A = {k['agent']['mean']}, P = {k['person']['mean']}, "
                         f"outcome {k['outcome']}, predicted {k['predicted']}, agrees {k['agrees']}")
        if "curve" in v:
            lines.append(f"  {variant} wrong writes by k: {[p['wrong_writes'] for p in v['curve']['points']]}, "
                         f"settlement {v['curve']['settlement']['wrong_writes']} at {v['curve']['settlement']['asks']} asks")
    return "\n".join(lines)


def _held(text: str) -> str:
    """What an existing output file holds, for the refusal: whose summary, or no summary."""
    try:
        found = json.loads(text)
    except ValueError:
        found = None
    run = found.get("run_id") if isinstance(found, dict) else None
    return f"the summary of run {run}" if run else "no summary"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path, help="the run configuration")
    parser.add_argument("--results", required=True, type=Path, help="the run's results file")
    parser.add_argument("--predictions", type=Path,
                        help="the committed predictions (default: those naming the configuration's injection record)")
    parser.add_argument("--judge-validation", required=True, type=Path,
                        help="the judge's validation file: it must clear the run's judge method (rubric SHA-256 included), model and prompt version "
                             "on the configuration's freeze")
    parser.add_argument("--without", action="append", default=[], metavar="QUESTION_ID",
                        help="a question found unscorable during the run; it stays in the confirmatory analysis, "
                             "and the analysis without it is given as descriptive (repeatable)")
    parser.add_argument("--out", type=Path,
                        help="where to write the summary as JSON (default: summary.json beside the run's results)")
    parser.add_argument("--replace", action="store_true",
                        help="replace an existing --out file this summary would change; without it, only an identical "
                             "summary is written over it")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    try:
        predictions = (json.loads(args.predictions.read_text()) if args.predictions
                       else committed_predictions_for(config))
        if predictions is None:
            raise ValueError("no committed predictions for this configuration; pass --predictions")
        records = [json.loads(line) for line in args.results.read_text().splitlines()]
        summary = summarise(config, records, predictions, config_hash=config_hash(args.config),
                            validation=args.judge_validation, without=args.without)
    except ValueError as error:
        print(f"refused: {error}")
        return 1
    # Beside the run's results, so a second freeze's summary does not land on the first's (#147); and an
    # existing file is written over only by an identical summary, which reproduces it, unless --replace.
    out = args.out or args.results.parent / "summary.json"
    text = json.dumps(summary, indent=2) + "\n"
    if out.exists() and not args.replace:
        try:
            existing = out.read_text()
        except (OSError, UnicodeDecodeError) as error:
            print(f"refused: {out} cannot be read ({type(error).__name__}); pass another --out")
            return 1
        if existing != text:
            print(f"refused: {out} holds {_held(existing)}, which this summary of run {summary['run_id']} would "
                  "change; pass --replace to replace it, or another --out")
            return 1
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    except OSError as error:
        print(f"refused: {out} cannot be written ({type(error).__name__}); pass another --out")
        return 1
    print(_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
