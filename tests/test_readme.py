import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text()
DERIVED_HEADING = "### Data derived from LiveSQLBench-Base-Lite"


def derived_paths() -> list[str]:
    """The paths the README's list of derived data names: those in backticks before each item's colon."""
    section = README.split(DERIVED_HEADING, 1)[1].split("\n#", 1)[0]
    items = re.split(r"\n- ", "\n" + section)[1:]
    return [path for item in items for path in re.findall(r"`([^`]+)`", item.split(":", 1)[0])]


def test_the_readme_attributes_the_dataset_to_its_authors_under_its_licence():
    for required in (
        "LiveSQLBench-Base-Lite",
        "birdsql/livesqlbench-base-lite-sqlite",
        "BIRD Team",
        "CC BY-SA 4.0",
        "LICENSE-DATA",
    ):
        assert required in README


def test_the_readme_names_the_changes_made_to_the_dataset():
    for change in ("defects", "knowledge-base entries", "questions", "drift tasks"):
        assert change in README


def test_every_file_or_directory_the_readme_lists_as_derived_data_exists():
    paths = derived_paths()
    assert "freeze/" in paths
    assert [p for p in paths if not (ROOT / p).exists()] == []
