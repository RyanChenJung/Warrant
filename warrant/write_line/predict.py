"""Predicted outcomes and the bridge prediction under the baseline battery (#37).

    uv run python -m warrant.write_line.predict --freeze freeze/<file>.yaml --injection-record injections/<file>.json

The baseline battery runs once on every distinct reading database that `warrant.defects.build` made
(readings that share a content hash share one run), and its normalised outputs (#31) are compared
byte for byte with the true reading's. No model is called. For each claim (defect slot):

- person only: every reading's output equals the true reading's;
- agent alone: the reference claim holds under every reading whose output equals the true reading's;
- both: some reading's output differs, but the reference claim fails under a reading whose output
  does not.

The rules are applied in that order. They overlap in one case: every reading's output equals the
true reading's and the reference claim holds under every reading. That case is predicted person only.
It is not the case of any frozen defect, since each has a drift reading under which the claim fails.

A claim kind's prediction is the one all its claims share, else "mixed", the per-kind combination
rule of the global part; the record carries the freeze's wording of the rule. The bridge prediction
says whether the battery tells a defect's drift reading from its true reading: whether the drift
reading's database gives a different normalised output.

The command reads the injection record and the copies the builder made, and writes the predictions
with every normalised output into the repository, for a person to commit before the first agent call
on the injected copies. It injects nothing, calls no git and commits nothing.
"""

import argparse
import hashlib
import json
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb
import yaml

from warrant.battery.normalise import normalise_database
from warrant.battery.settings import Normalisation
from warrant.config import data_dir
from warrant.data.release import Database, foreign_keys, sha256
from warrant.defects.build import Built, DriftType, content_hash
from warrant.defects.inject import Defect, load_defect
from warrant.freeze.validate import RELEASE_CONFIG, clean_databases
from warrant.store.claims import ClaimKind, PredictedOutcome

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = Path("predictions")
MIXED = "mixed"
# The pairing and peers `warrant.battery.run` implements (#28, #34); a freeze naming others is refused.
PAIRING, PEERS = "declared_child_to_parent", "declared_foreign_keys"

Battery = Callable[[Database, str, Path, Normalisation], bytes]


@dataclass(frozen=True)
class BatterySettings:
    """The settings the battery runs with, from the freeze's global part."""

    normalisation: Normalisation
    fixed_date: str
    duckdb_version: str
    pairing: str
    peers: str
    per_kind_combination: str

    @classmethod
    def from_freeze(cls, raw: dict) -> "BatterySettings":
        part = raw["global"]
        battery = part.get("battery") or {}
        return cls(
            normalisation=Normalisation.from_freeze(raw),
            fixed_date=str(part["fixed_date"]),
            duckdb_version=str(part["duckdb_version"]),
            pairing=battery.get("pairing"),
            peers=battery.get("peers"),
            per_kind_combination=str(part["per_kind_combination"]),
        )

    def problems(self) -> list[str]:
        """Why the battery here would not run as the freeze says; empty when it would."""
        found = []
        if duckdb.__version__ != self.duckdb_version:
            found.append(f"the freeze fixes DuckDB {self.duckdb_version}, but {duckdb.__version__} is installed")
        if self.pairing != PAIRING:
            found.append(f"the battery pairs declared keys {PAIRING}, not {self.pairing!r}")
        if self.peers != PEERS:
            found.append(f"the battery's peers are the {PEERS}, not {self.peers!r}")
        return found


@dataclass(frozen=True)
class ReadingResult:
    reading: str
    database: str  # content hash of the reading's database
    output: str  # SHA-256 of its normalised output
    differs: bool  # from the true reading's output
    holds: bool  # the reference claim under this reading, as frozen


@dataclass(frozen=True)
class ClaimPrediction:
    defect: str
    claim_kind: ClaimKind
    subject: str
    outcome: PredictedOutcome
    readings: tuple[ReadingResult, ...]


@dataclass(frozen=True)
class Bridge:
    defect: str
    drift_reading: str
    drift_type: DriftType
    battery_tells_apart: bool  # the drift reading's output differs from the true reading's


