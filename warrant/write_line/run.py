"""The write-line entry point: build the reading databases, predict, compute gold answers, write
claims, compose stores, ask the agent, score. With `stop_after_prediction` it returns before any
agent call (#37).

The rules are the empty store, everything from a person, and, from sample 1 of each prompt variant
(ADR 0012), everything from the agent and the settlement rule (#50), and the confidence rule, which
ranks the slots by samples 1 to 10 and the judge's profiles of their slot claims (#51).
"""

import argparse
import json
import signal
import sqlite3
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from warrant.agent.claude import ClaudeAgent, ClaudeClaimWriter, ClaudeJudge
from warrant.agent.config import ModelConfig
from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Tool, Usage
from warrant.agent.judge import JUDGE_PROMPT_VERSION, Judge, JudgeMethod, JudgeModel
from warrant.agent.tools import ReadOnlySQL
from warrant.agent.write_claims import (
    WRITE_CLAIMS_PROMPT_VERSION,
    BusinessTerms,
    ClaimWritingModel,
    WriteClaimsRequest,
    write_claims,
)
from warrant.config import data_dir
from warrant.data.sqlite import query, query_with_columns, schema
from warrant.defects.audit import Audit
from warrant.defects.build import Built, build
from warrant.defects.inject import Defect
from warrant.scoring.classify import (
    TOLERANCE,
    Bucket,
    RefusalCheck,
    ResponseClass,
    Result,
    Score,
    accuracy,
    execute,
    flips,
    results_match,
    rule_based_refusal_check,
    score,
)
from warrant.store.claims import KnowledgeStore
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.confidence import (
    CombinationRule,
    allocation,
    ranking,
    scores,
    settlement_ask_count,
    slot_claim_index,
    with_sample_one_claim,
)
from warrant.write_line.config import Config, Question, load_config
from warrant.write_line.guards import (
    Spend,
    answer_estimate,
    first_pass_cost,
    mean_tokens,
    over_estimate,
    predictions_differ,
    prices_for,
    validation_problems,
)
from warrant.write_line.predict import BatterySettings, Predictions, predict
from warrant.write_line.judging import judge_request, reading_orders_for, slot_order
from warrant.write_line.predict import record as predictions_record
from warrant.write_line.stores import compose, store_record, variant_of
from warrant.write_line.warrants import slot_warrants

REPO = Path(__file__).resolve().parents[2]
# The pilot's answers give the mean tokens per answer the first-pass estimate uses (#54).
PILOT_RESULTS = REPO / "results" / "pilot" / "2026-10-20-e33ac97.jsonl"


@dataclass(frozen=True)
class GoldAnswer:
    question_id: str
    sql: str
    columns: tuple[str, ...]
    rows: list[tuple]


@dataclass(frozen=True)
class ResultRow:
    question_id: str
    rule: str
    run: int
    response_class: str
    final_sql: str | None
    executed: list[tuple] | None
    usage: Usage
    failure: str = ""
    bucket: Bucket | None = None
    executed_columns: tuple[str, ...] | None = None
    # What the response said, beside its final SQL: the stated value; the answer's self-reported
    # confidence, not the slot confidence the confidence rule ranks by (#51); for a refusal, what it
    # says is missing and what it offers instead; and a clarification request's question. None or
    # empty for a failed call.
    value: Any = None
    confidence: float | None = None
    missing: str = ""
    alternative: str = ""
    clarification: str = ""


@dataclass(frozen=True)
class WriteLineResult:
    rows: list[ResultRow]
    accuracy: dict[str, float | None]
    # Per rule, how many responses fell in each response class, clarification requests and
    # failures included.
    counts: dict[str, Counter[str]]
    # Per question and rule, whether its scored runs do not all share one response class; None
    # when fewer than two runs were scored.
    flips: dict[tuple[str, str], bool | None]
    gold: dict[str, GoldAnswer]
    stores: dict[str, dict[str, KnowledgeStore]]  # per rule, each database's store
    injected: dict[str, Path]
    # Per defect, what its transformation did to the injected copy (#35).
    audits: dict[str, Audit]
    # The predicted outcomes (#37), when a defect has a reading set.
    predictions: Predictions | None = None
    # The run's id, a fresh one or the one resumed (#54).
    run_id: str = ""


class RunStopped(Exception):
    """The run stopped on purpose before its end: before a call that could pass the spending cap, or at
    the pause after a first pass that cost more than twice its estimate (#54). Its records are kept;
    resume it under its run id."""

    def __init__(self, message: str, run_id: str):
        super().__init__(message)
        self.run_id = run_id


# SIGTERM and SIGHUP (a closed terminal, a dropped SSH session) would end the process with no
# exception, losing the tokens of the answer in progress, so the command turns them into an interrupt
# the run records. `_signalled` keeps the signals received: the sqlite3 module swallows an exception
# raised in its authorizer callback, and later signals are ignored, so the run also checks it before
# each answer, after each tool call and once each answer is scored.
SIGNALS = (signal.SIGTERM, signal.SIGHUP)
_signalled: list[str] = []


