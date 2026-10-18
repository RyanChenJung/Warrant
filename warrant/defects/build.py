"""Inject a freeze's defects and build each reading's database (#36).

    uv run python -m warrant.defects.build --freeze freeze/<file>.yaml

All defects of a database are injected into one copy of its clean copy, in the declared order: the
injected copy. A world-fixed reading's database is the clean copy with the other defects' true
transformations applied, then the reading's own; the true reading owns its defect's transformation,
so its database must be the injected copy. A meaning-only reading has no transformation of its own
and shares the injected copy. Copies are named by a content hash over a canonical dump, so identical
databases are built once, and they stay in the data directory, never in the repository.

The command refuses to run while the freeze folder has uncommitted changes or while the commit it
runs from is not on the public remote's main branch, checked after a fetch (ADR 0007). It writes the
injection record, with that commit, as JSON into the repository for a person to commit; it commits
nothing itself. `build` never calls git.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

import yaml

from warrant.config import data_dir
from warrant.data.release import sha256
from warrant.data.sqlite import connect_read_only
from warrant.defects.audit import Audit
from warrant.defects.inject import Defect, inject, load_defect
from warrant.freeze.validate import RELEASE_CONFIG, clean_databases, validate

REPO = Path(__file__).resolve().parents[2]
# Where the injection record goes, relative to the repository. The location is still being settled
# with the project lead, so it is one constant here and a flag on the command.
RECORD_DIR = Path("injections")
PUBLIC_REMOTE, PUBLIC_BRANCH = "origin", "main"


class DriftType(StrEnum):
    """A drift reading's drift type, which follows from its database by content hash (#34)."""

    CONVENTION = "convention"  # the drift reading shares the injected copy
    DATA_PART = "data_part"  # the drift reading has a database of its own


def content_hash(path: Path) -> str:
    """SHA-256 over a canonical dump: the schema, then each table's rows, sorted.

    The file's bytes are not hashed, because page layout and SQLite's header counters differ between
    files with the same content. Each value is written with its type, so 1, 1.0 and '1' differ.
    """
    digest = hashlib.sha256()
    con = connect_read_only(path)
    try:
        entries = con.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        for entry in entries:
            digest.update((json.dumps(entry) + "\n").encode())
        for kind, name, _, _ in entries:
            if kind != "table":
                continue
            digest.update(f"table {json.dumps(name)}\n".encode())
            # ponytail: a table's rows are sorted in memory; stream a sorted export if a database
            # ever outgrows it.
            for row in sorted(json.dumps([_cell(v) for v in row]) for row in con.execute(f'SELECT * FROM "{name}"')):
                digest.update((row + "\n").encode())
    finally:
        con.close()
    return digest.hexdigest()


def _cell(value):
    if isinstance(value, bytes):
        return ["blob", value.hex()]
    return [type(value).__name__, value]


@dataclass(frozen=True)
class Built:
    out: Path
    injected: dict[str, str]  # database -> content hash of its injected copy
    readings: dict[str, dict[str, str]]  # defect -> reading -> content hash of its database
    drift: dict[str, tuple[str, DriftType]]  # defect -> (its drift reading, drift type)
    audits: tuple[Audit, ...]

    def copy(self, content: str) -> Path:
        return self.out / "copies" / f"{content}.sqlite"


def _keep(path: Path, out: Path) -> str:
    """Move a built database to its content-hash name, or drop it when that copy exists already."""
    content = content_hash(path)
    target = out / "copies" / f"{content}.sqlite"
    if target.exists():
        path.unlink()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        path.chmod(0o444)
        os.replace(path, target)
    return content


def _apply(clean: Path, dest: Path, statements: list[str]) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clean, dest)
    con = sqlite3.connect(dest)
    try:
        with con:
            for statement in statements:
                con.execute(statement)
    finally:
        con.close()
    return dest


def build(defects: list[Defect], clean: dict[str, Path], out: Path) -> Built:
    """Inject each database's defects and build every reading's database; the clean copies are only read."""
    work = out / "building"
    injected, readings, drift, audits = {}, {}, {}, []
    for name in dict.fromkeys(d.database for d in defects):
        if name not in clean:
            raise ValueError(f"no clean copy for database {name!r}")
        mine = [d for d in defects if d.database == name]
        audits += inject(clean[name], work / f"{name}.injected.sqlite", mine)
        injected[name] = _keep(work / f"{name}.injected.sqlite", out)
        for d in mine:
            if not d.readings:
                continue
            others = [s for o in mine if o is not d for s in o.transformation]
            readings[d.id] = {}
            for r in d.readings:
                if r["is_true"] and r["form"] != "world_fixed":
                    raise ValueError(
                        f"defect {d.id!r}: its true reading {r['id']!r} must be world-fixed and own the defect's transformation"
                    )
                if r["form"] == "meaning_only":
                    readings[d.id][r["id"]] = injected[name]
                    continue
                built = _apply(clean[name], work / f"{d.id}--{r['id']}.sqlite", others + list(r["transformation"]))
                readings[d.id][r["id"]] = _keep(built, out)
                if r["is_true"] and readings[d.id][r["id"]] != injected[name]:
                    raise ValueError(
                        f"defect {d.id!r}: its true reading {r['id']!r} does not give the injected copy; "
                        "do the defects' transformations depend on their order?"
                    )
            if d.drift_reading:
                reading = d.drift_reading["reading"]
                same = readings[d.id][reading] == injected[name]
                drift[d.id] = (reading, DriftType.CONVENTION if same else DriftType.DATA_PART)
    return Built(out, injected, readings, drift, tuple(audits))


