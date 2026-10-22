"""The write-line entry point: build the reading databases, predict, compute gold answers, compose
stores, ask the agent, score. With `stop_after_prediction` it returns before any agent call (#37).

The tracer bullet (#27) supports two allocation rules, the empty store and everything from a
person; #50 and #51 add the others.
"""

import argparse
import json
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from warrant.agent.claude import ClaudeAgent
from warrant.agent.interface import Agent, AnswerRequest, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
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
from warrant.store.claims import Claim, KnowledgeStore, Source, Toulmin, WarrantKind
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.config import Config, Question, load_config
from warrant.write_line.guards import (
    Spend,
    answer_estimate,
    first_pass_cost,
    mean_tokens,
    over_estimate,
    predictions_differ,
    prices_for,
)
from warrant.write_line.predict import BatterySettings, Predictions, predict
from warrant.write_line.predict import record as predictions_record

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
    stores: dict[str, KnowledgeStore]
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


def _person_claim(defect: Defect) -> Claim:
    # No battery runs yet, so the warrant kind is a placeholder until #50 computes it.
    return Claim(
        slot=defect.slot,
        statement=defect.reference_claim,
        source=Source.PERSON,
        warrant=WarrantKind.NONE,
        toulmin=Toulmin(backing="the person"),
    )


def compose(rule: str, defects: tuple[Defect, ...]) -> KnowledgeStore:
    if rule == "empty":
        return KnowledgeStore()
    if rule == "all_person":
        return KnowledgeStore(tuple(_person_claim(d) for d in defects))
    raise ValueError(f"unknown allocation rule: {rule!r}")


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


def _earlier_records(results: Path | None, provenance: Provenance | None, run_id: str, config: Config) -> list[dict]:
    """The stored records of the run being resumed, refused unless the run is incomplete and was made
    with this configuration, this answer prompt and these rules and runs."""
    if results is None or provenance is None or not Path(results).exists():
        raise ValueError(f"no run {run_id} to resume: no results file")
    mine = [r for r in _read(results) if r.get("run_id") == run_id]
    if not mine:
        raise ValueError(f"no run {run_id} in {results}")
    if any(r.get("record") == "complete" for r in mine):
        raise ValueError(f"run {run_id} is complete; there is nothing to resume")
    if any(r.get("config_hash") != provenance.config_hash for r in mine):
        raise ValueError(f"run {run_id} was made with another configuration; a run is resumed with its own")
    if any(r.get("prompt_version") != provenance.prompt_version for r in mine if r.get("record") == "answer"):
        raise ValueError(f"run {run_id} was made with another answer prompt version; a run is resumed with its own")
    start = next(r for r in mine if r.get("record") == "start")
    if (start["rules"], start["runs"]) != (list(config.rules), config.runs):
        raise ValueError(f"run {run_id} was started with other rules or runs; a run is resumed with its own")
    return mine


