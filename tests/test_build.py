"""The per-reading database builder and the injection command (#36).

The builder is tested on small fixtures, never the release. The command's guard (ADR 0007) is tested
in a temporary repository whose `origin` is a bare repository on disk, so no test reaches the network.
"""

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml

from warrant.data.release import sha256
from warrant.defects.build import DriftType, build, content_hash, main
from warrant.defects.inject import Defect, load_defect

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parents[1]
TWO_DEFECTS = FIXTURES / "freeze_two_defects.yaml"


def defects_of(path=TWO_DEFECTS):
    return [load_defect(d) for d in yaml.safe_load(Path(path).read_text())["defects"]]


def rows(path, sql):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.fixture
def built(workorders_db, tmp_path):
    return build(defects_of(), {"workorders": workorders_db}, tmp_path / "out")


# Content hash over a canonical dump -----------------------------------------------------------------


def database(path, *statements):
    con = sqlite3.connect(path)
    with con:
        con.execute("CREATE TABLE t (id INTEGER, v)")
        for statement in statements:
            con.execute(statement)
    con.close()
    return path


def test_the_content_hash_ignores_row_order_and_file_layout(tmp_path):
    a = database(tmp_path / "a.sqlite", "INSERT INTO t VALUES (1, 'x')", "INSERT INTO t VALUES (2, 'y')")
    b = database(tmp_path / "b.sqlite", "INSERT INTO t VALUES (2, 'y')", "INSERT INTO t VALUES (1, 'x')")
    assert content_hash(a) == content_hash(b)
    before = a.read_bytes()
    con = sqlite3.connect(a)
    con.execute("CREATE TABLE scratch (x)")
    con.execute("DROP TABLE scratch")
    con.execute("VACUUM")
    con.close()
    assert a.read_bytes() != before and content_hash(a) == content_hash(b)


@pytest.mark.parametrize("other", [
    "INSERT INTO t VALUES (1, 'z')",  # one value differs
    "INSERT INTO t VALUES (1, 1)",  # the integer 1, not the text '1'
    "INSERT INTO t VALUES (1, 1.0)",  # a real, not an integer
])
def test_the_content_hash_tells_values_and_their_types_apart(tmp_path, other):
    a = database(tmp_path / "a.sqlite", "INSERT INTO t VALUES (1, '1')")
    assert content_hash(a) != content_hash(database(tmp_path / "b.sqlite", other))


def test_the_content_hash_keeps_duplicate_rows_and_the_schema(tmp_path):
    once = database(tmp_path / "a.sqlite", "INSERT INTO t VALUES (1, 'x')")
    twice = database(tmp_path / "b.sqlite", "INSERT INTO t VALUES (1, 'x')", "INSERT INTO t VALUES (1, 'x')")
    indexed = database(tmp_path / "c.sqlite", "INSERT INTO t VALUES (1, 'x')", "CREATE INDEX t_id ON t (id)")
    assert len({content_hash(once), content_hash(twice), content_hash(indexed)}) == 3


# Building each reading's database --------------------------------------------------------------------


def test_the_true_readings_database_is_the_injected_copy(built):
    """Criterion 1, by content hash."""
    injected = built.injected["workorders"]
    assert built.readings["short-tasks-cut"]["under-one-hour-cut"] == injected
    assert built.readings["site-recode"]["one-is-north"] == injected
    assert content_hash(built.copy(injected)) == injected


def test_a_world_fixed_drift_reading_gets_its_own_database(built):
    """Criterion 2, first half: drift by a transformation of its own is data-part drift."""
    nothing_cut = built.readings["short-tasks-cut"]["nothing-cut"]
    assert nothing_cut != built.injected["workorders"]
    assert content_hash(built.copy(nothing_cut)) == nothing_cut
    assert built.drift["short-tasks-cut"] == ("nothing-cut", DriftType.DATA_PART)


def test_a_meaning_only_drift_reading_shares_the_injected_copy_and_is_convention_drift(built):
    """Criterion 2, second half."""
    assert built.readings["site-recode"]["two-is-north"] == built.injected["workorders"]
    assert built.drift["site-recode"] == ("two-is-north", DriftType.CONVENTION)


