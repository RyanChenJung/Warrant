"""Normalising the battery's findings (#31): `python -m warrant.battery.normalise`.

The normalised output of a database is what "the battery cannot tell two readings apart" compares:
two readings are indistinguishable when their normalised outputs are byte-identical (#34, "Battery
settings").

- A record is `{check, subject, statement, evidence}`: the assertion type, its subject and statement,
  and one `[sql, result]` pair per piece of evidence, in the detector's order. The SQL has its
  whitespace runs collapsed to one space; the result is the JSON value the evidence recorded.
- Dropped: `measured_at`, `valid_from`/`valid_to`, tier, author, conflicts, ids, the question (text,
  options, cost and priority) and impact.
- Results reach this module through the vendored `evidence._jsonable`, so they are already plain:
  Decimal is a float, a date or timestamp is its `str`, NULL is None. A float is written as Python's
  shortest round-trip form; NaN and infinities, which JSON has no form for, as "NaN", "Infinity" and
  "-Infinity". Quote evidence never occurs (the battery passes no dictionary) and is refused.
- The output is one record per line, as canonical JSON (sorted keys, separators `,` and `:`, no ASCII
  escaping), the lines sorted, duplicates kept, with a final newline, in UTF-8.

Counts and percentages are kept, rounded or dropped as the freeze's `global.battery.normalisation`
says: `exact` keeps both, or a mapping `{counts: keep|round|drop, percentages: keep|round|drop}`.
In a statement a percentage is a number followed by `%` and a count is an integer (`1,000`
included) standing on its own, not part of an identifier, date, decimal or quoted value; per-code
frequencies such as `Filled (18)` are counts. In an evidence result an integer (not a bool) is a
count and a float a percentage: in the clean scan of all 18 databases every float in evidence is a
percentage. Rounding takes a percentage to a whole percent and a count to two significant figures,
half up; dropping writes `#` (`#%` in a statement for a percentage, the string "#" in evidence).

Known limit of `round` and `drop`: an integer that is a code or an example value is taken for a
count, so numeric codes (`1 (315)` after the seeing-profile recoding, `[[1, 315], ...]` in its
evidence) are rounded or dropped with the frequencies. Telling them apart would mean special-casing
the vendored statement templates. The freeze uses `exact`, which changes no number.
"""

import argparse
import dataclasses
import json
import math
import re
import tempfile
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml

from warrant.battery.gloss.model import Finding, SqlEvidence
from warrant.battery.run import run_battery
from warrant.battery.settings import EXACT, Normalisation, Setting  # noqa: F401 (re-exported)
from warrant.data.fetch import DEFAULT_CONFIG as RELEASE_CONFIG
from warrant.data.release import Database, Release, load_database

DROPPED = "#"
COUNT_FIGURES = 2

# A number standing on its own: not touching a letter, digit, quote, `_`, `-`, `:`, `/` or a decimal point.
_ALONE_BEFORE = r"(?<![\w.'\"`\-:/])"
_ALONE_AFTER = r"(?![\w'\"`\-:/]|\.\d)"
PERCENTAGE = re.compile(_ALONE_BEFORE + r"(\d+(?:\.\d+)?)%")
COUNT = re.compile(_ALONE_BEFORE + r"(\d{1,3}(?:,\d{3})+|\d+)" + _ALONE_AFTER + r"(?!%)")


def _round_count(n: int) -> int:
    if n == 0:
        return 0
    exponent = math.floor(math.log10(abs(n))) - COUNT_FIGURES + 1
    return int(Decimal(n).scaleb(-exponent).quantize(Decimal(1), ROUND_HALF_UP).scaleb(exponent))


def _round_percentage(x: float) -> float:
    return float(Decimal(repr(x)).quantize(Decimal(1), ROUND_HALF_UP))


def _statement(text: str, settings: Normalisation) -> str:
    if settings.percentages == "round":
        text = PERCENTAGE.sub(lambda m: f"{_round_percentage(float(m[1])):.0f}%", text)
    elif settings.percentages == "drop":
        text = PERCENTAGE.sub(f"{DROPPED}%", text)
    if settings.counts == "round":
        text = COUNT.sub(lambda m: str(_round_count(int(m[1].replace(",", "")))), text)
    elif settings.counts == "drop":
        text = COUNT.sub(DROPPED, text)
    return text


def _result(value: Any, settings: Normalisation) -> Any:
    if isinstance(value, list):
        return [_result(v, settings) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        if settings.percentages == "round":
            return _round_percentage(value)
        return DROPPED if settings.percentages == "drop" else value
    if isinstance(value, int) and not isinstance(value, bool):
        if settings.counts == "round":
            return _round_count(value)
        return DROPPED if settings.counts == "drop" else value
    return value


def record(finding: Finding, settings: Normalisation = EXACT) -> dict:
    """One finding as its normalised record."""
    a = finding.assertion
    evidence = []
    for e in a.evidence:
        if not isinstance(e, SqlEvidence):
            raise TypeError(f"no normalised form for {type(e).__name__} on {a.subject}")
        evidence.append([" ".join(e.sql.split()), _result(e.expected, settings)])
    return {"check": a.type.value, "subject": a.subject, "statement": _statement(a.statement, settings),
            "evidence": evidence}


def _canonical(r: dict) -> str:
    return json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def normalise(findings: Iterable[Finding], settings: Normalisation = EXACT) -> list[dict]:
    """The records of the findings, sorted by their canonical JSON, duplicates kept."""
    return sorted((record(f, settings) for f in findings), key=_canonical)


def normalised_bytes(findings: Iterable[Finding], settings: Normalisation = EXACT) -> bytes:
    """The normalised output: one canonical JSON record per line, sorted, in UTF-8."""
    return "".join(_canonical(r) + "\n" for r in normalise(findings, settings)).encode("utf-8")


def normalise_database(db: Database, today: str, work_dir: Path, settings: Normalisation = EXACT) -> bytes:
    """Run the battery on every table of `db` (at `db.path`, which may be any copy with the clean
    database's schema and declared keys) and return its normalised output."""
    findings = run_battery(db, today, work_dir)
    return normalised_bytes((f for table in findings.values() for f in table), settings)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", required=True, type=Path,
                        help="the freeze; its global.battery.normalisation and global.fixed_date are used")
    parser.add_argument("--database", required=True, help="the database name in the release")
    parser.add_argument("--sqlite", type=Path,
                        help="a copy of the database to run on (a reading database); default the clean copy")
    parser.add_argument("--release-dir", type=Path,
                        help="the fetched release; default the release of the data directory")
    parser.add_argument("--out", required=True, type=Path, help="where to write the normalised output")
    args = parser.parse_args(argv)
    raw = yaml.safe_load(args.freeze.read_text())
    settings = Normalisation.from_freeze(raw)
    today = str(raw["global"]["fixed_date"])
    release_dir = args.release_dir or Release.from_yaml(RELEASE_CONFIG).local_dir()
    db = load_database(release_dir, args.database)
    if args.sqlite is not None:
        db = dataclasses.replace(db, path=args.sqlite)
    with tempfile.TemporaryDirectory() as work_dir:
        data = normalise_database(db, today, Path(work_dir), settings)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(f"{args.out}: {data.count(b'\n')} records, {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
