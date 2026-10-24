"""The blind audit's sheet and its agreement with the judge (#123, `global.judge.audit`).

A teammate who did not author the defects labels every distinct agent claim on a slot of the primary
prompt variant (ADR 0012), blind. The sheet has one row per claim and reading: the claim, its slot's
kind and subject, and the reading, lettered in the slot's frozen reading order, which is what the
judge sees. It never shows the judge's labels, the true reading, the defect id or the reading ids.

The key that maps each item back to its defect, its occurrences in the claim-writing samples and
each letter's reading stays with the lead. So does the run it was built from: the first run with a
complete record, the one the freeze uses (`global.judge.runs`). Or, given with `--run-id`, a run whose
judging is done, so the audit can start before the answers (#123). Agreement is computed afterwards
from the filled sheet, the key and that run's judgement records; the judge's labels stand either
way.

    uv run python -m warrant.write_line.audit sheet --config <run config> --results <results> --sheet <csv> --key <json> [--run-id <id>]
    uv run python -m warrant.write_line.audit agreement --results <results> --sheet <filled csv> --key <json> [--auditor <name> --out <audit.jsonl>]

Neither calls a model.
"""

import argparse
import csv
import json
import re
import string
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from warrant.write_line.config import Config, load_config
from warrant.write_line.validate_judge import OPERATION as VALIDATION

FIELDS = ("item", "claim_kind", "subject", "claim", "letter", "reading", "label", "notes")
# The prompt variant the audit covers (ADR 0012): the abstain variant's claims are judged, not audited.
# A judgement record without a variant predates the two variants and is the primary one's.
AUDITED = "confident"
LABELS = ("holds", "fails", "not_addressed")
# Written with a byte-order mark, so that a spreadsheet opens the claims as UTF-8, and read without it.
ENCODING = "utf-8-sig"


class SheetError(ValueError):
    """The filled sheet does not match its key."""


@dataclass(frozen=True)
class Item:
    """One distinct agent claim on a slot, as the auditor labels it once."""

    id: str
    defect: str
    claim: str
    occurrences: tuple[tuple[int, int], ...]  # (sample, index) of every judgement with this claim
    letters: dict[str, str]  # letter -> reading id, in the slot's frozen reading order
    claim_kind: str = ""
    subject: str = ""


def used_run(records: Iterable[Mapping]) -> str:
    """The run the audit is about: the first run id, in the file's order, that has a complete record.
    The judge validation's records, which keep their own file, are left out."""
    runs, complete = [], set()
    for record in records:
        if record.get("operation") == VALIDATION or "run_id" not in record:
            continue
        if record["run_id"] not in runs:
            runs.append(record["run_id"])
        if record.get("record") == "complete":
            complete.add(record["run_id"])
    run = next((r for r in runs if r in complete), None)
    if run is None:
        raise ValueError("no run in the results has a complete record, so there is nothing to audit")
    return run


def judging_done(records: Iterable[Mapping], run: str) -> bool:
    """Whether the run's judging is done: the run records its stores only after every judgement (#53),
    so the sheet can be built then, before the answers (#123)."""
    return any(r.get("record") == "store" and r.get("run_id") == run for r in records)


def _judgements(records: Iterable[Mapping], run: str) -> list[Mapping]:
    """The run's complete judgement records of the audited variant; one that stopped on an error has no
    labels to compare."""
    return [r for r in records
            if r.get("record") == "judgement" and r.get("run_id") == run and r.get("complete")
            and r.get("variant", AUDITED) == AUDITED]


def audit_items(records: Sequence[Mapping], run: str) -> list[Item]:
    """Every distinct claim string on a slot in the run, in order of defect and first occurrence,
    numbered C01..."""
    groups: dict[tuple[str, str], list[Mapping]] = {}
    for record in _judgements(records, run):
        groups.setdefault((record["defect"], record["claim"].strip()), []).append(record)
    ordered = sorted(groups.items(), key=lambda g: (g[0][0], min((r["sample"], r["index"]) for r in g[1])))
    items = []
    for number, ((defect, claim), group) in enumerate(ordered, start=1):
        first = min(group, key=lambda r: (r["sample"], r["index"]))
        items.append(Item(
            id=f"C{number:02d}",
            defect=defect,
            claim=claim,
            occurrences=tuple(sorted((r["sample"], r["index"]) for r in group)),
            letters=dict(zip(string.ascii_uppercase, first["reading_order"])),
            claim_kind=first["slot"]["claim_kind"],
            subject=first["slot"]["subject"],
        ))
    return items