def test_every_meaning_only_reading_shares_the_injected_copy(built):
    """A meaning-only `[]` is no transformation of its own, not nothing applied (#36): the coverage
    defect's provenance reading must not get the nothing-cut database."""
    for d in defects_of():
        for r in d.readings:
            if r["form"] == "meaning_only":
                assert built.readings[d.id][r["id"]] == built.injected[d.database], (d.id, r["id"])


def test_the_clean_copy_is_unchanged_after_building(workorders_db, tmp_path):
    """Criterion 3."""
    content, file = content_hash(workorders_db), sha256(workorders_db)
    build(defects_of(), {"workorders": workorders_db}, tmp_path / "out")
    assert (content_hash(workorders_db), sha256(workorders_db)) == (content, file)


def test_building_twice_gives_the_same_hash_for_every_readings_database(workorders_db, tmp_path):
    """Criterion 4."""
    first = build(defects_of(), {"workorders": workorders_db}, tmp_path / "first")
    second = build(defects_of(), {"workorders": workorders_db}, tmp_path / "second")
    assert first.injected == second.injected and first.readings == second.readings
    for hash in set(first.injected.values()) | {h for r in first.readings.values() for h in r.values()}:
        assert content_hash(second.copy(hash)) == hash


def test_each_readings_database_holds_the_other_defects_true_transformation(built):
    """Criterion 7: the coverage defect's readings are recoded, the value-meaning defect's are cut."""
    for reading, hash in built.readings["short-tasks-cut"].items():
        sites = rows(built.copy(hash), "SELECT site, COUNT(*) FROM workorders GROUP BY site ORDER BY site")
        assert sites == [("1", 7), ("2", 5)], reading
    for reading, hash in built.readings["site-recode"].items():
        assert rows(built.copy(hash), "SELECT COUNT(*) FROM tasks") == [(17,)], reading
    tasks = {r: rows(built.copy(h), "SELECT COUNT(*) FROM tasks")[0][0] for r, h in built.readings["short-tasks-cut"].items()}
    assert tasks == {"under-one-hour-cut": 17, "nothing-cut": 23, "under-two-hours-cut": 12, "kept-elsewhere": 17}


def test_identical_databases_are_built_once(built):
    copies = sorted(p.name for p in (built.out / "copies").glob("*.sqlite"))
    assert len(copies) == 3
    assert copies == sorted(f"{h}.sqlite" for h in {*built.injected.values(), *(h for r in built.readings.values() for h in r.values())})


def test_copies_are_left_read_only(built):
    assert all(not os.access(p, os.W_OK) for p in (built.out / "copies").glob("*.sqlite"))


def with_readings(defect: Defect, readings) -> Defect:
    return Defect(**{**defect.__dict__, "readings": tuple(readings)})


def test_a_meaning_only_true_reading_is_refused(workorders_db, tmp_path):
    """The true reading owns the transformation (#34), so it is world-fixed and actually built."""
    coverage, recode = defects_of()
    meaning_only = [{**r, "form": "meaning_only", "kind": "convention", "transformation": []} if r["is_true"] else r
                    for r in recode.readings]
    with pytest.raises(ValueError, match="world-fixed"):
        build([coverage, with_readings(recode, meaning_only)], {"workorders": workorders_db}, tmp_path / "out")


def test_a_true_reading_whose_database_differs_from_the_injected_copy_is_refused(workorders_db, tmp_path):
    """Two defects whose transformations do not commute: the true reading, built with the other defect
    applied first, is not the injected copy."""
    coverage, recode = defects_of()
    after_recode = ("DELETE FROM tasks WHERE wonum IN (SELECT wonum FROM workorders WHERE site = 'NORTH')",)
    coverage = Defect(**{**coverage.__dict__, "transformation": after_recode})
    coverage = with_readings(coverage, [{**r, "transformation": list(after_recode)} if r["is_true"] else r
                                        for r in coverage.readings])
    with pytest.raises(ValueError, match="injected copy"):
        build([coverage, recode], {"workorders": workorders_db}, tmp_path / "out")


