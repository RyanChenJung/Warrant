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
"""

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from warrant.agent.claude import ClaudeJudge
from warrant.agent.judge import JUDGE_PROMPT_VERSION, Judge, Judgement, JudgeMethod, JudgeModel, Label, prompt
from warrant.config import data_dir
from warrant.defects.inject import Defect
from warrant.store.results import Provenance, append, provenance_for
from warrant.write_line.config import load_config
from warrant.write_line.judging import judge_request, reading_orders

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
    claims: list[ValidationClaim]
    judgements: list[Judgement]
    # One row per expected label: defect, role, reading, expected, judged, match.
    rows: list[dict]
    # (claim, reading) pairs with no label two valid calls share, over every reading judged.
    splits: int
    # (claim, reading) pairs whose valid calls do not all give the same label.
    unsteady_pairs: int

    @property
    def mismatches(self) -> list[dict]:
        return [row for row in self.rows if not row["match"]]


def validate(defects: tuple[Defect, ...], model: JudgeModel, method: JudgeMethod, seed: int) -> ValidationReport:
    judge = Judge(model, method)
    orders = reading_orders(defects, seed)
    by_id = {d.id: d for d in defects}
    claims = validation_claims(defects)
    judgements, rows = [], []
    for claim in claims:
        judgement = judge.judge(judge_request(by_id[claim.defect], claim.claim, orders[claim.defect]))
        judgements.append(judgement)
        for reading, expected in claim.expected.items():
            judged = judgement.labels[reading]
            rows.append({
                "defect": claim.defect, "role": claim.role, "reading": reading,
                "expected": expected.value, "judged": judged.value, "match": judged == expected,
            })
    return ValidationReport(
        claims=claims,
        judgements=judgements,
        rows=rows,
        splits=sum(len(j.splits) for j in judgements),
        unsteady_pairs=sum(
            len({call[reading] for call in j.valid}) > 1 for j in judgements for reading in j.reading_order
        ),
    )


def write_validation(report: ValidationReport, results: Path, provenance: Provenance) -> None:
    """One record per judged claim: the judgement with its method, and each comparison."""
    for claim, judgement in zip(report.claims, report.judgements):
        mine = [row for row in report.mismatches if (row["defect"], row["role"]) == (claim.defect, claim.role)]
        append(results, provenance, {
            "operation": "judge_validation",
            "defect": claim.defect,
            "role": claim.role,
            **judgement.record(),
            "expected": {reading: label.value for reading, label in claim.expected.items()},
            "mismatches": mine,
        })


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
        orders = reading_orders(config.defects, seed)
        by_id = {d.id: d for d in config.defects}
        for claim in claims:
            text, _ = prompt(method.template, judge_request(by_id[claim.defect], claim.claim, orders[claim.defect]))
            print(f"=== {claim.defect}, {claim.role}\n{text}\n")
        print(f"{len(claims)} claims to judge, {method.valid_calls} valid calls and at most {limit} calls each; "
              "no model was called (dry run)")
        return 0

    if config.model is None:
        parser.error(f"{args.config} names no model block")
    report = validate(config.defects, ClaudeJudge(config.model), method, seed)
    provenance = replace(provenance_for(args.config, config.model), prompt_version=JUDGE_PROMPT_VERSION)
    write_validation(report, args.results, provenance)
    resent = sum(j.resent for j in report.judgements)
    print(f"{len(claims)} claims judged, {resent} calls re-sent, {report.splits} splits, "
          f"{report.unsteady_pairs} (claim, reading) pairs whose calls differ; written to {args.results}")
    for row in report.mismatches:
        print(f"  mismatch: {row['defect']} {row['role']} on {row['reading']}: "
              f"expected {row['expected']}, judged {row['judged']}")
    print(f"{len(report.mismatches)} mismatches of {len(report.rows)} expected labels (reported, not fixed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
