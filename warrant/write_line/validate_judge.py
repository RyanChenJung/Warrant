"""The judge's validation (#120): `python -m warrant.write_line.validate_judge --config <run configuration>`.

Before the first claim-writing call, the judge labels every reference claim and every drift-reading
statement of the freeze, and its labels are compared with the frozen holds flags (freeze,
global.judge.validation): on a reference claim, holds true expects holds and holds false expects
fails, on every reading; a drift-reading statement is checked on two readings only, holding on its
own drift reading and failing on the true reading. not_addressed, a split included, is a mismatch
either way. Mismatches are reported, not fixed: the rubric is not changed after this runs.

The configuration names the freeze and its recorded injection (`freeze:`, `injection:`), so only
the freeze the injection was built from is judged, and its model block is the one fixed for claim
writing, which the judge uses too (configs/write_line_pilot.yaml). `--dry-run` prints every prompt
the run would send and calls no model.

Every answer is kept with its run (global.judge.runs): each record carries the run's id, a start
record opens the run, each claim's record is appended as soon as it is judged, a claim whose judging
stops on an error keeps the answers paid for so far, and a completion record closes the run. A run
repeated for any reason is reported as such, with the first complete run, which is the one used.
"""

import argparse
import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import yaml

from warrant.agent.claude import ClaudeJudge
from warrant.agent.judge import JUDGE_PROMPT_VERSION, Judge, Judgement, JudgeMethod, JudgeModel, Label, prompt
from warrant.config import data_dir
from warrant.defects.inject import Defect
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.config import load_config
from warrant.write_line.judging import judge_request, reading_orders, reading_orders_for

OPERATION = "judge_validation"

REFERENCE_CLAIM = "reference_claim"
DRIFT_READING = "drift_reading"


@dataclass(frozen=True)
class ValidationClaim:
    defect: str
    role: str  # the defect's reference claim, or its drift-reading statement
    claim: str
    expected: dict[str, Label]  # by reading id; only the readings that settle an expected label


def validation_claims(defects: tuple[Defect, ...]) -> list[ValidationClaim]:
    """Each defect's reference claim and drift-reading statement, in declared order, with the labels
    the frozen holds flags expect."""
    claims = []
    for defect in defects:
        if not defect.readings:
            continue
        flag = {True: Label.HOLDS, False: Label.FAILS}
        claims.append(ValidationClaim(
            defect.id, REFERENCE_CLAIM, defect.reference_claim.strip(),
            {r["id"]: flag[r["holds"]] for r in defect.readings},
        ))
        by_id = {r["id"]: r for r in defect.readings}
        drift = defect.drift_reading
        (true,) = [r["id"] for r in defect.readings if r.get("is_true")]
        # A meaning-only drift reading carries the reference claim a person would state under it;
        # a world-fixed one is stated by its reading statement.
        statement = drift.get("reference_claim") or by_id[drift["reading"]]["statement"]
        claims.append(ValidationClaim(
            defect.id, DRIFT_READING, statement.strip(),
            {drift["reading"]: Label.HOLDS, true: Label.FAILS},
        ))
    return claims


@dataclass(frozen=True)
class ValidationReport:
    """The comparison, and the judge's repeat instability over the judgements made with a call.

    A (claim, reading) pair counts as unsteady when its valid calls do not all give the same label,
    and a pair with fewer valid calls than the method asks for counts as unsteady too, since its calls
    cannot be shown to agree. The share is `unsteady_pairs / judged_pairs`.
    """

    claims: list[ValidationClaim]
    judgements: list[Judgement]
    # One row per expected label: defect, role, reading, expected, judged, match.
    rows: list[dict]
    # (claim, reading) pairs with no label two valid calls share.
    splits: int
    unsteady_pairs: int
    judged_pairs: int

    @property
    def mismatches(self) -> list[dict]:
        return [row for row in self.rows if not row["match"]]


