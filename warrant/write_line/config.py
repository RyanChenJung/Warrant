"""The write-line configuration, read from YAML (see tests/fixtures/write_line.yaml)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from warrant.agent.config import ModelConfig, load_model_config
from warrant.defects.inject import Defect, load_defect


@dataclass(frozen=True)
class Question:
    """A probe question (`defect` names its defect) or a control question (`defect` is None).

    A question has a gold SQL, or, when its correct response is a refusal, the terms that name its
    missing piece. `key` names the columns a set answer is compared on.
    """

    id: str
    database: str
    text: str
    gold_sql: str | None
    defect: str | None
    missing_terms: tuple[str, ...] = ()
    key: tuple[str, ...] = ()


def _names(raw: dict, field: str) -> tuple[str, ...]:
    """A list of non-empty strings. A bare string would otherwise be read as its characters."""
    value = raw.get(field, [])
    if not isinstance(value, list) or not all(isinstance(name, str) and name.strip() for name in value):
        raise ValueError(f"question {raw['id']!r}: {field} must be a list of non-empty strings")
    return tuple(value)


def _question(raw: dict) -> Question:
    if (raw.get("gold_sql") is None) == (not raw.get("missing_terms")):
        raise ValueError(f"question {raw['id']!r} needs exactly one of gold_sql and missing_terms")
    return Question(
        id=raw["id"],
        database=raw["database"],
        text=raw["text"],
        gold_sql=raw.get("gold_sql"),
        defect=raw.get("defect"),
        missing_terms=_names(raw, "missing_terms"),
        key=_names(raw, "key"),
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


def load_config(path: Path) -> Config:
    """Read a configuration; database paths are relative to the configuration file."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    return Config(
        databases={name: (path.parent / db).resolve() for name, db in raw["databases"].items()},
        defects=tuple(load_defect(d) for d in raw["defects"]),
        questions=tuple(_question(q) for q in raw["questions"]),
        rules=tuple(raw["rules"]),
        runs=int(raw["runs"]),
        model=load_model_config(raw["model"]) if raw.get("model") else None,
        global_part=raw.get("global"),
    )
