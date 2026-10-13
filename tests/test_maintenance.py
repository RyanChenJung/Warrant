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
from warrant.agent.interface import AgentOutput, AnswerRequest, Response, ResponseKind, Usage
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


class FailsSome:
    """Fails the calls `fails` picks, as a timed-out model call would, and answers the rest by the
    script."""

    def __init__(self, script, fails):
        self._script, self._fails = script, fails

    def answer(self, request, tools):
        if self._fails(request):
            return AgentOutput(None, Usage(), failure="timed out")
        return AgentOutput(self._script(request, tools), Usage())


def edit_task(config_path, change, name=f"{TASK}.yaml"):
    """Apply `change` to the raw contents of a copied task file."""
    task = config_path.parent / name
    raw = yaml.safe_load(task.read_text())
    change(raw)
    task.write_text(yaml.safe_dump(raw))
    return config_path


def with_second_task(config_path, change):
    """Add a second task file to the configuration: a copy of the fixture task with `change` applied."""
    second = config_path.parent / "second.yaml"
    second.write_text((config_path.parent / f"{TASK}.yaml").read_text())
    edit_task(config_path, change, second.name)
    raw = yaml.safe_load(config_path.read_text())
    raw["tasks"].append(second.name)
    config_path.write_text(yaml.safe_dump(raw))
    return config_path


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


def test_every_stored_result_carries_its_executed_result_and_the_self_reported_confidence(config, tmp_path):
    def confident(request, tools):
        return dataclasses.replace(follows_the_store(request, tools), confidence=0.7)

    results = tmp_path / "results.jsonl"
    run(config, ScriptedAgent(confident), PROVENANCE, results)

    records = [json.loads(line) for line in results.read_text().splitlines()]
    assert {r["confidence"] for r in records} == {0.7}
    (stale,) = [r for r in records if (r["condition"], r["state"]) == (STORED, AFTER)]
    assert sorted(map(tuple, stale["executed"])) == [("NORTH", 1815.75), ("SOUTH", 2375.5)]


@pytest.mark.parametrize("sql", ["-- no query", "CREATE TEMP TABLE large AS SELECT 1"])
def test_an_answer_whose_final_sql_returns_no_result_is_wrong_but_came_with_an_error_so_it_is_not_a_silent_error(
    config, sql
):
    result = run(config, answers(sql))
    assert {(r.response_class, r.executed, r.stale_value, r.silent_error) for r in result.rows} == {
        ("wrong_answer", None, False, False)
    }


def test_the_stale_value_rate_weighs_each_task_the_same_whatever_number_of_its_runs_failed(maintenance_config):
    # A second task, the same as the fixture task under another id.
    config = dataclasses.replace(
        load_config(with_second_task(maintenance_config, lambda raw: raw.update(id="other"))), runs=3
    )

    def script(request, tools):
        # The fixture task follows its store; the other task misses both gold results.
        if request.question_id == TASK:
            return follows_the_store(request, tools)
        return Response(ResponseKind.ANSWER, final_sql=spend_over(1000))

    # Two of the fixture task's three runs fail, in both states and under both conditions.
    agent = FailsSome(script, lambda request: request.question_id == TASK and request.run < 2)
    result = run(config, agent)

    # After drift, the fixture task's one scored run is a stale value and none of the other task's
    # three is: 1.0 and 0.0, so 0.5, where pooling the four runs would give 0.25.
    assert result.stale_value_rate[(STORED, AFTER)] == 0.5
    assert result.stale_value_rate[(STORED, BEFORE)] == 0.0


# The validation command, on copies of the fixture task with other gold SQL.


def gold_sql(**sql_per_state):
    """A change to a task file that gives the states named other gold SQL."""

    def change(raw):
        for state, sql in sql_per_state.items():
            raw[state]["gold_sql"] = sql

    return change


def with_gold_sql(config_path, **sql_per_state):
    """Rewrite the copied task file with other gold SQL for the states named."""
    return edit_task(config_path, gold_sql(**sql_per_state))


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
        # Per site, a sum over no rows keeps the site and is NULL.
        (
            spend_over(500),
            "SELECT site, SUM(CASE WHEN total_cost > 5000 THEN total_cost END) FROM workorders GROUP BY site",
            "its post-drift result is empty",
        ),
        (spend_over(500), "DELETE FROM workorders WHERE total_cost > 800", "post_drift gold SQL is not a read-only query"),
        (spend_over(500), "CREATE TEMP TABLE large AS SELECT 1", "post_drift gold SQL is not a read-only query"),
    ],
    ids=["equal", "equal-within-the-tolerance", "empty", "only-null", "null-per-group", "a-write", "no-result"],
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