def test_a_defect_without_readings_gets_only_the_injected_copy(workorders_db, tmp_path):
    coverage, recode = defects_of()
    built = build([with_readings(coverage, ()), recode], {"workorders": workorders_db}, tmp_path / "out")
    assert "short-tasks-cut" not in built.readings and "short-tasks-cut" not in built.drift


# The injection command and its guard (ADR 0007) -------------------------------------------------------


@pytest.fixture
def git_env(monkeypatch):
    """Git with no global or system configuration, so the user's hooks and signing play no part."""
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(key, value)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, workorders_db, git_env, monkeypatch):
    """A repository with the two-defect freeze committed under freeze/ and pushed to origin/main."""
    monkeypatch.setenv("WARRANT_DATA_DIR", str(tmp_path / "data"))
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    git(work, "remote", "add", "origin", str(remote))
    raw = yaml.safe_load(TWO_DEFECTS.read_text())
    raw["global"] = yaml.safe_load((FIXTURES / "freeze_valid.yaml").read_text())["global"]
    raw["databases"] = {"workorders": str(workorders_db)}  # outside the repository
    (work / "freeze").mkdir()
    (work / "freeze" / "freeze.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "Freeze")
    git(work, "push", "-q", "origin", "main")
    return work


def inject_command(repo, tmp_path, *extra):
    return main(["--freeze", str(repo / "freeze" / "freeze.yaml"), "--repo", str(repo),
                 "--out", str(tmp_path / "out"), *extra])


def refused(repo, tmp_path, capsys, reason):
    assert inject_command(repo, tmp_path) == 1
    assert reason in capsys.readouterr().out
    assert not (tmp_path / "out").exists() and not (repo / "injections").exists()


def test_the_command_builds_and_records_the_commit_it_runs_from(repo, tmp_path, capsys):
    """Criterion 5, second half: the record holds the commit; the command does not commit it."""
    commits = git(repo, "rev-list", "--count", "HEAD")
    assert inject_command(repo, tmp_path) == 0
    (record_path,) = (repo / "injections").iterdir()
    record = json.loads(record_path.read_text())
    assert record["commit"] == git(repo, "rev-parse", "HEAD")
    assert record["remote"] == "origin" and record["freeze"] == "freeze/freeze.yaml"
    assert record["injected"]["workorders"] == record["readings"]["site-recode"]["one-is-north"]
    assert record["drift"]["site-recode"] == {"reading": "two-is-north", "type": "convention"}
    assert record["drift"]["short-tasks-cut"] == {"reading": "nothing-cut", "type": "data_part"}
    assert str(tmp_path) not in record_path.read_text()  # no local path goes into a committed file
    assert git(repo, "rev-list", "--count", "HEAD") == commits
    assert git(repo, "status", "--porcelain") == "?? injections/"


def test_the_injections_folder_holds_only_the_json_record(repo, tmp_path):
    assert inject_command(repo, tmp_path) == 0
    assert [p.suffix for p in (repo / "injections").rglob("*") if p.is_file()] == [".json"]
    assert len(list((tmp_path / "out" / "copies").glob("*.sqlite"))) == 3


def test_the_record_folder_can_be_moved(repo, tmp_path):
    assert inject_command(repo, tmp_path, "--record-dir", "records/injections") == 0
    assert len(list((repo / "records" / "injections").glob("*.json"))) == 1


def test_a_changed_freeze_file_is_refused(repo, tmp_path, capsys):
    """Criterion 5, first half."""
    freeze = repo / "freeze" / "freeze.yaml"
    freeze.write_text(freeze.read_text() + "# edited\n")
    refused(repo, tmp_path, capsys, "uncommitted")


def test_an_uncommitted_file_in_the_freeze_folder_is_refused(repo, tmp_path, capsys):
    (repo / "freeze" / "rubric.md").write_text("The judge's rubric.\n")
    refused(repo, tmp_path, capsys, "uncommitted")


def ignored_freeze(repo):
    """A freeze file kept out of git with .git/info/exclude, as a draft is before the freeze commit."""
    draft = repo / "freeze" / "draft.yaml"
    draft.write_text((repo / "freeze" / "freeze.yaml").read_text())
    (repo / ".git" / "info" / "exclude").write_text("freeze/draft.yaml\n")
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    return draft


def test_a_freeze_file_that_git_ignores_is_refused(repo, tmp_path, capsys):
    """Ryan's case on #99: an excluded draft shows in no `git status`, but was never committed."""
    draft = ignored_freeze(repo)
    assert main(["--freeze", str(draft), "--repo", str(repo), "--out", str(tmp_path / "out")]) == 1
    assert "not committed" in capsys.readouterr().out
    assert not (tmp_path / "out").exists() and not (repo / "injections").exists()


def test_an_ignored_file_in_the_freeze_folder_is_refused(repo, tmp_path, capsys):
    ignored_freeze(repo)
    refused(repo, tmp_path, capsys, "freeze/draft.yaml")


def test_a_commit_not_on_the_public_remote_is_refused(repo, tmp_path, capsys):
    """Criterion 6: committed but not pushed."""
    (repo / "notes.txt").write_text("local only\n")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "-m", "Local only")
    refused(repo, tmp_path, capsys, "origin/main")