def _rows(claim: ValidationClaim, judgement: Judgement) -> list[dict]:
    rows = []
    for reading, expected in claim.expected.items():
        judged = judgement.labels[reading]
        rows.append({
            "defect": claim.defect, "role": claim.role, "reading": reading,
            "expected": expected.value, "judged": judged.value, "match": judged == expected,
        })
    return rows


def _claim_record(claim: ValidationClaim, judgement: Judgement, rows: list[dict], error: str = "") -> dict:
    return {
        "record": "claim",
        "defect": claim.defect,
        "role": claim.role,
        "complete": not error,
        **judgement.record(),
        "expected": {reading: label.value for reading, label in claim.expected.items()},
        "mismatches": [row for row in rows if not row["match"]],
        "error": error,
    }


def validate(
    freeze_defects: tuple[Defect, ...],
    model: JudgeModel,
    method: JudgeMethod,
    seed: int,
    write: Callable[[dict], None] = lambda record: None,
) -> ValidationReport:
    """Judge every validation claim of the freeze, handing each claim's record to `write` as soon as
    it is judged. If judging a claim raises, its answers so far are written before the error goes
    on. `freeze_defects` is every defect of the freeze, as the reading orders need."""
    judge = Judge(model, method)
    orders = reading_orders(freeze_defects, seed)
    by_id = {d.id: d for d in freeze_defects}
    claims = validation_claims(freeze_defects)
    judgements, rows = [], []
    for claim in claims:
        try:
            judgement = judge.judge(judge_request(by_id[claim.defect], claim.claim, orders[claim.defect]))
        except BaseException as error:
            if judge.interrupted is not None:
                write(_claim_record(claim, judge.interrupted, [], error=f"{type(error).__name__}: {error}"))
            raise
        judgements.append(judgement)
        mine = _rows(claim, judgement)
        rows += mine
        write(_claim_record(claim, judgement, mine))
    called = [j for j in judgements if not j.without_a_call]
    return ValidationReport(
        claims=claims,
        judgements=judgements,
        rows=rows,
        splits=sum(len(j.splits) for j in called),
        unsteady_pairs=sum(
            len(j.valid) < method.valid_calls or len({call[reading] for call in j.valid}) > 1
            for j in called for reading in j.reading_order
        ),
        judged_pairs=sum(len(j.reading_order) for j in called),
    )


def run_validation(
    freeze_defects: tuple[Defect, ...],
    model: JudgeModel,
    method: JudgeMethod,
    seed: int,
    results: Path,
    provenance: Provenance,
    run_id: str,
) -> ValidationReport:
    """One validation run, appended to `results` as it goes: a start record, one record per claim
    and a completion record, each with the run's id."""

    def write(record: dict) -> None:
        append(results, provenance, {"operation": OPERATION, "run_id": run_id, **record})

    claims = validation_claims(freeze_defects)
    write({"record": "start", "claims": len(claims), "expected_labels": sum(len(c.expected) for c in claims)})
    report = validate(freeze_defects, model, method, seed, write)
    write({
        "record": "complete",
        "claims": len(report.claims),
        "expected_labels": len(report.rows),
        "mismatches": len(report.mismatches),
        "resent": sum(j.resent for j in report.judgements),
        "splits": report.splits,
        "unsteady_pairs": report.unsteady_pairs,
        "judged_pairs": report.judged_pairs,
    })
    return report


def expected_by_claim(defects: tuple[Defect, ...]) -> dict[tuple[str, str], tuple[dict, str, dict[str, str]]]:
    """Each validation claim of the freeze's `defects` by (defect, role): its slot, text and expected
    labels, as its record stores them. The records do not keep the reading statements, so they are
    not part of it."""
    slots = {d.id: {"claim_kind": d.slot.claim_kind.value, "subject": d.slot.subject} for d in defects}
    return {(c.defect, c.role): (slots[c.defect], c.claim, {reading: label.value for reading, label in c.expected.items()})
            for c in validation_claims(defects)}


