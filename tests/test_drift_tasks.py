"""The committed documented drift tasks (#43). The checks that need the clean databases run only where
the release is fetched; the rest run everywhere."""

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from warrant.data.release import Release, read_knowledge_base
from warrant.maintenance import validate
from warrant.maintenance.config import DriftType, load_config
from warrant.maintenance.draw import EXCLUDED, PER_DATABASE, candidates

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "drift_tasks" / "config.yaml"
RELEASE = Release.from_yaml(ROOT / "configs" / "livesqlbench-base-lite.yaml")
FETCHED = all((RELEASE.local_dir() / db / f"{db}_kb.jsonl").exists() for db in RELEASE.databases)
needs_release = pytest.mark.skipif(not FETCHED, reason="the release is not fetched into the data directory")


def drawn(path: Path) -> tuple[int, str, int, str]:
    """A task file's draw position, database, entry id and the direction its header says it used."""
    header = path.read_text()
    database, entry = path.stem.rsplit("-", 1)
    position = int(re.search(r"Draw position: (\d+)", header).group(1))
    direction = re.search(r"Direction used: (up|down) \(drawn\)", header).group(1)
    return position, database, int(entry), direction


def task_files() -> list[Path]:
    """The task files, in the order the configuration lists them."""
    return [ROOT / "drift_tasks" / name for name in yaml.safe_load(CONFIG.read_text())["tasks"]]


def test_twenty_documented_tasks_at_most_two_per_database_and_none_on_the_write_line_databases():
    config = load_config(CONFIG)
    per_database = Counter(task.database for task in config.tasks)
    assert len(config.tasks) == 20
    assert {task.drift_type for task in config.tasks} == {DriftType.DOCUMENTED}
    assert not set(per_database) & set(EXCLUDED)
    assert max(per_database.values()) <= PER_DATABASE
    assert set(per_database) == set(config.databases)


def test_the_tasks_are_listed_in_draw_order():
    positions = [drawn(path)[0] for path in task_files()]
    assert positions == sorted(positions) and len(set(positions)) == len(positions)


@needs_release
def test_every_task_is_valid_on_the_clean_databases(capsys):
    assert validate.main(["--config", str(CONFIG)]) == 0
    assert "20 of 20 tasks valid" in capsys.readouterr().out


@needs_release
def test_each_task_is_the_entry_drawn_at_its_position_in_the_drawn_direction():
    knowledge_bases = {
        db: read_knowledge_base(RELEASE.local_dir() / db / f"{db}_kb.jsonl")
        for db in RELEASE.databases
        if db not in EXCLUDED
    }
    order = candidates(RELEASE, knowledge_bases)
    for path in task_files():
        position, database, entry, direction = drawn(path)
        candidate = order[position - 1]
        assert (candidate.database, candidate.entry, candidate.direction) == (database, entry, direction), path.name