def sheet_rows(items: Sequence[Item], config: Config) -> list[dict[str, str]]:
    """One row per (claim, reading), with blank label and notes for the auditor to fill in."""
    statements = {(d.id, r["id"]): r["statement"].strip() for d in config.defects for r in d.readings}
    return [
        dict(zip(FIELDS, (item.id, item.claim_kind, item.subject, item.claim, letter,
                          statements[(item.defect, reading)], "", "")))
        for item in items
        for letter, reading in item.letters.items()
    ]


def write_sheet(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    with Path(path).open("w", newline="", encoding=ENCODING) as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_sheet(path: Path) -> list[dict[str, str]]:
    """The filled sheet's rows, without the rows a spreadsheet adds with every field blank."""
    with Path(path).open(newline="", encoding=ENCODING) as sheet:
        reader = csv.DictReader(sheet)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise SheetError(f"the sheet's columns are {reader.fieldnames}, not {list(FIELDS)}")
        return [row for row in reader if any((value or "").strip() for value in row.values())]


def write_key(path: Path, run: str, items: Iterable[Item]) -> None:
    """The lead's key: the run, and each item's defect, occurrences and letters. Not for the auditor."""
    key = {"run_id": run, "items": {
        i.id: {"defect": i.defect, "claim": i.claim, "occurrences": [list(o) for o in i.occurrences],
               "letters": i.letters} for i in items}}
    Path(path).write_text(json.dumps(key, indent=2) + "\n")


def read_key(path: Path) -> tuple[str, list[Item]]:
    key = json.loads(Path(path).read_text())
    return key["run_id"], [Item(id, k["defect"], k["claim"], tuple(tuple(o) for o in k["occurrences"]), k["letters"])
                           for id, k in key["items"].items()]


def _label(value: str) -> str:
    """A label as typed, with case, surrounding spaces and a space or hyphen for the underscore forgiven."""
    return re.sub(r"[\s-]+", "_", (value or "").strip().lower())


@dataclass
class Agreement:
    pairs: int = 0  # (claim, reading) pairs in the key
    labelled: int = 0  # pairs the auditor labelled with one of the three labels
    agree: int = 0  # labelled pairs whose label equals the judge's
    missing: list[tuple[str, str]] = field(default_factory=list)  # (item, letter) left blank or absent
    invalid: list[tuple[str, str]] = field(default_factory=list)  # (item, letter) with another label
    by_defect: dict[str, tuple[int, int]] = field(default_factory=dict)  # defect -> (agree, labelled)
    confusion: Counter = field(default_factory=Counter)  # (judge label, auditor label) -> pairs
    notes: dict[str, str] = field(default_factory=dict)  # item -> the auditor's notes, joined
    without_noted: tuple[int, int] = (0, 0)  # (agree, labelled) over items with no notes
    labels: dict[str, dict[str, str]] = field(default_factory=dict)  # item -> reading id -> auditor label


def agreement(rows: Sequence[Mapping[str, str]], items: Sequence[Item], records: Sequence[Mapping],
              run: str) -> Agreement:
    """How often the auditor's label equals the judge's, over every (claim, reading) pair of the key.

    The sheet must hold each pair of the key exactly once; a pair it lacks counts as missing, and a
    duplicate or unknown row is refused. The judge's label is read from the run's judgement records at
    the item's first occurrence. Notes are kept per item, and agreement is also given without the items
    that carry notes, since the notes are where the auditor discloses AI assistance (#123)."""
    by_item = {i.id: i for i in items}
    seen: dict[tuple[str, str], Mapping[str, str]] = {}
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        pair = (row.get("item", "").strip(), row.get("letter", "").strip())
        if pair[0] not in by_item or pair[1] not in by_item[pair[0]].letters:
            raise SheetError(f"sheet row {number}: item {pair[0]!r}, letter {pair[1]!r} is not in the key")
        if pair in seen:
            raise SheetError(f"sheet row {number}: item {pair[0]} letter {pair[1]} appears twice")
        seen[pair] = row
    judged = {(r["defect"], r["sample"], r["index"]): r["labels"] for r in _judgements(records, run)}
    report = Agreement()
    tallies: dict[str, list[int]] = {}
    plain = [0, 0]
    for item in items:
        notes = " ".join(n for n in ((seen.get((item.id, letter)) or {}).get("notes", "").strip()
                                     for letter in item.letters) if n)
        if notes:
            report.notes[item.id] = notes
        judge_labels = judged[(item.defect, *item.occurrences[0])]
        for letter, reading in item.letters.items():
            report.pairs += 1
            label = _label((seen.get((item.id, letter)) or {}).get("label", ""))
            if not label:
                report.missing.append((item.id, letter))
                continue
            if label not in LABELS:
                report.invalid.append((item.id, letter))
                continue
            report.labels.setdefault(item.id, {})[reading] = label
            judge = judge_labels[reading]
            report.labelled += 1
            report.confusion[(judge, label)] += 1
            tally = tallies.setdefault(item.defect, [0, 0])
            tally[1] += 1
            if not notes:
                plain[1] += 1
            if label == judge:
                report.agree += 1
                tally[0] += 1
                if not notes:
                    plain[0] += 1
    report.by_defect = {defect: (agree, labelled) for defect, (agree, labelled) in sorted(tallies.items())}
    report.without_noted = (plain[0], plain[1])
    return report


def audit_records(report: Agreement, items: Sequence[Item], run: str, auditor: str) -> list[dict]:
    """One record per audited item for the summary (#53): its defect, occurrences, the auditor, the
    labels by reading id and the notes."""
    return [{"record": "audit", "run_id": run, "item": i.id, "defect": i.defect,
             "occurrences": [list(o) for o in i.occurrences], "auditor": auditor,
             "labels": report.labels.get(i.id, {}), "notes": report.notes.get(i.id, "")} for i in items]


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The blind audit's sheet and its agreement with the judge.")
    commands = parser.add_subparsers(dest="command", required=True)
    sheet = commands.add_parser("sheet", help="write the blind sheet and the lead's key")
    sheet.add_argument("--config", required=True, type=Path)
    sheet.add_argument("--results", required=True, type=Path)
    sheet.add_argument("--sheet", required=True, type=Path)
    sheet.add_argument("--key", required=True, type=Path)
    sheet.add_argument("--run-id", help="build the sheet from this run once its judging is done, before it completes; "
                                        "by default, the first run with a complete record")
    agree = commands.add_parser("agreement", help="compare a filled sheet with the judge's labels")
    agree.add_argument("--results", required=True, type=Path)
    agree.add_argument("--sheet", required=True, type=Path)
    agree.add_argument("--key", required=True, type=Path)
    agree.add_argument("--auditor", help="who labelled the sheet; with --out, the audit records name them")
    agree.add_argument("--out", type=Path, help="append one audit record per item to this file (#53)")
    args = parser.parse_args(argv)

    records = _records(args.results)
    if args.command == "sheet":
        if args.run_id and not judging_done(records, args.run_id):
            parser.error(f"run {args.run_id}'s judging is not done: it has no store record yet")
        run = args.run_id or used_run(records)
        items = audit_items(records, run)
        write_sheet(args.sheet, sheet_rows(items, load_config(args.config)))
        write_key(args.key, run, items)
        print(f"{len(items)} claims to audit from run {run}, written to {args.sheet}; "
              f"key in {args.key} (not for the auditor)")
        return 0
    if args.out and not args.auditor:
        parser.error("--out needs --auditor")
    run, items = read_key(args.key)
    try:
        report = agreement(read_sheet(args.sheet), items, records, run)
    except SheetError as error:
        parser.error(str(error))
    print(f"auditor and judge agree on {report.agree} of {report.labelled} labelled pairs "
          f"({report.pairs} in the key, {len(report.missing)} blank or absent, {len(report.invalid)} invalid)")
    for defect, (agreed, labelled) in report.by_defect.items():
        print(f"  {defect}: {agreed} of {labelled}")
    for (judge, auditor), count in sorted(report.confusion.items()):
        if judge != auditor:
            print(f"  judge {judge}, auditor {auditor}: {count}")
    for kind, pairs in (("blank or absent", report.missing), ("invalid", report.invalid)):
        if pairs:
            print(f"  {kind}: " + ", ".join(f"{item} {letter}" for item, letter in pairs))
    if report.notes:
        print(f"  without the {len(report.notes)} items with notes: "
              f"{report.without_noted[0]} of {report.without_noted[1]}")
        for item, notes in report.notes.items():
            print(f"  notes on {item}: {notes}")
    if args.out:
        with args.out.open("a") as out:
            for record in audit_records(report, items, run, args.auditor):
                out.write(json.dumps(record) + "\n")
        print(f"  {len(items)} audit records appended to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