@dataclass(frozen=True)
class Predictions:
    claims: dict[str, ClaimPrediction]
    kinds: dict[ClaimKind, PredictedOutcome | str]  # a predicted outcome, or MIXED
    bridge: dict[str, Bridge]
    outputs: dict[str, bytes]  # content hash -> normalised output


def outcome(readings: Sequence[ReadingResult]) -> PredictedOutcome:
    """A claim's predicted outcome from all its readings, the true one included."""
    if not any(r.differs for r in readings):
        return PredictedOutcome.PERSON_ONLY
    if all(r.holds for r in readings if not r.differs):
        return PredictedOutcome.AGENT_ALONE
    return PredictedOutcome.BOTH


def combine(outcomes: Iterable[PredictedOutcome]) -> PredictedOutcome | str:
    """The per-kind combination rule: the prediction all claims of the kind share, else mixed."""
    distinct = set(outcomes)
    if not distinct:
        raise ValueError("a claim kind with no claims has no prediction")
    return distinct.pop() if len(distinct) == 1 else MIXED


def predict(
    defects: Sequence[Defect],
    built: Built,
    clean: Mapping[str, Path],
    settings: BatterySettings,
    work_dir: Path,
    battery: Battery = normalise_database,
) -> Predictions:
    """The predictions for every defect with a reading set; `clean` gives each database's declared keys."""
    problems = settings.problems()
    if problems:
        raise ValueError("; ".join(problems))
    keys = {name: foreign_keys(path) for name, path in clean.items()}
    outputs: dict[str, bytes] = {}
    digests: dict[str, str] = {}

    def output(database: str, content: str) -> str:
        if content not in outputs:
            work = Path(work_dir) / content
            work.mkdir(parents=True, exist_ok=True)
            db = Database(database, built.copy(content), keys[database], {}, [])
            outputs[content] = battery(db, settings.fixed_date, work, settings.normalisation)
            digests[content] = hashlib.sha256(outputs[content]).hexdigest()
        return digests[content]

    claims, bridge = {}, {}
    for d in defects:
        if not d.readings:
            continue
        hashes = built.readings[d.id]
        true = next(r["id"] for r in d.readings if r["is_true"])
        expected = output(d.database, hashes[true])
        results = []
        for r in d.readings:
            digest = output(d.database, hashes[r["id"]])
            results.append(ReadingResult(r["id"], hashes[r["id"]], digest, digest != expected, r["holds"]))
        claims[d.id] = ClaimPrediction(d.id, d.slot.claim_kind, d.slot.subject, outcome(results), tuple(results))
        if d.id in built.drift:
            reading, drift_type = built.drift[d.id]
            bridge[d.id] = Bridge(d.id, reading, drift_type, output(d.database, hashes[reading]) != expected)
    kinds = {
        kind: combine(c.outcome for c in claims.values() if c.claim_kind == kind)
        for kind in dict.fromkeys(c.claim_kind for c in claims.values())
    }
    return Predictions(claims, kinds, bridge, outputs)


def record(predictions: Predictions, settings: BatterySettings, provenance: dict, outputs_dir: str) -> dict:
    """The predictions as committed; each normalised output is the file `<outputs_dir>/<content hash>.jsonl`."""
    return {
        **provenance,
        "settings": {
            "normalisation": asdict(settings.normalisation),
            "fixed_date": settings.fixed_date,
            "duckdb_version": {"frozen": settings.duckdb_version, "installed": duckdb.__version__},
            "pairing": settings.pairing,
            "peers": settings.peers,
            "per_kind_combination": settings.per_kind_combination,
        },
        "outputs": {
            content: {"file": f"{outputs_dir}/{content}.jsonl", "sha256": hashlib.sha256(data).hexdigest(),
                      "records": data.count(b"\n")}
            for content, data in sorted(predictions.outputs.items())
        },
        "claims": {
            c.defect: {
                "claim_kind": c.claim_kind.value,
                "subject": c.subject,
                "outcome": c.outcome.value,
                "readings": {r.reading: {"database": r.database, "output": r.output, "differs": r.differs,
                                         "holds": r.holds} for r in c.readings},
            }
            for c in predictions.claims.values()
        },
        "kinds": {kind.value: str(p) for kind, p in predictions.kinds.items()},
        "bridge": {
            b.defect: {"drift_reading": b.drift_reading, "drift_type": b.drift_type.value,
                       "battery_tells_apart": b.battery_tells_apart}
            for b in predictions.bridge.values()
        },
    }