class Refused(Exception):
    """The command will not inject."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def guard(repo: Path, freeze: Path, remote: str = PUBLIC_REMOTE, branch: str = PUBLIC_BRANCH) -> str:
    """The commit to inject from, once the freeze folder is committed and the commit is public (ADR 0007).

    The commit comes from git itself, never from $WARRANT_REPO_COMMIT, so a run cannot claim a commit
    it does not run from. Only the remote's main branch counts: a squash merge deletes the PR branch.
    """
    # The freeze file must be in HEAD as it is on disk; `git status` alone lists no ignored file, and a
    # draft kept in .git/info/exclude would pass it without ever being committed.
    if _git(repo, "ls-files", "--error-unmatch", "--", str(freeze)).returncode:
        raise Refused(f"the freeze file {freeze.name} is not committed")
    if _git(repo, "diff", "--quiet", "HEAD", "--", str(freeze)).returncode:
        raise Refused(f"the freeze has uncommitted changes: {freeze.name}")
    status = _git(repo, "status", "--porcelain", "--untracked-files=all", "--ignored", "--", str(freeze.parent))
    if status.returncode:
        raise Refused(f"git status failed: {status.stderr.strip()}")
    if status.stdout.strip():
        raise Refused(f"the freeze folder has uncommitted or ignored files:\n{status.stdout.rstrip()}")
    # The record says the run came from its commit, so the code, configs and battery must be that
    # commit's too. Untracked files elsewhere, such as an earlier run's record, are no part of it.
    changed = _git(repo, "diff", "--name-only", "HEAD")
    if changed.returncode or changed.stdout.strip():
        raise Refused(f"tracked files differ from HEAD:\n{changed.stdout.rstrip() or changed.stderr.strip()}")
    fetch = _git(repo, "fetch", "--quiet", remote, branch)
    if fetch.returncode:
        raise Refused(f"could not fetch {remote}/{branch}, so the commit cannot be checked: {fetch.stderr.strip()}")
    commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if _git(repo, "merge-base", "--is-ancestor", "HEAD", f"{remote}/{branch}").returncode:
        raise Refused(f"commit {commit[:12]} is not on {remote}/{branch}; merge and push it first")
    return commit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", required=True, type=Path, help="the freeze file, committed and pushed")
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--release", type=Path, default=RELEASE_CONFIG,
                        help="the release configuration, used when the freeze gives no databases: paths")
    parser.add_argument("--out", type=Path, help="where the copies go (default: <data dir>/injections/<commit>)")
    parser.add_argument("--record-dir", type=Path, default=RECORD_DIR, help="the record's folder, in the repository")
    args = parser.parse_args(argv)
    repo, freeze = args.repo.resolve(), args.freeze.resolve()
    try:
        commit = guard(repo, freeze)
        out = (args.out or data_dir() / "injections" / commit).resolve()
        if out.is_relative_to(repo):
            raise Refused(f"the output folder {out} is inside the repository; databases are never committed")
        raw = yaml.safe_load(freeze.read_text())
        errors, _ = validate(raw)
        if errors:
            raise Refused("the freeze is not valid:\n" + "\n".join(errors))
        clean = clean_databases(raw, freeze, args.release)
        missing = [name for name, path in clean.items() if not path.is_file()]
        if missing:
            raise Refused(f"no clean copy of {', '.join(missing)}; fetch the release with `uv run python -m warrant.data.fetch`")
        built = build([load_defect(d) for d in raw["defects"]], clean, out)
    except (Refused, ValueError) as error:
        print(f"refused: {error}")
        return 1
    record = {
        "commit": commit,
        "remote": PUBLIC_REMOTE,
        "branch": PUBLIC_BRANCH,
        "freeze": freeze.relative_to(repo).as_posix(),
        "freeze_sha256": sha256(freeze),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "clean": {name: content_hash(path) for name, path in clean.items()},
        "injected": built.injected,
        "readings": built.readings,
        "drift": {d: {"reading": r, "type": t.value} for d, (r, t) in built.drift.items()},
        "audits": [asdict(a) for a in built.audits],
    }
    path = repo / args.record_dir / f"{commit[:12]}-{freeze.stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    print(f"built {len(set(built.injected.values()) | {h for r in built.readings.values() for h in r.values()})} "
          f"databases in {out / 'copies'}; record written to {path.relative_to(repo)} for you to commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
