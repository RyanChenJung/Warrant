"""Append-only result records, one JSON object per line.

Every record carries the provenance of the run that produced it: the configuration hash, the repo
commit, the model name and the prompt version (#8, without the content-hash guard). The entry
points are given their provenance and never call git; `provenance()` below is for the commands that
assemble it.
"""

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from warrant.agent.config import ModelConfig
from warrant.agent.prompt import PROMPT_VERSION

REPO_COMMIT_ENV = "WARRANT_REPO_COMMIT"


@dataclass(frozen=True)
class Provenance:
    config_hash: str
    repo_commit: str
    model: str
    prompt_version: str


def config_hash(path: Path) -> str:
    """The SHA-256 of a configuration file, as stored with every result of a run."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repo_commit() -> str:
    """$WARRANT_REPO_COMMIT, else the checked-out commit. For commands, not for entry points."""
    if REPO_COMMIT_ENV in os.environ:
        return os.environ[REPO_COMMIT_ENV]
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def provenance_for(config_path: Path, model: ModelConfig) -> Provenance:
    """What a command records with every result of the run it is about to start."""
    return Provenance(
        config_hash=config_hash(config_path),
        repo_commit=repo_commit(),
        model=model.model,
        prompt_version=PROMPT_VERSION,
    )


def append(path: Path, provenance: Provenance, record: Mapping[str, Any]) -> None:
    """Add one record. The file is only ever appended to."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {**asdict(provenance), "timestamp": datetime.now(timezone.utc).isoformat(), **record},
        default=str,
    )
    with path.open("a") as out:
        out.write(line + "\n")
