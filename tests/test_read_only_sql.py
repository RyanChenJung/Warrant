import sqlite3
from pathlib import Path

import pytest

from warrant.agent.interface import Response, ResponseKind
from warrant.agent.tools import ReadOnlySQL
from warrant.data.sqlite import query, schema
from warrant.scoring.classify import execute

# Statements that write a file or change state even on a connection opened read-only.
ESCAPES = [
    "VACUUM INTO 'copy.sqlite'",
    "ATTACH DATABASE 'attached.sqlite' AS attached",
    "CREATE TEMP TABLE scratch (x)",
    "PRAGMA journal_mode = WAL",
    "DELETE FROM tasks",
    "INSERT INTO tasks (wonum, description, hours) VALUES ('WO-1001', 'Extra', 1.0)",
    "UPDATE workorders SET total_cost = 0",
    "DROP TABLE tasks",
]

READS = {
    "join": "SELECT COUNT(*) FROM tasks t JOIN workorders w USING (wonum) WHERE w.status = 'OPEN'",
    "cte": "WITH open AS (SELECT wonum FROM workorders WHERE status = 'OPEN') SELECT COUNT(*) FROM open",
    "recursive cte": "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 3) SELECT SUM(i) FROM n",
    "window": "SELECT wonum, RANK() OVER (ORDER BY total_cost DESC) FROM workorders LIMIT 1",
    "functions": "SELECT ROUND(SUM(total_cost), 1), COALESCE(MAX(site), ''), strftime('%Y', MIN(reported_date)) FROM workorders",
    "subquery": "SELECT COUNT(*) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders WHERE status = 'CLOSED')",
}


@pytest.fixture
def database(tmp_path, monkeypatch):
    """The work-order fixture, read-only on disk, with the working directory set beside it."""
    path = tmp_path / "workorders.sqlite"
    con = sqlite3.connect(path)
    con.executescript((Path(__file__).parent / "fixtures" / "workorders.sql").read_text())
    con.close()
    path.chmod(0o444)
    monkeypatch.chdir(tmp_path)
    return path


def files_beside(path):
    return sorted(p.name for p in path.parent.iterdir())


@pytest.mark.parametrize("sql", ESCAPES)
def test_a_statement_that_does_more_than_read_is_refused_and_leaves_no_trace(database, sql):
    before = database.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        query(database, sql)
    assert files_beside(database) == ["workorders.sqlite"]
    assert database.read_bytes() == before


@pytest.mark.parametrize("name", READS)
def test_reads_still_work(database, name):
    assert query(database, READS[name])


def test_the_schema_the_agent_sees_is_still_read(database):
    assert "CREATE TABLE workorders" in schema(database)


def test_the_agents_sql_tool_cannot_copy_the_database_out(database):
    with pytest.raises(sqlite3.DatabaseError):
        ReadOnlySQL(database)("VACUUM INTO 'copy.sqlite'")
    assert files_beside(database) == ["workorders.sqlite"]


def test_a_final_sql_that_writes_a_file_is_not_executed_by_the_pipeline(database):
    response = Response(ResponseKind.ANSWER, final_sql="VACUUM INTO 'copy.sqlite'")
    assert execute(database, response.final_sql) is None
    assert files_beside(database) == ["workorders.sqlite"]