def test_the_validator_judges_equal_gold_results_within_the_tolerance_the_run_is_given(maintenance_config, capsys):
    # One site total moves 2.6 percent: equal within the default 5 percent, not within 1 percent.
    with_gold_sql(maintenance_config, pre_drift=spend_over(60), post_drift=spend_over(70))

    assert validate.main(["--config", str(maintenance_config)]) == 1
    assert validate.main(["--config", str(maintenance_config), "--tolerance", "0.01"]) == 0
    assert "1 of 1 tasks valid" in capsys.readouterr().out
    assert len(run(load_config(maintenance_config), ScriptedAgent(follows_the_store), tolerance=0.01).rows) == 4


def large_order(version, threshold, id=0):
    return {
        "id": id,
        "version": version,
        "knowledge": LARGE,
        "description": "Which work orders count as large.",
        "definition": f"A work order is large when its total cost is over {threshold}.",
        "type": "domain_knowledge",
        "children_knowledge": -1,
    }


def view(state, *entries):
    """A change to a task file that gives a state's knowledge-base view these entries."""

    def change(raw):
        raw[state]["knowledge_base"] = list(entries)

    return change


def entry_id(new_id):
    """A change to a task file that gives its one entry another id, in its views too."""

    def change(raw):
        raw["entries"][0]["id"] = new_id
        raw[BEFORE]["knowledge_base"][0]["id"] = raw[AFTER]["knowledge_base"][0]["id"] = new_id

    return change


@pytest.mark.parametrize(
    "change, reason",
    [
        # Left out of a view, the entry would show its release text instead.
        (view(BEFORE), "its pre_drift knowledge-base view lists entries [], not its entries [0]"),
        (view(AFTER), "its post_drift knowledge-base view lists entries [], not its entries [0]"),
        # A wrong id would put a second claim in the entry's slot.
        (view(AFTER, large_order(2, 800, id=9)), "its post_drift knowledge-base view lists entries [9], not"),
        (entry_id(9), "entry 9 is not in the workorders knowledge base"),
    ],
    ids=["no-pre-drift-entry", "no-post-drift-entry", "another-post-drift-entry", "an-unknown-entry"],
)
def test_the_validator_rejects_a_task_whose_knowledge_base_views_do_not_hold_exactly_its_entries(
    maintenance_config, capsys, change, reason
):
    edit_task(maintenance_config, change)

    assert validate.main(["--config", str(maintenance_config)]) == 1
    out = capsys.readouterr().out
    assert f"{TASK}: " in out and reason in out


def test_the_validator_rejects_a_task_that_leaves_out_another_entry_in_the_slot_of_one_of_its_entries(
    maintenance_config, capsys
):
    # After drift the full knowledge base would hold entry 0's new threshold and this entry's old one.
    kb = maintenance_config.parent / "workorders_kb.jsonl"
    same_slot = {k: v for k, v in large_order(1, 500, id=3).items() if k != "version"}
    kb.write_text(kb.read_text() + json.dumps(same_slot) + "\n")

    assert validate.main(["--config", str(maintenance_config)]) == 1
    out = capsys.readouterr().out
    assert f"{TASK}: knowledge-base entry 3 is in the slot of entry 0 but is not one of its entries" in out


def test_the_run_refuses_an_undocumented_task_while_a_view_cannot_mark_an_entry_removed_or_under_revision(
    maintenance_config,
):
    # Left out of the post-drift view, the entry would come back with its pre-drift release text.
    def undocumented(raw):
        raw["drift_type"] = "undocumented"
        raw[AFTER]["knowledge_base"] = []

    config = load_config(edit_task(maintenance_config, undocumented))
    agent = ScriptedAgent(follows_the_store)

    with pytest.raises(ValueError, match=f"{TASK}.*undocumented drift is not supported yet"):
        run(config, agent)
    assert agent.requests == []


def test_two_task_files_with_one_id_are_refused_before_any_task_is_validated_or_run(maintenance_config, capsys):
    # A copy of the fixture task kept as a template for another task, its id left unchanged.
    with_second_task(maintenance_config, gold_sql(pre_drift=spend_over(900), post_drift=spend_over(1000)))

    with pytest.raises(SystemExit) as exited:
        validate.main(["--config", str(maintenance_config)])
    assert exited.value.code == 2
    assert f"task ids used more than once: {TASK}" in capsys.readouterr().err
    with pytest.raises(ValueError, match=f"task ids used more than once: {TASK}"):
        load_config(maintenance_config)
