import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from anthropic.types import Message

FIXTURES = Path(__file__).parent / "fixtures"
RESPONSES = FIXTURES / "responses"


@pytest.fixture(autouse=True)
def no_live_model_calls(monkeypatch):
    """No test calls a model: the agent's client factory raises if anything reaches for it."""

    def refuse(config):
        raise AssertionError(f"a test tried to reach the real model: {config.provider}")

    monkeypatch.setattr("warrant.agent.claude.client", refuse)


class Replay:
    """Stands in for `messages.create`: hands back recorded responses and keeps every request.

    The responses under `fixtures/responses/` are written by hand to the shape the Anthropic SDK
    returns and replayed through its own `Message` model, so no test reaches the network.
    """

    def __init__(self, *names):
        self.responses = [
            Message.model_validate(json.loads((RESPONSES / f"{name}.json").read_text())) for name in names
        ]
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("the agent asked for more responses than were recorded")
        return self.responses.pop(0)


@pytest.fixture
def replay():
    """The recorded-response stand-in, built with the fixture names to return in order."""
    return Replay


@pytest.fixture
def workorders_db(tmp_path):
    """A freshly built clean work-order database."""
    path = tmp_path / "workorders.sqlite"
    con = sqlite3.connect(path)
    con.executescript((FIXTURES / "workorders.sql").read_text())
    con.commit()
    con.close()
    return path


@pytest.fixture
def write_line_config(workorders_db):
    """The tracer-bullet configuration next to a freshly built clean work-order database."""
    return Path(shutil.copy(FIXTURES / "write_line.yaml", workorders_db.parent))


@pytest.fixture
def scoring_config(workorders_db):
    """The scoring configuration (#40) next to a freshly built clean work-order database."""
    return Path(shutil.copy(FIXTURES / "write_line_scoring.yaml", workorders_db.parent))


@pytest.fixture
def maintenance_config(workorders_db):
    """The maintenance tracer-bullet configuration (#42), with its task file and knowledge base,
    next to a freshly built work-order database."""
    shutil.copytree(FIXTURES / "maintenance", workorders_db.parent, dirs_exist_ok=True)
    return workorders_db.parent / "config.yaml"


@pytest.fixture
def shop_release(tmp_path):
    """A fetched release directory holding one database, `shop`, laid out as LiveSQLBench-Base-Lite:
    the clean SQLite copy, column meanings and a knowledge base (#30)."""
    root = tmp_path / "release"
    folder = root / "shop"
    folder.mkdir(parents=True)
    con = sqlite3.connect(folder / "shop_template.sqlite")
    con.executescript((FIXTURES / "battery_scan.sql").read_text())
    con.commit()
    con.close()
    meanings = {"shop|Orders|Status": "Possible categories: Filled, Cancelled.",
                "shop|Orders|Total": "Net plus tax plus shipping."}
    (folder / "shop_column_meaning_base.json").write_text(json.dumps(meanings))
    (folder / "shop_kb.jsonl").write_text(json.dumps({"id": 0, "knowledge": "Total", "definition": "Net + Tax"}) + "\n")
    return root
