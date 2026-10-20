"""The write-line configuration, read from YAML (see tests/fixtures/write_line.yaml).

A configuration that names a committed freeze (`freeze:`) takes its defects, its global part and its
clean databases from it, so they cannot drift from what was frozen, and may name the injection
record of that freeze (`injection:`), which the run checks its databases against (#49).
"""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from warrant.agent.config import ModelConfig, load_model_config
from warrant.data.release import sha256
from warrant.defects.inject import Defect, load_defect
from warrant.freeze.validate import RELEASE_CONFIG, clean_databases


@dataclass(frozen=True)
class Question:
    """A probe question (`defect` names its defect) or a control question (`defect` is None).

    A question has a gold SQL, or, when its correct response is a refusal, the terms that name its
    missing piece. `key` names the columns a set answer is compared on. A probe with a gold SQL names
    the readings it separates (`separates`), each with the SQL that answers it on the injected copy
    under that reading; the run checks them before any agent call (#34, round 2).
    """

    id: str
    database: str
    text: str
    gold_sql: str | None
    defect: str | None
    missing_terms: tuple[str, ...] = ()
    key: tuple[str, ...] = ()
    separates: tuple[tuple[str, str], ...] = ()  # (reading id, SQL under that reading)


def _names(raw: dict, field: str) -> tuple[str, ...]:
    """A list of non-empty strings. A bare string would otherwise be read as its characters."""
    value = raw.get(field, [])
    if not isinstance(value, list) or not all(isinstance(name, str) and name.strip() for name in value):
        raise ValueError(f"question {raw['id']!r}: {field} must be a list of non-empty strings")
    return tuple(value)


def _question(raw: dict) -> Question:
    if (raw.get("gold_sql") is None) == (not raw.get("missing_terms")):
        raise ValueError(f"question {raw['id']!r} needs exactly one of gold_sql and missing_terms")
    separates = raw.get("separates") or {}
    if not isinstance(separates, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in separates.items()):
        raise ValueError(f"question {raw['id']!r}: separates maps reading ids to SQL")
    if separates and (raw.get("defect") is None or raw.get("gold_sql") is None):
        raise ValueError(f"question {raw['id']!r}: only a probe with a gold answer names readings it separates")
    return Question(
        id=raw["id"],
        database=raw["database"],
        text=raw["text"],
        gold_sql=raw.get("gold_sql"),
        defect=raw.get("defect"),
        missing_terms=_names(raw, "missing_terms"),
        key=_names(raw, "key"),
        separates=tuple(separates.items()),
    )


@dataclass(frozen=True)
class Config:
    databases: dict[str, Path]
    defects: tuple[Defect, ...]
    questions: tuple[Question, ...]
    rules: tuple[str, ...]
    runs: int
    model: ModelConfig | None = None
    global_part: dict | None = None
    # The injection record of the freeze, when the configuration names one.
    injection: dict | None = None


def load_config(path: Path, release_config: Path = RELEASE_CONFIG) -> Config:
    """Read a configuration; paths are relative to the configuration file."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    common = dict(
        questions=tuple(_question(q) for q in raw["questions"]),
        rules=tuple(raw["rules"]),
        runs=int(raw["runs"]),
        model=load_model_config(raw["model"]) if raw.get("model") else None,
    )
    if not raw.get("freeze"):
        if raw.get("injection"):
            raise ValueError("an injection record needs the freeze it was built from (freeze:)")
        return Config(
            databases={name: (path.parent / db).resolve() for name, db in raw["databases"].items()},
            defects=tuple(load_defect(d) for d in raw["defects"]),
            global_part=raw.get("global"),
            **common,
        )
    if any(key in raw for key in ("defects", "global", "databases")):
        raise ValueError("a configuration that names a freeze takes its defects, global part and databases from it")
    freeze = (path.parent / raw["freeze"]).resolve()
    frozen = yaml.safe_load(freeze.read_text())
    injection = None
    if raw.get("injection"):
        injection = json.loads((path.parent / raw["injection"]).read_text())
        if injection.get("outcome") != "built":
            raise ValueError(f"the injection record's outcome is {injection.get('outcome')!r}, not 'built'")
        if injection.get("freeze_sha256") != sha256(freeze):
            raise ValueError(f"the injection record is not of this freeze: {freeze.name}'s SHA-256 differs")
    return Config(
        databases=clean_databases(frozen, freeze, release_config),
        defects=tuple(load_defect(d) for d in frozen["defects"]),
        global_part=frozen.get("global"),
        injection=injection,
        **common,
    )
