import dataclasses
import json
import sqlite3

import anthropic
import httpx2 as httpx
import pytest

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import AgentOutput, AnswerRequest, Response, ResponseKind, Usage
from warrant.agent.tools import ReadOnlySQL
from warrant.data.sqlite import query_with_columns
from warrant.store.claims import ClaimKind, Slot, Source, WarrantKind
from warrant.store.results import Provenance
from warrant.write_line.config import load_config
from warrant.write_line.run import run

OPEN_ORDERS_SLOT = Slot(ClaimKind.COVERAGE, "workorders")

PROVENANCE = Provenance(
    config_hash="0" * 64,
    repo_commit="abc1234",
    model="anthropic.claude-model-placeholder",
    prompt_version="1",
)

# What an agent would write without and with the coverage claim in its knowledge store.
SQL_WITHOUT_CLAIM = {
    "open-orders": "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'",
    "open-order-hours": "SELECT SUM(t.hours) FROM tasks t JOIN workorders w USING (wonum) WHERE w.status = 'OPEN'",
    "closed-cost": "SELECT SUM(total_cost) FROM workorders WHERE status = 'CLOSED'",
}
SQL_WITH_CLAIM = {
    "open-orders": "SELECT COUNT(DISTINCT wonum) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)",
    "open-order-hours": "SELECT SUM(hours) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)",
    "closed-cost": "SELECT SUM(total_cost) FROM workorders WHERE status = 'CLOSED'",
}


def knows_the_claim(request, tools):
    """Answers with the SQL that matches what the store tells it, after running it through the tool."""
    knows = any(claim.slot == OPEN_ORDERS_SLOT for claim in request.store.claims)
    sql = (SQL_WITH_CLAIM if knows else SQL_WITHOUT_CLAIM)[request.question_id]
    return Response(ResponseKind.ANSWER, final_sql=sql, value=tools["sql"](sql))


def rows(path, sql):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.fixture
def config(write_line_config):
    return load_config(write_line_config)


def test_run_returns_a_results_row_per_question_rule_and_run_and_accuracy_per_rule(config, tmp_path):
    result = run(config, ScriptedAgent(knows_the_claim), tmp_path / "work")
    assert len(result.rows) == 3 * 2 * 1
    assert {(r.question_id, r.rule, r.run) for r in result.rows} == {
        (q, rule, 0) for q in SQL_WITH_CLAIM for rule in ("empty", "all_person")
    }
    assert {r.response_class for r in result.rows} <= {"correct_answer", "wrong_answer"}
    assert set(result.accuracy) == {"empty", "all_person"}


def test_the_reference_claim_raises_accuracy_over_the_empty_store(config, tmp_path):
    result = run(config, ScriptedAgent(knows_the_claim), tmp_path / "work")
    assert result.accuracy == {"empty": pytest.approx(1 / 3), "all_person": 1.0}


def test_the_clean_database_is_unchanged_and_the_defect_is_injected_into_a_copy(config, tmp_path):
    clean = config.databases["workorders"]
    before = clean.read_bytes()
    result = run(config, ScriptedAgent(knows_the_claim), tmp_path / "work")
    assert clean.read_bytes() == before
    injected = result.injected["workorders"]
    assert injected != clean
    assert rows(injected, "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'") == [(0,)]
    assert rows(clean, "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'") == [(4,)]


def test_gold_answers_are_computed_on_the_injected_copy_and_stored_with_their_sql(config, tmp_path):
    result = run(config, ScriptedAgent(knows_the_claim), tmp_path / "work")
    gold = result.gold["open-orders"]
    assert gold.sql == SQL_WITH_CLAIM["open-orders"]
    assert gold.rows == [(4,)]
    assert rows(config.databases["workorders"], gold.sql) == [(0,)]
    assert result.gold["open-order-hours"].rows == [(16.25,)]


def test_the_agent_gets_the_schema_the_store_and_only_a_read_only_sql_tool(config, tmp_path):
    offered = []

    def script(request, tools):
        offered.append(tools)
        return knows_the_claim(request, tools)

    agent = ScriptedAgent(script)
    run(config, agent, tmp_path / "work")
    request = agent.requests[0]
    assert {f.name for f in dataclasses.fields(AnswerRequest)} == {
        "database", "question_id", "question", "run", "schema", "store", "tools",
    }
    assert request.tools == ("sql",)
    assert "CREATE TABLE workorders" in request.schema
    assert set(offered[0]) == {"sql"}
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        offered[0]["sql"]("DELETE FROM tasks")


def test_the_pipeline_scores_the_re_executed_final_sql_not_the_stated_value(config, tmp_path):
    def right_value_wrong_sql(request, tools):
        gold_like = knows_the_claim(request, tools)
        return Response(ResponseKind.ANSWER, final_sql=SQL_WITHOUT_CLAIM[request.question_id], value=gold_like.value)

    result = run(config, ScriptedAgent(right_value_wrong_sql), tmp_path / "work")
    assert result.accuracy["all_person"] == pytest.approx(1 / 3)


def test_the_person_store_holds_the_reference_claim_and_requests_never_name_the_rule(config, tmp_path):
    agent = ScriptedAgent(knows_the_claim)
    result = run(config, agent, tmp_path / "work")

    (claim,) = result.stores["all_person"]["workorders"].claims
    assert claim.statement == config.defects[0].reference_claim
    assert claim.slot == OPEN_ORDERS_SLOT
    assert claim.source == Source.PERSON
    assert claim.warrant == WarrantKind.NONE
    assert claim.toulmin.backing == "the person"
    assert result.stores["empty"]["workorders"].claims == ()

    by_question = {}
    for request in agent.requests:
        assert "all_person" not in repr(request)
        by_question.setdefault(request.question_id, []).append(dataclasses.replace(request, store=None))
    assert all(a == b for a, b in by_question.values())