class Refused(Exception):
    """The command will not predict."""


def _shown(path: Path) -> str:
    """A path as the record shows it: relative to the repository, else its name, never a local path."""
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name


def _built(injection: dict, out: Path) -> Built:
    drift = {d: (v["reading"], DriftType(v["type"])) for d, v in injection["drift"].items()}
    built = Built(out, injection["injected"], injection["readings"], drift, ())
    for content in set(built.injected.values()) | {h for r in built.readings.values() for h in r.values()}:
        copy = built.copy(content)
        if not copy.is_file():
            raise Refused(f"no copy {copy.name} in {out / 'copies'}; was the build's output moved?")
        if content_hash(copy) != content:
            raise Refused(f"the content of {copy.name} does not match its name")
    return built


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", required=True, type=Path, help="the freeze the databases were built from")
    parser.add_argument("--injection-record", required=True, type=Path,
                        help="the record `warrant.defects.build` wrote for that build")
    parser.add_argument("--built", type=Path, help="the build's output folder (default: <data dir>/injections/<commit>)")
    parser.add_argument("--release", type=Path, default=RELEASE_CONFIG,
                        help="the release configuration, used when the freeze gives no databases: paths")
    parser.add_argument("--out-dir", type=Path, default=REPO / OUT_DIR, help="where the predictions go, to be committed")
    args = parser.parse_args(argv)
    freeze, injection_path = args.freeze.resolve(), args.injection_record.resolve()
    try:
        raw = yaml.safe_load(freeze.read_text())
        injection = json.loads(injection_path.read_text())
        if injection.get("outcome") != "built":
            raise Refused(f"the injection record's outcome is {injection.get('outcome')!r}, not built")
        if injection.get("freeze_sha256") != sha256(freeze):
            raise Refused(f"the injection record is not of this freeze: {freeze.name}'s SHA-256 differs")
        built = _built(injection, (args.built or data_dir() / "injections" / injection["commit"]).resolve())
        settings = BatterySettings.from_freeze(raw)
        defects = [load_defect(d) for d in raw["defects"]]
        clean = clean_databases(raw, freeze, args.release)
        with tempfile.TemporaryDirectory() as work:
            predictions = predict(defects, built, clean, settings, Path(work))
    except (Refused, ValueError) as error:
        print(f"refused: {error}")
        return 1
    name = f"{injection['commit'][:12]}-{freeze.stem}"
    provenance = {
        "commit": injection["commit"],
        "freeze": _shown(freeze),
        "freeze_sha256": injection["freeze_sha256"],
        "injection_record": _shown(injection_path),
        "injection_record_sha256": sha256(injection_path),
    }
    out = args.out_dir.resolve()
    (out / name).mkdir(parents=True, exist_ok=True)
    for content, data in predictions.outputs.items():
        (out / name / f"{content}.jsonl").write_bytes(data)
    path = out / f"{name}.json"
    path.write_text(json.dumps(record(predictions, settings, provenance, name), indent=2) + "\n")
    for c in predictions.claims.values():
        print(f"{c.defect} ({c.claim_kind.value}): {c.outcome.value}")
    for kind, p in predictions.kinds.items():
        print(f"kind {kind.value}: {p}")
    for b in predictions.bridge.values():
        print(f"bridge {b.defect}: the battery {'tells' if b.battery_tells_apart else 'cannot tell'} "
              f"{b.drift_reading} from the true reading")
    print(f"predictions written to {path} for you to commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
