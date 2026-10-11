import shutil
import sqlite3
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def write_line_config(tmp_path):
    """The tracer-bullet configuration next to a freshly built clean work-order database."""
    con = sqlite3.connect(tmp_path / "workorders.sqlite")
    con.executescript((FIXTURES / "workorders.sql").read_text())
    con.commit()
    con.close()
    return Path(shutil.copy(FIXTURES / "write_line.yaml", tmp_path))
