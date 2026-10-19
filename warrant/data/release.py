"""The public LiveSQLBench-Base-Lite SQLite release, pinned to one revision.

Per database the release holds a template SQLite file (the clean copy, never modified), column
meanings and a knowledge base. Only these three files are fetched; the release's task file is not
used, because the team writes every question and gold SQL.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from warrant.config import data_dir

FILE_SUFFIXES = ("_template.sqlite", "_column_meaning_base.json", "_kb.jsonl")


class ChecksumMismatch(Exception):
    """A fetched file does not match the recorded checksum."""


@dataclass(frozen=True)
class Release:
    dataset: str
    revision: str
    databases: tuple[str, ...]

    @classmethod
    def from_yaml(cls, path: Path) -> "Release":
        raw = yaml.safe_load(Path(path).read_text())
        return cls(dataset=raw["dataset"], revision=str(raw["revision"]), databases=tuple(raw["databases"]))

    def files(self) -> list[str]:
        """Paths of the fetched files, relative to the release root."""
        return [f"{db}/{db}{suffix}" for db in self.databases for suffix in FILE_SUFFIXES]

    def url(self, relative: str) -> str:
        return f"https://huggingface.co/datasets/{self.dataset}/resolve/{self.revision}/{relative}"

    def local_dir(self) -> Path:
        """Where this release is fetched to: one directory per revision inside the data directory."""
        return data_dir() / "livesqlbench-base-lite" / self.revision

    def template(self, name: str) -> Path:
        """A database's clean copy: its template SQLite file in the fetched release."""
        return self.local_dir() / name / f"{name}_template.sqlite"


@dataclass(frozen=True, order=True)
class ForeignKey:
    table: str
    column: str
    ref_table: str
    ref_column: str


@dataclass(frozen=True)
class Database:
    name: str
    path: Path
    foreign_keys: list[ForeignKey]
    column_meanings: dict[str, Any]
    knowledge_base: list[dict[str, Any]]


def http_download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(release: Release, dest: Path, expected: dict[str, str] | None = None, download=http_download) -> dict[str, str]:
    """Fetch the release into dest and return each file's SHA-256, keyed by relative path.

    With `expected`, a file already in dest that matches its recorded checksum is not fetched again,
    and any fetched file that does not match raises ChecksumMismatch. Every file is left read-only.
    """
    checksums = {}
    for relative in release.files():
        target = dest / relative
        if expected is not None and relative not in expected:
            raise ChecksumMismatch(f"{relative}: no recorded checksum")
        if not (expected and target.exists() and sha256(target) == expected[relative]):
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".partial")
            download(release.url(relative), partial)
            os.replace(partial, target)
        checksums[relative] = sha256(target)
        if expected is not None and checksums[relative] != expected[relative]:
            raise ChecksumMismatch(f"{relative}: got {checksums[relative]}, recorded {expected[relative]}")
        target.chmod(0o444)
    return checksums


def read_checksums(path: Path) -> dict[str, str]:
    """Read a checksum file in `sha256sum` format."""
    pairs = (line.split(maxsplit=1) for line in Path(path).read_text().splitlines() if line.strip())
    return {relative.strip(): digest for digest, relative in pairs}


def write_checksums(path: Path, checksums: dict[str, str]) -> None:
    Path(path).write_text("".join(f"{digest}  {relative}\n" for relative, digest in sorted(checksums.items())))


def read_knowledge_base(path: Path) -> list[dict[str, Any]]:
    """The entries of a knowledge-base file (`<db>_kb.jsonl`), one JSON object per line."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def load_database(release_dir: Path, name: str) -> Database:
    """Load one database of a fetched release: declared foreign keys, column meanings, knowledge base."""
    root = Path(release_dir) / name
    path = root / f"{name}_template.sqlite"
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        foreign_keys = [
            ForeignKey(table, column, ref_table, ref_column)
            for table in tables
            for _id, _seq, ref_table, column, ref_column, *_ in con.execute(f'PRAGMA foreign_key_list("{table}")')
        ]
    finally:
        con.close()
    column_meanings = json.loads((root / f"{name}_column_meaning_base.json").read_text())
    knowledge_base = read_knowledge_base(root / f"{name}_kb.jsonl")
    return Database(name, path, foreign_keys, column_meanings, knowledge_base)