def judged_by_claim(records: list[dict]) -> dict[tuple[str, str], tuple[dict, str, dict[str, str]]]:
    """The claims a run's records judged, in the form of `expected_by_claim`."""
    return {(r["defect"], r["role"]): (r["slot"], r["claim"], r["expected"])
            for r in records if r.get("record") == "claim"}


def earlier_runs(results: Path, defects: tuple[Defect, ...] | None = None) -> tuple[list[str], str | None]:
    """The run ids of earlier validation runs in `results`, in order, and the first complete one.

    With a freeze's `defects`, only the runs on its validation claims count (#147): the default file
    is shared, so a second freeze's validation may follow the first's in it. A run that judged a claim
    not among them was made on another freeze, and a complete run counts only if it judged exactly
    them."""
    if not results.exists():
        return [], None
    by_run: dict[str, list[dict]] = {}
    for line in results.read_text().splitlines():
        record = json.loads(line)
        if record.get("operation") == OPERATION:
            by_run.setdefault(record["run_id"], []).append(record)
    wanted = None if defects is None else expected_by_claim(defects)
    runs, first = [], None
    for run_id, records in by_run.items():
        judged = judged_by_claim(records)
        if wanted is not None and any(wanted.get(key) != value for key, value in judged.items()):
            continue
        runs.append(run_id)
        complete = any(r.get("record") == "complete" for r in records)
        if first is None and complete and (wanted is None or judged == wanted):
            first = run_id
    return runs, first


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the judge on the freeze's own claims.")
    parser.add_argument("--config", required=True, type=Path,
                        help="a run configuration naming the freeze, its injection record and the model")
    parser.add_argument("--results", type=Path, default=data_dir() / "judge_validation.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="print the prompts and call no model")
    args = parser.parse_args(argv)

    raw = yaml.safe_load(args.config.read_text())
    if not raw.get("freeze") or not raw.get("injection"):
        parser.error(f"{args.config} must name the freeze and its injection record, so that only the "
                     "freeze the injection was built from is judged")
    config = load_config(args.config)  # refuses an injection record of another freeze
    method = JudgeMethod.from_freeze(config.global_part)
    seed = config.global_part["seeds"]["judge_reading_order"]
    claims = validation_claims(config.defects)
    limit = method.valid_calls + method.extra_calls

    if args.dry_run:
        orders = reading_orders_for(config)
        by_id = {d.id: d for d in config.defects}
        for claim in claims:
            text, _ = prompt(method.template, judge_request(by_id[claim.defect], claim.claim, orders[claim.defect]))
            print(f"=== {claim.defect}, {claim.role}\n{text}\n")
        print(f"{len(claims)} claims to judge, {method.valid_calls} valid calls and at most {limit} calls each; "
              "no model was called (dry run)")
        return 0

    if config.model is None:
        parser.error(f"{args.config} names no model block")
    try:
        model = ClaudeJudge(config.model)
    except ValueError as error:
        parser.error(f"{args.config}: {error}")  # a misconfiguration, before any claim is judged

    runs, first_complete = earlier_runs(args.results, config.defects)
    if runs:
        print(f"This is a repeated run (earlier runs in {args.results}: {', '.join(runs)}); "
              + (f"the first complete run is {first_complete}, and it is the one used."
                 if first_complete else "no earlier run completed."))
    run_id = uuid.uuid4().hex
    provenance = replace(provenance_for(args.config, config.model), prompt_version=JUDGE_PROMPT_VERSION)
    report = run_validation(config.defects, model, method, seed, args.results, provenance, run_id)
    resent = sum(j.resent for j in report.judgements)
    print(f"Run {run_id}: {len(claims)} claims judged, {resent} calls re-sent, {report.splits} splits; "
          f"{report.unsteady_pairs} of {report.judged_pairs} (claim, reading) pairs whose valid calls do not "
          f"all agree; written to {args.results}")
    for row in report.mismatches:
        print(f"  mismatch: {row['defect']} {row['role']} on {row['reading']}: "
              f"expected {row['expected']}, judged {row['judged']}")
    print(f"{len(report.mismatches)} mismatches of {len(report.rows)} expected labels (reported, not fixed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
