"""The maintenance line's entry point (#42), on one documented constant-change task.

The fixture task (`fixtures/maintenance/large-order-spend.yaml`) runs on the work-order fixture: a
large work order costs more than 500 before drift and more than 800 after it. The database stays
the same; only the knowledge-base entry and the gold SQL change.
"""

import dataclasses
import json
import re

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import AnswerRequest, Response, ResponseKind
from warrant.data.sqlite import query
from warrant.maintenance import validate
from warrant.maintenance.config import load_config
from warrant.maintenance.run import run
from warrant.store.claims import Source, Toulmin, WarrantKind
from warrant.store.results import Provenance

TASK = "large-order-spend"
FULL = "full_knowledge_base"
STORED = "stored_answer_without_tools"
BEFORE, AFTER = "pre_drift", "post_drift"
LARGE = "Large work order"

PROVENANCE = Provenance(
    config_hash="0" * 64,
    repo_commit="abc1234",
    model="anthropic.claude-model-placeholder",
    prompt_version="1",
)


def spend_over(threshold):
    return f"SELECT site, SUM(total_cost) FROM workorders WHERE total_cost > {threshold} GROUP BY site"


def threshold(claim):
    return int(re.search(r"over (\d+)", claim.statement).group(1))


def follows_the_store(request, tools):
    """Writes the SQL that the large-work-order threshold in its store gives, and runs it only when
    the request offers the SQL tool."""
    (claim,) = [c for c in request.store.claims if c.slot.subject == LARGE]
    sql = spend_over(threshold(claim))
    value = tools["sql"](sql) if "sql" in request.tools else None
    return Response(ResponseKind.ANSWER, final_sql=sql, value=value)


def answers(sql):
    return ScriptedAgent(lambda request, tools: Response(ResponseKind.ANSWER, final_sql=sql))


def rows_of(result, condition, state):
    return [r for r in result.rows if r.condition == condition and r.state == state]


@pytest.fixture
def config(maintenance_config):
    return load_config(maintenance_config)


def test_run_returns_a_results_row_per_task_condition_state_and_run(config):
    result = run(config, ScriptedAgent(follows_the_store))
    assert sorted((r.task, r.condition, r.state, r.run) for r in result.rows) == sorted(
        (TASK, condition, state, 0) for condition in (FULL, STORED) for state in (BEFORE, AFTER)
    )


def test_the_stored_answer_without_tools_is_right_before_drift_and_a_stale_value_after_it(config):
    result = run(config, ScriptedAgent(follows_the_store))
    # The full knowledge base in the prompt is right in both states.
    assert result.accuracy == {(FULL, BEFORE): 1.0, (FULL, AFTER): 1.0, (STORED, BEFORE): 1.0, (STORED, AFTER): 0.0}
    assert result.stale_value_rate == {
        (FULL, BEFORE): 0.0,
        (FULL, AFTER): 0.0,
        (STORED, BEFORE): 0.0,
        (STORED, AFTER): 1.0,
    }


def test_a_stale_value_after_drift_given_without_an_escalation_is_a_silent_error(config):
    result = run(config, ScriptedAgent(follows_the_store))
    (stale,) = rows_of(result, STORED, AFTER)
    assert (stale.response_class, stale.stale_value, stale.silent_error) == ("wrong_answer", True, True)
    others = [r for r in result.rows if r is not stale]
    assert {(r.response_class, r.stale_value, r.silent_error) for r in others} == {("correct_answer", False, False)}


def test_a_wrong_answer_after_drift_that_misses_the_pre_drift_gold_result_too_is_a_silent_error_not_a_stale_value(
    config,
):
    result = run(config, answers(spend_over(1000)))
    after = rows_of(result, FULL, AFTER) + rows_of(result, STORED, AFTER)
    assert {(r.response_class, r.stale_value, r.silent_error) for r in after} == {("wrong_answer", False, True)}
    assert result.stale_value_rate[(STORED, AFTER)] == 0.0


def test_without_tools_the_agent_is_offered_none_and_the_sql_it_never_ran_is_executed_and_scored(config):
    calls = []

    def script(request, tools):
        calls.append((request, tools))
        return follows_the_store(request, tools)

    result = run(config, ScriptedAgent(script))
    offered = [(request.tools, set(tools)) for request, tools in calls]
    assert sorted(offered) == [((), set()), ((), set()), (("sql",), {"sql"}), (("sql",), {"sql"})]
    (before,) = rows_of(result, STORED, BEFORE)
    assert sorted(before.executed) == [("NORTH", 1815.75), ("SOUTH", 2375.5)]
    assert before.response_class == "correct_answer"


def test_requests_carry_the_store_and_the_tool_set_but_never_the_condition_or_the_task_state(config):
    agent = ScriptedAgent(follows_the_store)
    run(config, agent)

    assert {f.name for f in dataclasses.fields(AnswerRequest)} == {
        "database", "question_id", "question", "run", "schema", "store", "tools",
    }
    assert len(agent.requests) == 4
    for request in agent.requests:
        for name in (FULL, STORED, BEFORE, AFTER):
            assert name not in repr(request)
    # Apart from the store and the tool set, the four requests for the task are the same.
    assert len({dataclasses.replace(r, store=None, tools=None) for r in agent.requests}) == 1
    assert {r.question_id for r in agent.requests} == {TASK}


