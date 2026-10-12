"""The write-line configuration, read from YAML (see tests/fixtures/write_line.yaml)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from warrant.agent.config import ModelConfig, load_model_config
from warrant.defects.inject import Defect
from warrant.store.claims import ClaimKind, Slot


@dataclass(frozen=True)
class Question:
    id: str
    database: str
    text: str
    gold_sql: str
    defect: str | None


@dataclass(frozen=True)
class Config:
    databases: dict[str, Path]
    defects: tuple[Defect, ...]
    questions: tuple[Question, ...]
    rules: tuple[str, ...]
    runs: int
    model: ModelConfig | None = None


def load_config(path: Path) -> Config:
    """Read a configuration; database paths are relative to the configuration file."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    return Config(
        databases={name: (path.parent / db).resolve() for name, db in raw["databases"].items()},
        defects=tuple(
            Defect(
                id=d["id"],
                database=d["database"],
                slot=Slot(ClaimKind(d["slot"]["claim_kind"]), d["slot"]["subject"]),
                transformation=tuple(d["transformation"]),
                reference_claim=d["reference_claim"],
            )
            for d in raw["defects"]
        ),
        questions=tuple(
            Question(id=q["id"], database=q["database"], text=q["text"], gold_sql=q["gold_sql"], defect=q.get("defect"))
            for q in raw["questions"]
        ),
        rules=tuple(raw["rules"]),
        runs=int(raw["runs"]),
        model=load_model_config(raw["model"]) if raw.get("model") else None,
    )
