"""The order in which knowledge-base entries are tried as documented drift tasks (#43).

    uv run python -m warrant.maintenance.draw

Every entry of the release's databases, the write line's excepted, whose definition states a number
is a candidate. The candidates are put in an order drawn with a recorded seed, each with a drawn
direction for its new value, so that no entry is picked by hand: the team writes tasks in this
order, at most two per database, skipping an entry only for a reason listed on #43 and recording it.
"""

import argparse
import random
import re
from dataclasses import dataclass
from pathlib import Path

from warrant.data.release import Release, read_knowledge_base

SEED = 20261015
# The write line's databases: in crypto most entries name or build on a column a write-line defect
# changes, so one entry would have two answers across the lines with no drift (#43).
EXCLUDED = ("crypto", "alien")
PER_DATABASE = 2
# A new value is the old one moved by this share, up or down.
CHANGE = 0.2
DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class Candidate:
    database: str
    entry: int
    knowledge: str
    direction: str  # "up" or "down"


def candidates(release: Release, knowledge_bases: dict[str, list[dict]], seed: int = SEED) -> list[Candidate]:
    """Every entry whose definition states a number, in the order the seed draws, with its direction."""
    pool = sorted(
        (database, e["id"], e["knowledge"])
        for database in release.databases
        if database not in EXCLUDED
        for e in knowledge_bases[database]
        if DIGIT.search(e["definition"])
    )
    rng = random.Random(seed)
    rng.shuffle(pool)
    return [Candidate(database, entry, knowledge, rng.choice(("up", "down"))) for database, entry, knowledge in pool]


def new_value(old: str, direction: str) -> str:
    """The old number moved by 20 percent in the direction, rounded to the old number's decimal places
    and written the same way (with thousands separators if it had them)."""
    digits = old.replace(",", "")
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    value = float(digits) * (1 + CHANGE if direction == "up" else 1 - CHANGE)
    return f"{value:{',' if ',' in old else ''}.{decimals}f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print the order in which entries are tried as drift tasks.")
    parser.add_argument("--release", type=Path, default=Path("configs/livesqlbench-base-lite.yaml"))
    args = parser.parse_args(argv)
    release = Release.from_yaml(args.release)
    root = release.local_dir()
    knowledge_bases = {
        database: read_knowledge_base(root / database / f"{database}_kb.jsonl")
        for database in release.databases
        if database not in EXCLUDED
    }
    for position, c in enumerate(candidates(release, knowledge_bases), 1):
        print(f"{position}\t{c.database}\t{c.entry}\t{c.direction}\t{c.knowledge}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