def test_a_failing_final_sql_is_scored_wrong(config, tmp_path):
    def broken(request, tools):
        return Response(ResponseKind.ANSWER, final_sql="SELECT no_such_column FROM workorders")

    result = run(config, ScriptedAgent(broken), tmp_path / "work")
    assert {r.response_class for r in result.rows} == {"wrong_answer"}
    assert all(r.executed is None for r in result.rows)


class FailsOneQuestion:
    """An agent whose call fails on one question: recorded as a failure, never scored."""

    def answer(self, request, tools):
        if request.question_id == "closed-cost":
            return AgentOutput(None, Usage(1200, 20), failure="malformed output after 2 attempts")
        return AgentOutput(knows_the_claim(request, tools), Usage(1200, 90))


def test_a_failed_call_is_recorded_as_a_failure_and_left_out_of_the_accuracy(config, tmp_path):
    result = run(config, FailsOneQuestion(), tmp_path / "work")

    failed = [r for r in result.rows if r.response_class == "failed"]
    assert [r.question_id for r in failed] == ["closed-cost", "closed-cost"]
    assert all(r.final_sql is None and r.executed is None for r in failed)
    assert all(r.usage.input_tokens == 1200 for r in result.rows)
    # Two scored rows per rule. The failure is left out of both numerator and denominator, so the
    # empty store drops from 1/3 to 0/2: its one correct answer was the question that failed.
    assert result.accuracy == {"empty": 0.0, "all_person": 1.0}


def test_a_rule_whose_every_call_failed_has_no_accuracy_to_report(config, tmp_path):
    class AlwaysFails:
        def answer(self, request, tools):
            return AgentOutput(None, Usage(), failure="malformed output after 2 attempts")

    result = run(config, AlwaysFails(), tmp_path / "work")
    assert {r.response_class for r in result.rows} == {"failed"}
    assert result.accuracy == {"empty": None, "all_person": None}


def test_a_misconfigured_model_stops_the_run_without_storing_a_row(config, tmp_path):
    """A failure that is wrong for every question is not worth a record per question."""
    results = tmp_path / "results.jsonl"

    class Misconfigured:
        def answer(self, request, tools):
            raise anthropic.AuthenticationError(
                "unauthorized",
                response=httpx.Response(401, request=httpx.Request("POST", "http://example.invalid")),
                body=None,
            )

    with pytest.raises(anthropic.AuthenticationError):
        run(config, Misconfigured(), tmp_path / "work", PROVENANCE, results)

    # The run's start record and its two stores are stored; no answer is.
    assert [json.loads(line)["record"] for line in results.read_text().splitlines()] == ["start", "store", "store"]


def test_every_stored_result_carries_the_provenance_of_its_run(config, tmp_path):
    results = tmp_path / "results.jsonl"
    result = run(config, ScriptedAgent(knows_the_claim), tmp_path / "work", PROVENANCE, results)

    records = [r for r in map(json.loads, results.read_text().splitlines()) if r["record"] == "answer"]
    assert len(records) == len(result.rows)
    assert {r["model"] for r in records} == {"anthropic.claude-model-placeholder"}
    assert {r["prompt_version"] for r in records} == {"1"}
    assert {r["repo_commit"] for r in records} == {"abc1234"}
    assert records[0]["question_id"] and records[0]["rule"] and records[0]["response_class"]
    assert records[0]["input_tokens"] == 0 and records[0]["output_tokens"] == 0


def test_every_stored_answer_carries_its_executed_result_its_stated_value_and_the_self_reported_confidence(
    config, tmp_path
):
    # The pilot's records held only the final SQL, so its values had to be re-executed (#49).
    def confident(request, tools):
        return dataclasses.replace(knows_the_claim(request, tools), confidence=0.7)

    results = tmp_path / "results.jsonl"
    result = run(config, ScriptedAgent(confident), tmp_path / "work", PROVENANCE, results)

    records = [r for r in map(json.loads, results.read_text().splitlines()) if r["record"] == "answer"]
    (injected,) = result.injected.values()
    assert {r["confidence"] for r in records} == {0.7}
    for record in records:
        columns, executed = query_with_columns(injected, record["final_sql"])
        assert list(map(tuple, record["executed"])) == executed
        assert record["executed_columns"] == list(columns)
        # The scripted agent states what the SQL tool returned.
        assert record["value"] == json.loads(json.dumps(ReadOnlySQL(injected)(record["final_sql"])))


def test_a_stored_refusal_carries_what_it_says_is_missing_and_what_it_offers_instead(config, tmp_path):
    def refuses(request, tools):
        return Response(ResponseKind.REFUSAL, missing="the order status", alternative="the open tasks", confidence=0.4)

    results = tmp_path / "results.jsonl"
    run(config, ScriptedAgent(refuses), tmp_path / "work", PROVENANCE, results)

    records = [r for r in map(json.loads, results.read_text().splitlines()) if r["record"] == "answer"]
    assert {
        (r["missing"], r["alternative"], r["confidence"], r["executed"], r["executed_columns"]) for r in records
    } == {("the order status", "the open tasks", 0.4, None, None)}


def test_a_stored_clarification_request_carries_its_question(config, tmp_path):
    def asks(request, tools):
        return Response(ResponseKind.CLARIFICATION, clarification="Do open work orders count?", confidence=0.3)

    results = tmp_path / "results.jsonl"
    run(config, ScriptedAgent(asks), tmp_path / "work", PROVENANCE, results)

    records = [r for r in map(json.loads, results.read_text().splitlines()) if r["record"] == "answer"]
    assert {(r["response_class"], r["clarification"], r["value"]) for r in records} == {
        ("clarification_request", "Do open work orders count?", None)
    }
