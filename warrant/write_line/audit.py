"""The blind audit's sheet and its agreement with the judge (#123, `global.judge.audit`).

A teammate who did not author the defects labels every distinct agent claim on a slot, blind: the
sheet shows the claim, its slot's kind and subject, and the slot's readings lettered in the frozen
reading order, which is what the judge sees, and never the judge's labels, the true reading, the
defect id or the reading ids. The key that maps each item back to its defect, its occurrences in the
claim-writing samples and each letter's reading stays with the lead. Agreement is computed afterwards
from the filled sheet, the key and the judgement records; the judge's labels stand either way.

    uv run python -m warrant.write_line.audit sheet --config <run config> --results <results> --sheet <csv> --key <json>
    uv run python -m warrant.write_line.audit agreement --results <results> --sheet <filled csv> --key <json>

Neither calls a model.
"""

import argparse
import csv
import json
import string
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from warrant.write_line.config import Config, load_config

FIELDS = ("item", "claim_kind", "subject", "claim", "letter", "reading", "label", "notes")
LABELS = ("holds", "fails", "not_addressed")


@dataclass(frozen=True)
class Item:
    """One distinct agent claim on a slot, as the auditor labels it once."""

    id: str
    defect: str
    claim_kind: str
    subject: str
    claim: str
    occurrences: tuple[tuple[int, int], ...]  # (sample, index) of every judgement with this claim
    letters: dict[str, str]  # letter -> reading id, in the slot's frozen reading order


def _judgements(records: Iterable[Mapping]) -> list[Mapping]:
    """The complete judgement records; one that stopped on an error has no labels to compare."""
    return [r for r in records if r.get("record") == "judgement" and r.get("complete")]


def audit_items(records: Iterable[Mapping]) -> list[Item]:
    """Every distinct claim string on a slot, in order of defect and first occurrence, numbered C01..."""
    groups: dict[tuple[str, str], list[Mapping]] = {}
    for record in _judgements(records):
        groups.setdefault((record["defect"], record["claim"].strip()), []).append(record)
    ordered = sorted(groups.items(), key=lambda g: (g[0][0], min((r["sample"], r["index"]) for r in g[1])))
    items = []
    for number, ((defect, claim), group) in enumerate(ordered, start=1):
        first = min(group, key=lambda r: (r["sample"], r["index"]))
        items.append(Item(
            id=f"C{number:02d}",
            defect=defect,
            claim_kind=first["slot"]["claim_kind"],
            subject=first["slot"]["subject"],
            claim=claim,
            occurrences=tuple(sorted((r["sample"], r["index"]) for r in group)),
            letters=dict(zip(string.ascii_uppercase, first["reading_order"])),
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
    with Path(path).open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_sheet(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as sheet:
        return list(csv.DictReader(sheet))


def write_key(path: Path, items: Iterable[Item]) -> None:
    """The lead's key: each item's defect, occurrences and letters. Not for the auditor."""
    key = {i.id: {"defect": i.defect, "claim": i.claim, "occurrences": [list(o) for o in i.occurrences],
                  "letters": i.letters} for i in items}
    Path(path).write_text(json.dumps(key, indent=2) + "\n")


def read_key(path: Path) -> list[Item]:
    key = json.loads(Path(path).read_text())
    return [Item(id, k["defect"], "", "", k["claim"], tuple(tuple(o) for o in k["occurrences"]), k["letters"])
            for id, k in key.items()]


@dataclass
class Agreement:
    pairs: int = 0  # (claim, reading) pairs on the sheet
    labelled: int = 0  # pairs the auditor labelled with one of the three labels
    agree: int = 0  # labelled pairs whose label equals the judge's
    missing: int = 0  # pairs left blank
    invalid: int = 0  # pairs labelled with something else
    by_defect: dict[str, tuple[int, int]] = field(default_factory=dict)  # defect -> (agree, labelled)
    confusion: Counter = field(default_factory=Counter)  # (judge label, auditor label) -> pairs


def agreement(rows: Iterable[Mapping[str, str]], items: Sequence[Item], records: Iterable[Mapping]) -> Agreement:
    """How often the auditor's label equals the judge's, over every (claim, reading) pair on the sheet.
    Labels are read case-insensitively with spaces trimmed; anything but the three labels is counted
    as invalid and left out, and a blank as missing."""
    by_item = {i.id: i for i in items}
    judged = {}
    for record in _judgements(records):
        judged.setdefault((record["defect"], record["claim"].strip()), record["labels"])
    report = Agreement()
    tallies: dict[str, list[int]] = {}
    for row in rows:
        item = by_item[row["item"]]
        reading = item.letters[row["letter"]]
        judge = judged[(item.defect, item.claim)][reading]
        report.pairs += 1
        label = (row.get("label") or "").strip().lower()
        if not label:
            report.missing += 1
            continue
        if label not in LABELS:
            report.invalid += 1
            continue
        report.labelled += 1
        report.confusion[(judge, label)] += 1
        tally = tallies.setdefault(item.defect, [0, 0])
        tally[1] += 1
        if label == judge:
            report.agree += 1
            tally[0] += 1
    report.by_defect = {defect: (agree, labelled) for defect, (agree, labelled) in sorted(tallies.items())}
    return report


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
    agree = commands.add_parser("agreement", help="compare a filled sheet with the judge's labels")
    agree.add_argument("--results", required=True, type=Path)
    agree.add_argument("--sheet", required=True, type=Path)
    agree.add_argument("--key", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "sheet":
        items = audit_items(_records(args.results))
        write_sheet(args.sheet, sheet_rows(items, load_config(args.config)))
        write_key(args.key, items)
        print(f"{len(items)} claims to audit, written to {args.sheet}; key in {args.key} (not for the auditor)")
        return 0
    report = agreement(read_sheet(args.sheet), read_key(args.key), _records(args.results))
    print(f"auditor and judge agree on {report.agree} of {report.labelled} labelled pairs "
          f"({report.pairs} on the sheet, {report.missing} blank, {report.invalid} invalid)")
    for defect, (agreed, labelled) in report.by_defect.items():
        print(f"  {defect}: {agreed} of {labelled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