def test_a_commit_pushed_only_to_another_branch_is_refused(repo, tmp_path, capsys):
    """A squash merge deletes the branch, so only origin/main counts as public."""
    git(repo, "switch", "-q", "-c", "feature")
    (repo / "notes.txt").write_text("on a branch\n")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "-m", "On a branch")
    git(repo, "push", "-q", "origin", "feature")
    refused(repo, tmp_path, capsys, "origin/main")


def test_an_unreachable_remote_is_refused(repo, tmp_path, capsys):
    git(repo, "remote", "set-url", "origin", str(tmp_path / "nowhere.git"))
    refused(repo, tmp_path, capsys, "fetch")


def test_an_output_folder_inside_the_repository_is_refused(repo, tmp_path, capsys):
    assert main(["--freeze", str(repo / "freeze" / "freeze.yaml"), "--repo", str(repo),
                 "--out", str(repo / "copies")]) == 1
    assert "inside the repository" in capsys.readouterr().out
    assert not (repo / "copies").exists() and not (repo / "injections").exists()


def test_an_invalid_freeze_is_refused(repo, tmp_path, capsys):
    freeze = repo / "freeze" / "freeze.yaml"
    raw = yaml.safe_load(freeze.read_text())
    del raw["global"]["judge"]
    freeze.write_text(yaml.safe_dump(raw, sort_keys=False))
    git(repo, "commit", "-q", "-am", "Break the freeze")
    git(repo, "push", "-q", "origin", "main")
    refused(repo, tmp_path, capsys, "judge")


def test_the_two_defect_fixture_is_a_valid_freeze_apart_from_its_global_part():
    from warrant.freeze.validate import validate

    raw = yaml.safe_load(TWO_DEFECTS.read_text())
    raw["global"] = yaml.safe_load((FIXTURES / "freeze_valid.yaml").read_text())["global"]
    assert validate(raw) == ([], [])


# No database in the repository ------------------------------------------------------------------------

DATABASE_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".duckdb")


def test_no_database_file_is_committed():
    """Criterion 8: by name, and by SQLite's file header so that a renamed database is caught too."""
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout
    paths = [ROOT / p for p in tracked.decode().split("\0") if p]
    assert [p for p in paths if p.suffix.lower() in DATABASE_SUFFIXES] == []
    headers = []
    for p in paths:
        if p.is_file():
            with open(p, "rb") as f:
                if f.read(16) == b"SQLite format 3\x00":
                    headers.append(p)
    assert headers == []


def test_git_ignores_a_database_under_the_test_fixtures():
    ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "tests/fixtures/stray.sqlite"])
    assert ignored.returncode == 0