def _interrupt(signum, frame):
    for other in SIGNALS:  # a second signal, such as uv's forward of the first, would cut the records short
        if signal.getsignal(other) is _interrupt:
            signal.signal(other, signal.SIG_IGN)
    _signalled.append(signal.Signals(signum).name)
    raise KeyboardInterrupt(_signalled[-1])


def _stop_if_signalled() -> None:
    if _signalled:
        raise KeyboardInterrupt(_signalled[-1])


def _checked(tool: Tool) -> Tool:
    """The tool, stopping the answer once a call returns after a signal the sqlite3 module swallowed."""
    def call(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        finally:
            _stop_if_signalled()
    return call


def _record(row: ResultRow, run_id: str = "") -> dict:
    return {
        "record": "answer",
        "run_id": run_id,
        "question_id": row.question_id,
        "rule": row.rule,
        "run": row.run,
        "response_class": row.response_class,
        "bucket": row.bucket,
        "final_sql": row.final_sql,
        # The executed result is stored with its score, so each answer's value can be audited, and its
        # score recomputed from the gold answer, without re-executing its final SQL (#49).
        "executed": row.executed,
        "executed_columns": row.executed_columns,
        "value": row.value,
        "confidence": row.confidence,
        "missing": row.missing,
        "alternative": row.alternative,
        "clarification": row.clarification,
        "input_tokens": row.usage.input_tokens,
        "output_tokens": row.usage.output_tokens,
        "failure": row.failure,
    }


# A probe's answers under the readings it separates differ from its gold answer by more than this
# share, or are different sets (#34, round 2).
SEPARATION = 0.02


def _unseparated(q: Question, defect: Defect | None, injected: Path, gold: GoldAnswer) -> list[str]:
    """Why a probe of a defect with a reading set does not separate the readings it names."""
    if defect is None or not defect.readings:
        return []
    if not q.separates:
        return [f"{q.id} (a probe of {defect.id}, which has a reading set, names no reading it separates)"]
    readings = {r["id"]: r for r in defect.readings}
    expected = Result(gold.columns, gold.rows)
    found = []
    for reading, sql in q.separates:
        if reading not in readings:
            found.append(f"{q.id} ({reading!r} is not a reading of {defect.id})")
        elif readings[reading].get("is_true"):
            found.append(f"{q.id} ({reading!r} is the true reading)")
        else:
            try:
                answer = Result(*query_with_columns(injected, sql))
            except sqlite3.Error as error:
                found.append(f"{q.id} (its SQL for reading {reading!r} fails: {error})")
                continue
            if results_match(answer, expected, key=q.key, tolerance=SEPARATION):
                found.append(f"{q.id} (its answer is within 2 percent of the gold answer under reading {reading!r})")
    return found


def _rejected(config: Config, gold: dict[str, GoldAnswer], injected: dict[str, Path]) -> list[str]:
    """Each question the run could not score as configured, and why; checked before any agent call."""
    defects = {d.id: d for d in config.defects}
    rejected = []
    for q in config.questions:
        if q.id not in gold:  # its correct response is a refusal
            continue
        g = gold[q.id]
        if q.defect is None and Counter(query(config.databases[q.database], q.gold_sql)) != Counter(g.rows):
            rejected.append(f"{q.id} (a control question whose gold answer differs between clean and injected copy)")
        # A set answer is compared on its key values, so it needs a key its gold result has.
        if len(g.rows) > 1 and not q.key:
            rejected.append(f"{q.id} (a set answer with no key)")
        columns = {column.casefold() for column in g.columns}
        if any(column.casefold() not in columns for column in q.key):
            rejected.append(f"{q.id} (a key column its gold result does not have)")
        rejected += _unseparated(q, defects.get(q.defect), injected[q.database], g)
    return rejected


def _same_as_recorded(built: Built, record: dict) -> None:
    """Refuse databases that are not the recorded injection's: the builder is deterministic, so a
    rebuild on any machine gives the recorded content hashes, and a run on other databases is not a
    run on the injected copy (#49)."""
    differ = [
        f"the injected copy of {name!r}"
        for name in sorted(built.injected.keys() | record["injected"].keys())
        if built.injected.get(name) != record["injected"].get(name)
    ]
    readings = {(d, r) for d, rs in built.readings.items() for r in rs} | {
        (d, r) for d, rs in record["readings"].items() for r in rs
    }
    differ += [
        f"reading {r!r} of {d!r}"
        for d, r in sorted(readings)
        if built.readings.get(d, {}).get(r) != record["readings"].get(d, {}).get(r)
    ]
    if differ:
        raise ValueError("the databases built for this run are not the recorded injection's: " + ", ".join(differ))


def _read(path: Path | None) -> list[dict]:
    """Every record of a results file, none when there is no file."""
    if path is None or not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def _answer_prompt(record: dict) -> bool:
    """Whether the record carries the answer prompt's version (#53): a start record, an answer, or a
    call paid for while answering."""
    return record.get("record") in ("start", "answer") or (
        record.get("record") == "spent" and record.get("operation") == "answer")


def _write_claims(record: dict) -> bool:
    """Whether the record carries the write-claims prompt's version: a sample, or a call paid for while
    writing one."""
    return record.get("record") == "sample" or (
        record.get("record") == "spent" and record.get("operation") == "write_claims")


# The fields `append` adds to every record from the run's provenance.
PROVENANCE_FIELDS = ("config_hash", "repo_commit", "model", "prompt_version", "timestamp")


def _runs(records: list[dict], config_hash: str) -> tuple[list[str], set[str], set[str]]:
    """This configuration's run ids in the order they were started, the complete ones, and the ones set
    aside: started before the configuration's first complete run. The summary uses the first complete
    run in the file, so completing a run set aside would change which run it uses."""
    started = list(dict.fromkeys(
        r["run_id"] for r in records if r.get("record") == "start" and r.get("config_hash") == config_hash))
    complete = {r["run_id"] for r in records if r.get("record") == "complete"}
    first = next((run_id for run_id in started if run_id in complete), None)
    set_aside = set() if first is None else {run_id for run_id in started[:started.index(first)] if run_id not in complete}
    return started, complete, set_aside


def _earlier_records(results: Path | None, provenance: Provenance | None, run_id: str, config: Config) -> list[dict]:
    """The stored records of the run being resumed, refused unless the run is incomplete, was not set
    aside for a run of its configuration that has since completed, and was made with this
    configuration, these answer, write-claims and judge prompts, and these rules and runs."""
    if results is None or provenance is None or not Path(results).exists():
        raise ValueError(f"no run {run_id} to resume: no results file")
    stored = _read(results)
    mine = [r for r in stored if r.get("run_id") == run_id]
    if not mine:
        raise ValueError(f"no run {run_id} in {results}")
    if any(r.get("record") == "complete" for r in mine):
        raise ValueError(f"run {run_id} is complete; there is nothing to resume")
    if any(r.get("config_hash") != provenance.config_hash for r in mine):
        raise ValueError(f"run {run_id} was made with another configuration; a run is resumed with its own")
    if run_id in _runs(stored, provenance.config_hash)[2]:
        raise ValueError(f"run {run_id} was set aside: a run of its configuration completed after it started, "
                         "and the summary uses the first complete run")
    if any(r.get("prompt_version") != provenance.prompt_version for r in mine if _answer_prompt(r)):
        raise ValueError(f"run {run_id} was made with another answer prompt version; a run is resumed with its own")
    if any(r.get("prompt_version") != WRITE_CLAIMS_PROMPT_VERSION for r in mine if _write_claims(r)):
        raise ValueError(f"run {run_id} was made with another write-claims prompt version; a run is resumed with its own")
    if any(r.get("prompt_version") != JUDGE_PROMPT_VERSION for r in mine if r.get("record") == "judgement"):
        raise ValueError(f"run {run_id} was made with another judge prompt version; a run is resumed with its own")
    start = next(r for r in mine if r.get("record") == "start")
    if (start["rules"], start["runs"]) != (list(config.rules), config.runs):
        raise ValueError(f"run {run_id} was started with other rules or runs; a run is resumed with its own")
    return mine


def _scored(q: Question, rule: str, run_index: int, output, path: Path, expected: Result | None,
            tolerance: float, refusal_check: RefusalCheck) -> ResultRow:
    """The result row of one answer, its final SQL re-executed on the injected copy and scored."""
    response = output.response
    executed = (
        execute(path, response.final_sql)
        if response is not None and response.kind == ResponseKind.ANSWER
        else None
    )
    # A failed call is recorded, not scored: it is neither a correct nor a wrong answer, and it
    # stays out of the accuracy.
    scored = (
        Score(ResponseClass.FAILED)
        if output.failure
        else score(
            response,
            executed,
            expected,
            key=q.key,
            missing_terms=q.missing_terms,
            tolerance=tolerance,
            refusal_check=refusal_check,
        )
    )
    return ResultRow(
        question_id=q.id,
        rule=rule,
        run=run_index,
        response_class=scored.response_class,
        final_sql=None if response is None else response.final_sql,
        executed=None if executed is None else executed.rows,
        usage=output.usage,
        failure=output.failure,
        bucket=scored.bucket,
        executed_columns=None if executed is None else executed.columns,
        value=None if response is None else response.value,
        confidence=None if response is None else response.confidence,
        missing="" if response is None else response.missing,
        alternative="" if response is None else response.alternative,
        clarification="" if response is None else response.clarification,
    )


def run(
    config: Config,
    agent: Agent,
    work_dir: Path,
    provenance: Provenance | None = None,
    results: Path | None = None,
    *,
    tolerance: float | None = None,
    refusal_check: RefusalCheck = rule_based_refusal_check,
    stop_after_prediction: bool = False,
    run_id: str | None = None,
    spend: Spend | None = None,
    first_pass_estimate: float | None = None,
    approve_first_pass: bool = False,
    committed_predictions: Mapping | None = None,
    claim_writer: ClaimWritingModel | None = None,
    judge_model: JudgeModel | None = None,
) -> WriteLineResult:
    """Ask every question under every rule `config.runs` times and score the responses.

    Without a `tolerance`, answers are scored with the global part's numeric_tolerance when the
    configuration has one, else the scorer's default; the refusal check is the frozen rule's. When the
    configuration names an injection record, the databases built here must be that injection's, copy
    for copy by content hash, or the run stops before any agent call. When a defect has a reading
    set, the predicted outcomes are computed first, from the global part's battery settings, and with
    `stop_after_prediction` the run returns them before any agent call.

    Every stored record carries the run's id and its type (#53): a start record; sample 1 of each
    prompt variant the rules read, on every database, written by `claim_writer`, a failed one stopping
    the run so that a resume draws it again; samples 2 to 10 of each variant a confidence rule ranks;
    given a `judge_model`, one judgement record per claim on a slot in every sample; one store record
    per rule, the confidence rule's with its scores and ranking; one answer record per (question,
    rule, run); and a complete record once every answer is stored. Each question is given its rule's store on its own database. A call paid for whose result
    is not stored, because the run stopped during it, leaves a spent record with its tokens. Every
    record of a model call carries its wall time, and the start record the battery's on each
    database's injected copy. Given a `run_id`, the run resumes that run from `results`: it makes only
    the calls still missing, reuses its samples, recomposes its stores and refuses them if they differ
    from the stored ones, and refuses a complete run, one set aside for a run that has since
    completed, and one made with another configuration, answer, write-claims or judge prompt, rules
    or runs.
    Given a `spend`, which the caller builds from every record already paid for
    (`Spend.from_records`), it stops before a call that could take the spend past its cap. Given a
    `first_pass_estimate`, it pauses after run 0 when that pass's answers cost more than twice the
    estimate, unless the lead approves it with `approve_first_pass` when resuming a run whose first
    pass is stored, an approval the start record keeps for later resumes (#54). A stop raises
    RunStopped and keeps every record; any other error raised once the run has started carries a
    note naming the run id to resume. Given the `committed_predictions`, the recomputed predictions
    must equal them slot by slot, or the run stops before any agent call, since the stores are
    composed from the predictions that fixed k.
    """
    if first_pass_estimate is not None and spend is None:
        raise ValueError("the first-pass check needs the run's spend, for its prices")
    variants = list(dict.fromkeys(v for v in map(variant_of, config.rules) if v is not None))
    # The variants a confidence rule ranks, whose samples 2 to 10 are written and judged too (#51).
    ranked = [v for v in variants if any(variant_of(r) == v and r.removesuffix("_abstain") == "confidence"
                                         for r in config.rules)]
    if variants and claim_writer is None:
        raise ValueError(f"the rules {', '.join(r for r in config.rules if variant_of(r))} need a claim writer")
    if ranked and judge_model is None:
        raise ValueError("the confidence rules rank the judge's profiles, so they need a judge model")
    # Read before any call, so that a configuration that cannot rank or judge stops before it pays.
    combination = CombinationRule.from_freeze(config.global_part) if ranked else None
    method = JudgeMethod.from_freeze(config.global_part) if judge_model is not None else None
    if tolerance is None:
        tolerance = (config.global_part or {}).get("numeric_tolerance", TOLERANCE)
    built = build(list(config.defects), config.databases, work_dir)
    if config.injection is not None:
        _same_as_recorded(built, config.injection)
    injected = {name: built.copy(content) for name, content in built.injected.items()}
    audits = {a.defect: a for a in built.audits}
    predictions = None
    if any(d.readings for d in config.defects):
        if config.global_part is None:
            raise ValueError("defects with reading sets need the global part's battery settings to predict")
        settings = BatterySettings.from_freeze({"global": config.global_part})
        predictions = predict(config.defects, built, config.databases, settings, work_dir / "battery")
        computed = predictions_record(predictions, settings, {}, "")
        if committed_predictions is not None:
            problems = predictions_differ(computed, committed_predictions)
            if problems:
                raise ValueError("the recomputed predictions differ from the committed ones: " + "; ".join(problems))
    if stop_after_prediction:
        if predictions is None:
            raise ValueError("no defect has a reading set, so there is nothing to predict")
        return WriteLineResult([], {}, {}, {}, {}, {}, injected, audits, predictions)
    # A question whose correct response is a refusal has no gold answer.
    gold = {
        q.id: GoldAnswer(q.id, q.gold_sql, *query_with_columns(injected[q.database], q.gold_sql))
        for q in config.questions
        if q.gold_sql is not None
    }
    rejected = _rejected(config, gold, injected)
    if rejected:
        raise ValueError("questions the run cannot score: " + "; ".join(rejected))
    expected = {question_id: Result(g.columns, g.rows) for question_id, g in gold.items()}
    if variants and predictions is None:
        raise ValueError("the rules that read claim-writing samples need the predicted outcomes, "
                         "but no defect has a reading set")
    warrants = slot_warrants(config.defects, computed) if predictions is not None else {}
    # The baseline battery's output on each database's injected copy, the one the claim writer sees, and
    # its wall time: the true reading's database is the injected copy, so prediction ran it already.
    battery = {name: predictions.outputs[content] for name, content in built.injected.items()
               if predictions is not None and content in predictions.outputs}
    battery_s = {name: predictions.seconds[content] for name, content in built.injected.items()
                 if predictions is not None and content in predictions.seconds}
    if variants and (missing := [name for name in config.databases if name not in battery]):
        raise ValueError(f"no baseline battery output on the injected copy of {', '.join(missing)}")
    attempts = config.model.attempts if config.model is not None else ModelConfig.attempts

    keep = results is not None and provenance is not None
    earlier: list[dict] = []
    if run_id is not None:
        earlier = _earlier_records(results, provenance, run_id, config)
    else:
        run_id = uuid.uuid4().hex
    stored = list(earlier)  # the run's records, a resumed run's earlier ones included

    def write(record: dict) -> None:
        stored.append(record)
        if keep:
            append(results, provenance, record)

    done = {(r["question_id"], r["rule"], r["run"]) for r in earlier if r.get("record") == "answer"}
    # The lead approves a first pass whose cost has been seen: one whose every answer is stored.
    if approve_first_pass and not all((q.id, rule, 0) in done for rule in config.rules for q in config.questions):
        raise ValueError("there is no first pass to approve yet: the approval resumes a run paused after its "
                         "complete first pass")
    approved = approve_first_pass or any(r.get("first_pass_approved") for r in earlier if r.get("record") == "start")
    write({"record": "start", "run_id": run_id, "rules": list(config.rules), "runs": config.runs,
           "resumed": bool(earlier), "first_pass_approved": approved, "battery_s": battery_s})

    def check_the_cap() -> None:
        if spend is not None and not spend.allows_another_call():
            raise RunStopped(
                f"stopped before a call that could take the spend past the ${spend.cap:.2f} cap "
                f"(${spend.total:.2f} spent so far); raising the cap is the lead's decision (#54)", run_id)

    def spent(usage: Usage, started: float, error: BaseException, **fields) -> None:
        """Record the tokens of a call paid for whose result is not stored, so the cap counts them."""
        if usage.input_tokens or usage.output_tokens:
            if spend is not None:
                spend.add(usage.input_tokens, usage.output_tokens)
            write({"record": "spent", "run_id": run_id, **fields, "input_tokens": usage.input_tokens,
                   "output_tokens": usage.output_tokens, "error": f"{type(error).__name__}: {error}",
                   "duration_s": time.monotonic() - started})

    rows = []
    try:
        def draw(variant: str, database: str, number: int) -> dict:
            """Write one claim-writing sample, recorded as it returns."""
            _stop_if_signalled()
            check_the_cap()
            request = WriteClaimsRequest(database, schema(injected[database]), battery[database].decode(),
                                         config.business_terms.get(database, BusinessTerms((), ())))
            started = time.monotonic()
            try:
                output = write_claims(claim_writer, request, attempts, variant=variant)
            except BaseException as error:
                partial = getattr(error, "partial", None)
                spent(partial.usage if partial is not None else Usage(), started, error,
                      operation="write_claims", variant=variant, database=database, sample=number,
                      prompt_version=WRITE_CLAIMS_PROMPT_VERSION)
                raise
            if spend is not None:
                spend.add(output.usage.input_tokens, output.usage.output_tokens)
            record = {"record": "sample", "run_id": run_id, "database": database, "sample": number, **output.record(),
                      "prompt_version": WRITE_CLAIMS_PROMPT_VERSION, "duration_s": time.monotonic() - started}
            write(record)
            return record

        # Claim writing (#50, #51): sample 1 of each variant the rules read, on every database, then
        # samples 2 to 10 of each variant a confidence rule ranks. A resumed run reuses the samples it
        # has, since a sample drawn again would be another claim set. A failed sample 1 has no claim set
        # to keep: it stops the run before the stores, and a resume draws it again, its record kept, so
        # the run uses each database's first sample 1 without a failure (decided by the lead on
        # 2026-10-22). A failed later sample counts as having no claim, which the freeze counts as
        # disagreeing, and is not drawn again.
        samples: dict[tuple[str, str, int], dict] = {}
        for r in earlier:
            if r.get("record") == "sample" and (r["sample"] > 1 or not r.get("failure")):
                samples.setdefault((r["variant"], r["database"], r["sample"]), r)
        for variant in variants:
            for database in config.databases:
                if (variant, database, 1) not in samples:
                    record = draw(variant, database, 1)
                    if record["failure"]:
                        raise RunStopped(f"sample 1 of {database} under the {variant} variant failed after its "
                                         f"attempts ({record['failure']}); resume the run to draw it again", run_id)
                    samples[(variant, database, 1)] = record
        last = combination.samples if combination is not None else 1
        for variant in ranked:
            for database in config.databases:
                for number in range(2, last + 1):
                    if (variant, database, number) not in samples:
                        samples[(variant, database, number)] = draw(variant, database, number)

        # Judging (#51, #120): every claim on a slot in every sample, sample 1's first, each in its slot's
        # reading order, before the stores. Each variant's samples have their own judgements (ADR 0012):
        # within a variant, a claim string already judged on its slot agrees without a call, across
        # invocations too. A judgement cut short by an error keeps its paid answers and is judged again
        # on resume, since a claim's judgement is its first complete one (#53).
        if method is not None:
            orders = reading_orders_for(config)
            judged = {(r["variant"], r["defect"], r["sample"], r["index"])
                      for r in earlier if r.get("record") == "judgement" and r.get("complete")}
            labelled = {(r["variant"], r["defect"], r["claim"]): r for r in earlier
                        if r.get("record") == "judgement" and r.get("complete") and not r.get("without_a_call")}
            for variant in variants:
                judge = Judge(judge_model, method)  # its own cache of judged strings, this variant's only
                for database in config.databases:
                    for number in range(1, (last if variant in ranked else 1) + 1):
                        sample = samples[(variant, database, number)]
                        if sample.get("failure"):
                            continue
                        for d in sorted((d for d in config.defects if d.database == database and d.readings),
                                        key=slot_order):
                            index = slot_claim_index(sample, d)
                            if index is None or (variant, d.id, number, index) in judged:
                                continue
                            request = judge_request(d, sample["claims"][index]["statement"], orders[d.id])
                            fields = {"record": "judgement", "run_id": run_id, "defect": d.id, "variant": variant,
                                      "sample": number, "index": index}
                            if (variant, d.id, request.claim) in labelled:
                                first = labelled[(variant, d.id, request.claim)]
                                write({**fields, "complete": True, "error": "", "slot": first["slot"],
                                       "claim": request.claim, "reading_order": first["reading_order"],
                                       "labels": first["labels"], "valid": [], "answers": [], "resent": 0, "splits": [],
                                       "without_a_call": True, "input_tokens": 0, "output_tokens": 0,
                                       "method": first["method"], "prompt_version": JUDGE_PROMPT_VERSION,
                                       "duration_s": 0.0})
                                continue
                            _stop_if_signalled()
                            check_the_cap()
                            started = time.monotonic()
                            try:
                                judgement = judge.judge(request)
                            except BaseException as error:
                                if judge.interrupted is not None:
                                    usage = judge.interrupted.usage
                                    if spend is not None:
                                        spend.add(usage.input_tokens, usage.output_tokens)
                                    write({**fields, "complete": False, "error": f"{type(error).__name__}: {error}",
                                           **judge.interrupted.record(), "prompt_version": JUDGE_PROMPT_VERSION,
                                           "duration_s": time.monotonic() - started})
                                raise
                            if spend is not None:
                                spend.add(judgement.usage.input_tokens, judgement.usage.output_tokens)
                            record = {**fields, "complete": True, "error": "", **judgement.record(),
                                      "prompt_version": JUDGE_PROMPT_VERSION, "duration_s": time.monotonic() - started}
                            write(record)
                            labelled[(variant, d.id, request.claim)] = record

        # The confidence rule's allocation, per ranked variant: its k least confident slots go to a
        # person, k being the settlement rule's ask count in the committed predictions (#51).
        ranks = {}
        for variant in ranked:
            # The samples the run uses (a redrawn sample 1's failed record left out) and the judgements.
            view = ([r for (v, _, _), r in samples.items() if v == variant]
                    + [r for r in stored if r.get("record") == "judgement" and r.get("variant") == variant])
            found = scores(view, config.defects, combination)
            order = ranking(found, config.defects, combination)
            ranks[variant] = (found, order, allocation(order, settlement_ask_count(computed),
                                                       with_sample_one_claim(view, config.defects)))

        # The stores, one per rule and database, each recorded once per run, before the first answer.
        composed = {rule: {database: compose(rule, database, config.defects, warrants,
                                             samples.get((variant_of(rule), database, 1)),
                                             ranks[variant_of(rule)][2] if rule.removesuffix("_abstain") == "confidence"
                                             else None)
                           for database in config.databases}
                    for rule in config.rules}
        recorded = {r["rule"]: {k: v for k, v in r.items() if k not in PROVENANCE_FIELDS}
                    for r in earlier if r.get("record") == "store"}
        for rule in config.rules:
            extra = {}
            if rule.removesuffix("_abstain") == "confidence":
                extra = {"scores": ranks[variant_of(rule)][0], "ranking": ranks[variant_of(rule)][1]}
            record = {**store_record(rule, composed[rule], config.defects, **extra), "run_id": run_id}
            if rule not in recorded:
                write(record)
            elif recorded[rule] != record:
                raise ValueError(f"the {rule} stores composed now differ from the stored ones of run {run_id}")
        stores = {rule: {database: c.store for database, c in by_database.items()} for rule, by_database in composed.items()}

        for run_index in range(config.runs):
            if run_index == 1 and first_pass_estimate is not None and not approved:
                actual = first_pass_cost(stored, spend.prices)
                if over_estimate(actual, first_pass_estimate):
                    raise RunStopped(
                        f"the first pass cost ${actual:.2f}, more than twice its estimate of ${first_pass_estimate:.2f}; "
                        "the run pauses for the lead and goes on when resumed with the first pass approved", run_id)
            for rule in config.rules:
                for q in config.questions:
                    if (q.id, rule, run_index) in done:
                        continue
                    check_the_cap()
                    path = injected[q.database]
                    request = AnswerRequest(
                        database=q.database,
                        question_id=q.id,
                        question=q.text,
                        run=run_index,
                        schema=schema(path),
                        store=stores[rule][q.database],
                        tools=(ReadOnlySQL.name,),
                    )
                    output = None
                    started = time.monotonic()
                    try:
                        _stop_if_signalled()
                        output = agent.answer(request, {ReadOnlySQL.name: _checked(ReadOnlySQL(path))})
                        duration = time.monotonic() - started  # the agent's own SQL queries included
                        row = _scored(q, rule, run_index, output, path, expected.get(q.id), tolerance, refusal_check)
                        _stop_if_signalled()  # an interrupt swallowed while scoring, perhaps changing the score
                    except BaseException as error:
                        # The call was paid for although its answer is not stored: its tokens are
                        # recorded, and the answer stays missing, so a resume asks again.
                        spent(output.usage if output is not None else getattr(error, "usage", Usage()), started, error,
                              operation="answer", question_id=q.id, rule=rule, run=run_index)
                        raise
                    if spend is not None:
                        spend.add(output.usage.input_tokens, output.usage.output_tokens)
                    rows.append(row)
                    write({**_record(row, run_id), "duration_s": duration})
        write({"record": "complete", "run_id": run_id,
               "answers": sum(r.get("record") == "answer" for r in stored)})
    except BaseException as error:
        if keep and not isinstance(error, RunStopped):
            error.add_note(f"run {run_id} stopped with its records kept: resume it with --run-id {run_id}")
        raise

    by_rule = {rule: [r for r in rows if r.rule == rule] for rule in config.rules}
    return WriteLineResult(
        rows=rows,
        accuracy={rule: accuracy(r.response_class for r in by_rule[rule]) for rule in config.rules},
        counts={rule: Counter(r.response_class for r in by_rule[rule]) for rule in config.rules},
        flips={
            (q.id, rule): flips(r.response_class for r in by_rule[rule] if r.question_id == q.id)
            for q in config.questions
            for rule in config.rules
        },
        gold=gold,
        stores=stores,
        injected=injected,
        audits=audits,
        predictions=predictions,
        run_id=run_id,
    )


def check(config: Config, work_dir: Path) -> int:
    """Print each question's gold answer, a control's gold answer on the clean copy too, and each
    probe's answers under the readings it separates, then every problem the run would stop on; no
    agent is called."""
    built = build(list(config.defects), config.databases, work_dir)
    if config.injection is not None:
        _same_as_recorded(built, config.injection)
    injected = {name: built.copy(content) for name, content in built.injected.items()}
    gold = {}
    for q in config.questions:
        if q.gold_sql is None:
            print(f"{q.id}: a refusal question")
            continue
        gold[q.id] = GoldAnswer(q.id, q.gold_sql, *query_with_columns(injected[q.database], q.gold_sql))
        print(f"{q.id}: gold: {gold[q.id].rows}")
        if q.defect is None:  # a control's gold answer must be the same on the clean copy
            print(f"  clean copy: {query(config.databases[q.database], q.gold_sql)}")
        for reading, sql in q.separates:
            try:
                print(f"  {reading}: {query_with_columns(injected[q.database], sql)[1]}")
            except sqlite3.Error as error:
                print(f"  {reading}: fails ({error})")
    problems = _rejected(config, gold, injected)
    for problem in problems:
        print(f"problem: {problem}")
    print(f"{len(problems)} problems")
    return 1 if problems else 0


def committed_predictions_for(config: Config, directory: Path = REPO / "predictions") -> dict | None:
    """The committed predictions of the configuration's injection record (#37), found by the record's
    SHA-256, which they name; None when the configuration names no injection record or no defect has
    a reading set, so nothing is predicted. Refused when none or several match: the stores are
    composed from the committed predictions, so a run may not go on without them."""
    if config.injection_sha256 is None or not any(d.readings for d in config.defects):
        return None
    found = [json.loads(path.read_text()) for path in sorted(Path(directory).glob("*.json"))]
    found = [p for p in found if p.get("injection_record_sha256") == config.injection_sha256]
    if len(found) != 1:
        raise ValueError(f"{len(found) or 'no'} committed predictions name this injection record in {directory}")
    return found[0]


def _claim_writing_problems(config: Config, judge_validation: Path) -> list[str]:
    """Why the run may not make its first claim-writing call (#54, `global.judge.validation`): the
    judge's validation must be complete, with this run's judge method and model."""
    try:
        method = JudgeMethod.from_freeze(config.global_part or {})
    except (KeyError, ValueError) as error:
        return [f"the configuration's judge method: {error!r}"]
    return validation_problems(judge_validation, method.record(), config.model.model)


def main(argv=None) -> int:
    """Run one configuration against the configured model: `python -m warrant.write_line.run`."""
    parser = argparse.ArgumentParser(description="Run the write line against the configured model.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path, default=data_dir() / "write_line")
    parser.add_argument("--results", type=Path, default=data_dir() / "results.jsonl")
    parser.add_argument("--check", action="store_true",
                        help="check the questions and print their answers, with no agent call")
    parser.add_argument("--judge-validation", type=Path, default=data_dir() / "judge_validation.jsonl",
                        help="the judge validation's records, whose spend the cap also covers")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--run-id", help="resume this run from the results file, making only the calls still missing")
    which.add_argument("--new-run", action="store_true",
                       help="start a new run although a run of this configuration in the results file is incomplete")
    parser.add_argument("--approve-first-pass", action="store_true",
                        help="go on past the pause after a first pass that cost more than twice its estimate")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.check:
        return check(config, args.work_dir)
    if config.model is None:
        parser.error(f"{args.config} names no model block")
    provenance = provenance_for(args.config, config.model)
    stored = _read(args.results)
    started, complete, set_aside = _runs(stored, provenance.config_hash)
    if args.run_id is None and not args.new_run and started:
        # Another run is paid for again in full, so it is started only on purpose.
        incomplete = [run_id for run_id in started if run_id not in complete and run_id not in set_aside]
        if incomplete:
            parser.error(f"run {incomplete[-1]} of this configuration in {args.results} is incomplete: resume it "
                         f"with --run-id {incomplete[-1]}, or start another with --new-run")
        parser.error(f"this configuration already has a complete run in {args.results}; "
                     "start another only on purpose, with --new-run")
    try:
        agent = ClaudeAgent(config.model)
        claim_writer = ClaudeClaimWriter(config.model) if any(map(variant_of, config.rules)) else None
        judge_model = ClaudeJudge(config.model) if claim_writer is not None else None
        # The cap covers every call already paid for: every run in the results file, a repeated run
        # included, and the judge validation (#54).
        spend = Spend.from_records(stored + _read(args.judge_validation), prices_for(config.model.model))
        committed = committed_predictions_for(config)
    except ValueError as error:
        parser.error(f"{args.config}: {error}")  # a misconfiguration, before any question is asked
    if claim_writer is not None and (problems := _claim_writing_problems(config, args.judge_validation)):
        parser.error("no claim is written before the judge's validation clears it: " + "; ".join(problems))
    mean_input, mean_output = mean_tokens(json.loads(line) for line in PILOT_RESULTS.read_text().splitlines())
    estimate = answer_estimate(len(config.questions) * len(config.rules), mean_input, mean_output, spend.prices)
    # A signal already ignored, as nohup ignores SIGHUP, stays ignored.
    _signalled.clear()
    handlers = {signum: signal.signal(signum, _interrupt) for signum in SIGNALS
                if signal.getsignal(signum) is not signal.SIG_IGN}
    try:
        result = run(
            config,
            agent,
            args.work_dir,
            provenance,
            args.results,
            run_id=args.run_id,
            spend=spend,
            first_pass_estimate=estimate,
            approve_first_pass=args.approve_first_pass,
            committed_predictions=committed,
            claim_writer=claim_writer,
            judge_model=judge_model,
        )
    except RunStopped as stop:
        print(f"run {stop.run_id} stopped: {stop}")
        print(f"  resume it with --run-id {stop.run_id}"
              + (" --approve-first-pass once the lead approves the first pass" if "first pass" in str(stop) else ""))
        return 3
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        _signalled.clear()
    failed = sum(row.response_class == ResponseClass.FAILED for row in result.rows)
    print(f"run {result.run_id} complete: {len(result.rows)} results this invocation, {failed} failed calls, "
          f"${spend.total:.2f} spent in all, written to {args.results}")
    for rule, rule_accuracy in result.accuracy.items():  # over this invocation's results
        counts = result.counts[rule]
        print(
            f"  {rule}: {'no counted response' if rule_accuracy is None else f'{rule_accuracy:.3f}'}, "
            f"{counts[ResponseClass.CLARIFICATION_REQUEST]} clarification requests, "
            f"{counts[ResponseClass.FAILED]} failed calls"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
