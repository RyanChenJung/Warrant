"""Getting bytes into a queryable state without destroying the evidence.

Two decisions matter here and both are load-bearing:

1. Encoding is detected over the whole file, not a sample. Legacy exports are
   often cp1252, and the first non-UTF-8 byte can sit far into the file - past
   any reasonable sniff window. DuckDB cannot read cp1252 at all (its latin-1
   reader rejects the C1 range cp1252 uses for smart quotes), so non-UTF-8
   sources are transcoded into a cache directory (default .gloss-cache in the
   working directory, gitignored here) that must never be committed.

2. Every column is read as VARCHAR. Type 3 FIELD detection compares a declared
   type against the observed text format; coercion would erase the finding.
"""
from __future__ import annotations

import codecs
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb

CANDIDATE_ENCODINGS = ("utf-8", "cp1252", "latin-1")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CHUNK = 1 << 20


@dataclass(frozen=True)
class SourceTable:
    """`name` is the logical name every piece of evidence SQL refers to."""

    name: str
    path: Path
    encoding: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER.match(self.name):
            raise ValueError(
                f"logical table name must be a bare SQL identifier: {self.name!r}"
            )


def detect_encoding(path: Path) -> str:
    """First candidate that decodes the entire file. Streams, so a large file costs
    a read rather than a load."""
    for enc in CANDIDATE_ENCODINGS:
        decoder = codecs.getincrementaldecoder(enc)()
        try:
            with path.open("rb") as fh:
                while chunk := fh.read(_CHUNK):
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path} as any of {CANDIDATE_ENCODINGS}")


def normalise(path: Path, cache_dir: Path) -> Path:
    """Return a UTF-8 path for `path`, transcoding into `cache_dir` if needed.

    The cache directory (default .gloss-cache, gitignored here) holds a verbatim
    copy of customer data and must never be committed.
    """
    encoding = detect_encoding(path)
    if encoding == "utf-8":
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{path.stem}.utf8{path.suffix}"
    with path.open("r", encoding=encoding, newline="") as src, \
            out.open("w", encoding="utf-8", newline="") as dst:
        shutil.copyfileobj(src, dst, length=_CHUNK)
    return out


def open_workspace(
    tables: list[SourceTable], cache_dir: Path
) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    for table in tables:
        readable = normalise(table.path, cache_dir)
        # The relation API rather than a CREATE VIEW string: DuckDB cannot bind
        # parameters inside CREATE VIEW, and interpolating the path would put a
        # filesystem location into SQL. This way the path never appears in any
        # statement a detector could copy into evidence.
        relation = conn.read_csv(
            str(readable), all_varchar=True, sample_size=-1, header=True,
        )
        # Materialised, not a view. A view over read_csv re-parses the file on
        # every query, and a full sweep issues many of them. On a large export a
        # simple aggregate is much slower against a view than against a table, so
        # materialising makes a slow sweep a fast one. The cost is a one-off load
        # and holding the table in memory, which is the right trade for a profiling
        # tool.
        relation.to_table(table.name)
    return conn


def columns(conn: duckdb.DuckDBPyConnection, name: str) -> list[str]:
    return [r[0] for r in conn.sql(f'DESCRIBE "{name}"').fetchall()]


def row_count(conn: duckdb.DuckDBPyConnection, name: str) -> int:
    return conn.sql(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