def _incomplete_runs(records: list[dict], config_hash: str) -> list[str]:
    """The run ids of this configuration's runs that were started and never completed, oldest first."""
    complete = {r["run_id"] for r in records if r.get("record") == "complete"}
    started = (r["run_id"] for r in records if r.get("record") == "start" and r.get("config_hash") == config_hash)
    return [run_id for run_id in dict.fromkeys(started) if run_id not in complete]


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
) -> WriteLineResult:
    """Ask every question under every rule `config.runs` times and score the responses.

    Without a `tolerance`, answers are scored with the global part's numeric_tolerance when the
    configuration has one, else the scorer's default; the refusal check is the frozen rule's. When the
    configuration names an injection record, the databases built here must be that injection's, copy
    for copy by content hash, or the run stops before any agent call. When a defect has a reading
    set, the predicted outcomes are computed first, from the global part's battery settings, and with
    `stop_after_prediction` the run returns them before any agent call.

    Every stored record carries the run's id and its type: a start record, one answer record per
    (question, rule, run), and a complete record once every answer is stored (#53). A call paid for
    whose answer is not stored, because the run stopped during it, leaves a spent record with its
    tokens. Given a `run_id`, the run resumes that run from `results`: it makes only the calls still
    missing, refusing a complete run and one made with another configuration, answer prompt, rules or
    runs. Given a `spend`, which the caller builds from every record already paid for
    (`Spend.from_records`), it stops before a call that could take the spend past its cap. Given a
    `first_pass_estimate`, it pauses after run 0 when that pass's answers cost more than twice the
    estimate, unless the lead approves it with `approve_first_pass`, an approval the start record
    keeps for later resumes (#54). A stop raises RunStopped and keeps every record; any other error
    raised once the run has started carries a note naming the run id to resume. Given the
    `committed_predictions`, the recomputed predictions must equal them slot by slot, or the run stops
    before any agent call, since the stores are composed from the predictions that fixed k.
    """
    if first_pass_estimate is not None and spend is None:
        raise ValueError("the first-pass check needs the run's spend, for its prices")
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
        if committed_predictions is not None:
            problems = predictions_differ(predictions_record(predictions, settings, {}, ""), committed_predictions)
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
    stores = {rule: compose(rule, config.defects) for rule in config.rules}

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
    approved = approve_first_pass or any(r.get("first_pass_approved") for r in earlier if r.get("record") == "start")
    write({"record": "start", "run_id": run_id, "rules": list(config.rules), "runs": config.runs,
           "resumed": bool(earlier), "first_pass_approved": approved})

    rows = []
    try:
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
                    if spend is not None and not spend.allows_another_call():
                        raise RunStopped(
                            f"stopped before a call that could take the spend past the ${spend.cap:.2f} cap "
                            f"(${spend.total:.2f} spent so far); raising the cap is the lead's decision (#54)", run_id)
                    path = injected[q.database]
                    request = AnswerRequest(
                        database=q.database,
                        question_id=q.id,
                        question=q.text,
                        run=run_index,
                        schema=schema(path),
                        store=stores[rule],
                        tools=(ReadOnlySQL.name,),
                    )
                    output = None
                    try:
                        output = agent.answer(request, {ReadOnlySQL.name: ReadOnlySQL(path)})
                        row = _scored(q, rule, run_index, output, path, expected.get(q.id), tolerance, refusal_check)
                    except BaseException as error:
                        # The call was paid for although its answer is not stored: its tokens are
                        # recorded, so the cap counts them, and the answer stays missing, so a resume
                        # asks again.
                        usage = output.usage if output is not None else getattr(error, "usage", Usage())
                        if usage.input_tokens or usage.output_tokens:
                            if spend is not None:
                                spend.add(usage.input_tokens, usage.output_tokens)
                            write({"record": "spent", "run_id": run_id, "operation": "answer",
                                   "question_id": q.id, "rule": rule, "run": run_index,
                                   "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                                   "error": f"{type(error).__name__}: {error}"})
                        raise
                    if spend is not None:
                        spend.add(output.usage.input_tokens, output.usage.output_tokens)
                    rows.append(row)
                    write(_record(row, run_id))
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
    incomplete = _incomplete_runs(stored, provenance.config_hash)
    if args.run_id is None and not args.new_run and incomplete:
        parser.error(f"run {incomplete[-1]} of this configuration in {args.results} is incomplete: resume it "
                     f"with --run-id {incomplete[-1]}, or start another with --new-run")
    try:
        agent = ClaudeAgent(config.model)
        # The cap covers every call already paid for: every run in the results file, a repeated run
        # included, and the judge validation (#54).
        spend = Spend.from_records(stored + _read(args.judge_validation), prices_for(config.model.model))
        committed = committed_predictions_for(config)
    except ValueError as error:
        parser.error(f"{args.config}: {error}")  # a misconfiguration, before any question is asked
    mean_input, mean_output = mean_tokens(json.loads(line) for line in PILOT_RESULTS.read_text().splitlines())
    estimate = answer_estimate(len(config.questions) * len(config.rules), mean_input, mean_output, spend.prices)
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
        )
    except RunStopped as stop:
        print(f"run {stop.run_id} stopped: {stop}")
        print(f"  resume it with --run-id {stop.run_id}"
              + (" --approve-first-pass once the lead approves the first pass" if "first pass" in str(stop) else ""))
        return 3
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