def test_the_full_knowledge_base_holds_every_entry_as_a_record_warranted_claim_of_its_states_version(config):
    agent = ScriptedAgent(follows_the_store)
    run(config, agent)

    stores = [r.store for r in agent.requests if r.tools == ("sql",)]
    assert len(stores) == 2
    for store in stores:
        assert [c.slot.subject for c in store.claims] == [LARGE, "Open work order", "Task hours"]
        assert {(c.warrant, c.source) for c in store.claims} == {(WarrantKind.RECORD, Source.PERSON)}
    # The entry the task depends on, in each state's version; another entry, as released.
    large = {(c.toulmin.backing, threshold(c)) for s in stores for c in s.claims if c.slot.subject == LARGE}
    assert large == {("knowledge base entry 0, version 1", 500), ("knowledge base entry 0, version 2", 800)}
    released = {c.toulmin.backing for s in stores for c in s.claims if c.slot.subject == "Open work order"}
    assert released == {"knowledge base entry 1, version 1"}


def test_the_stored_answer_holds_the_pre_drift_value_in_both_states_with_no_warrant_source_or_version(config):
    agent = ScriptedAgent(follows_the_store)
    run(config, agent)

    stores = [r.store for r in agent.requests if r.tools == ()]
    assert len(stores) == 2 and stores[0] == stores[1]
    (claim,) = stores[0].claims
    assert claim.statement == "A large work order is one whose total cost is over 500."
    assert claim.slot.subject == LARGE
    assert claim.warrant == WarrantKind.NONE
    assert claim.toulmin == Toulmin()


def test_every_stored_result_carries_its_provenance_and_its_stale_value_and_silent_error_flags(config, tmp_path):
    results = tmp_path / "results.jsonl"
    result = run(config, ScriptedAgent(follows_the_store), PROVENANCE, results)

    records = [json.loads(line) for line in results.read_text().splitlines()]
    assert len(records) == len(result.rows) == 4
    assert {(r["model"], r["prompt_version"], r["repo_commit"]) for r in records} == {
        ("anthropic.claude-model-placeholder", "1", "abc1234")
    }
    assert [(r["task"], r["condition"], r["state"]) for r in records if r["stale_value"]] == [(TASK, STORED, AFTER)]
    assert [(r["condition"], r["state"]) for r in records if r["silent_error"]] == [(STORED, AFTER)]
    assert {r["escalations"] for r in records} == {0}


# The validation command, on copies of the fixture task with other gold SQL.


def with_gold_sql(config_path, **gold_sql):
    """Rewrite the copied task file with other gold SQL for the states named."""
    task = config_path.parent / f"{TASK}.yaml"
    raw = yaml.safe_load(task.read_text())
    for state, sql in gold_sql.items():
        raw[state]["gold_sql"] = sql
    task.write_text(yaml.safe_dump(raw))
    return config_path


def test_the_validator_accepts_the_fixture_task(maintenance_config, capsys):
    assert validate.main(["--config", str(maintenance_config)]) == 0
    assert "1 of 1 tasks valid" in capsys.readouterr().out


@pytest.mark.parametrize(
    "pre_drift, post_drift, reason",
    [
        # The same work orders cost more than 501 as more than 500.
        (spend_over(500), spend_over(501), "its two gold results are equal"),
        # One order of 64.25 drops out of a site total of 2,514.75: 2.6 percent, within the
        # tolerance, so a stale answer would still be scored correct.
        (spend_over(60), spend_over(70), "its two gold results are equal"),
        (spend_over(500), spend_over(5000), "its post-drift result is empty"),
        # A sum over no rows is one NULL.
        (
            "SELECT SUM(total_cost) FROM workorders WHERE total_cost > 500",
            "SELECT SUM(total_cost) FROM workorders WHERE total_cost > 5000",
            "its post-drift result is empty",
        ),
        (spend_over(500), "DELETE FROM workorders WHERE total_cost > 800", "post_drift gold SQL is not a read-only query"),
        (spend_over(500), "CREATE TEMP TABLE large AS SELECT 1", "post_drift gold SQL is not a read-only query"),
    ],
    ids=["equal", "equal-within-the-tolerance", "empty", "only-null", "a-write", "no-result"],
)
def test_the_validator_rejects_an_invalid_task_and_leaves_the_database_unchanged(
    maintenance_config, workorders_db, capsys, pre_drift, post_drift, reason
):
    with_gold_sql(maintenance_config, pre_drift=pre_drift, post_drift=post_drift)

    assert validate.main(["--config", str(maintenance_config)]) == 1
    out = capsys.readouterr().out
    assert f"{TASK}: " in out and reason in out
    assert "0 of 1 tasks valid" in out
    assert query(workorders_db, "SELECT COUNT(*) FROM workorders") == [(12,)]


def test_the_run_refuses_an_invalid_task_before_any_agent_call(maintenance_config):
    config = load_config(with_gold_sql(maintenance_config, post_drift=spend_over(501)))
    agent = ScriptedAgent(follows_the_store)

    with pytest.raises(ValueError, match=f"{TASK}.*two gold results are equal"):
        run(config, agent)
    assert agent.requests == []
