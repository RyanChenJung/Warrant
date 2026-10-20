"""A write-line configuration on a committed freeze (#49): the defects and the global part come from
the freeze, the run's databases must be the recorded injection's, and answers are scored with the
freeze's numeric tolerance. The freeze here is the whole-freeze fixture of the predicted outcomes,
on copies of the work-order fixture."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from warrant.agent.fake import ScriptedAgent
from warrant.agent.interface import Response, ResponseKind
from warrant.data.release import sha256
from warrant.defects.build import build
from warrant.defects.inject import load_defect
from warrant.freeze.validate import clean_databases
from warrant.scoring.classify import ResponseClass
from warrant.write_line.config import load_config
from warrant.write_line.run import run

FIXTURES = Path(__file__).parent / "fixtures"
CLOSED_COST = "SELECT SUM(total_cost) FROM workorders WHERE status = 'CLOSED'"
QUESTIONS = [
    {
        "id": "open-orders",
        "database": "depot",
        "defect": "open-orders-cut",
        "text": "How many open work orders are there?",
        "gold_sql": "SELECT COUNT(DISTINCT wonum) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)",
    },
    {"id": "closed-cost", "database": "depot", "defect": None, "text": "What do closed work orders cost?", "gold_sql": CLOSED_COST},
]


@pytest.fixture
def freeze(workorders_db):
    """The whole-freeze fixture next to the clean work-order database its `databases:` name."""
    return Path(shutil.copy(FIXTURES / "freeze_predictions.yaml", workorders_db.parent))


def injection_record(freeze, out, **change):
    """The record the builder writes for a build of `freeze`, as JSON next to the freeze."""
    raw = yaml.safe_load(freeze.read_text())
    built = build([load_defect(d) for d in raw["defects"]], clean_databases(raw, freeze), out)
    record = {
        "outcome": "built",
        "freeze_sha256": sha256(freeze),
        "injected": built.injected,
        "readings": built.readings,
        "drift": {d: {"reading": r, "type": t.value} for d, (r, t) in built.drift.items()},
        **change,
    }
    path = freeze.parent / "injection.json"
    path.write_text(json.dumps(record))
    return path


def configuration(freeze, **extra):
    path = freeze.parent / "pilot.yaml"
    raw = {"freeze": freeze.name, "rules": ["empty", "all_person"], "runs": 1, "questions": QUESTIONS, **extra}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


def answers(sql_for):
    def answer(request, tools):
        sql = sql_for(request)
        return Response(ResponseKind.ANSWER, final_sql=sql, value=tools["sql"](sql))

    return ScriptedAgent(answer)


def test_a_configuration_naming_a_freeze_takes_its_defects_global_part_and_clean_copies_from_it(freeze):
    config = load_config(configuration(freeze))
    raw = yaml.safe_load(freeze.read_text())
    assert [d.id for d in config.defects] == [d["id"] for d in raw["defects"]]
    assert config.global_part == raw["global"]
    assert config.databases == clean_databases(raw, freeze)
    assert config.injection is None


@pytest.mark.parametrize("own", ["defects", "global", "databases"])
def test_a_configuration_naming_a_freeze_may_not_give_its_own_defects_global_part_or_databases(freeze, own):
    with pytest.raises(ValueError, match="takes its defects, global part and databases from"):
        load_config(configuration(freeze, **{own: {}}))


def test_an_injection_record_needs_the_freeze_it_was_built_from(write_line_config, tmp_path):
    raw = yaml.safe_load(write_line_config.read_text())
    write_line_config.write_text(yaml.safe_dump({**raw, "injection": "injection.json"}))
    with pytest.raises(ValueError, match="needs the freeze"):
        load_config(write_line_config)


@pytest.mark.parametrize(
    "change, reason",
    [({"outcome": "failed"}, "outcome is 'failed'"), ({"freeze_sha256": "0" * 64}, "not of this freeze")],
    ids=["not-built", "another-freeze"],
)
def test_an_injection_record_that_is_not_a_built_record_of_this_freeze_is_refused(freeze, tmp_path, change, reason):
    record = injection_record(freeze, tmp_path / "recorded", **change)
    with pytest.raises(ValueError, match=reason):
        load_config(configuration(freeze, injection=record.name))


def test_the_run_goes_ahead_on_databases_identical_to_the_recorded_injections(freeze, tmp_path):
    record = injection_record(freeze, tmp_path / "recorded")
    config = load_config(configuration(freeze, injection=record.name))
    result = run(config, answers(lambda r: CLOSED_COST), tmp_path / "work")
    assert len(result.rows) == len(QUESTIONS) * 2
    assert config.injection["injected"] == {name: path.stem for name, path in result.injected.items()}


def test_databases_other_than_the_recorded_injections_stop_the_run_before_any_agent_call(freeze, tmp_path):
    record = injection_record(freeze, tmp_path / "recorded")
    tampered = json.loads(record.read_text())
    tampered["injected"]["depot"] = "0" * 64
    record.write_text(json.dumps(tampered))
    calls = []
    agent = answers(lambda r: calls.append(r) or CLOSED_COST)
    with pytest.raises(ValueError, match="not the recorded injection's: the injected copy of 'depot'"):
        run(load_config(configuration(freeze, injection=record.name)), agent, tmp_path / "work")
    assert calls == []


def test_answers_are_scored_with_the_freezes_numeric_tolerance(freeze, tmp_path):
    """3 percent off the gold answer: wrong under the freeze's 1 percent, right when the run is given
    5 percent, the scorer's default."""
    off = "SELECT SUM(total_cost) * 1.03 FROM workorders WHERE status = 'CLOSED'"
    result = run(load_config(configuration(freeze)), answers(lambda r: off), tmp_path / "work")
    closed = [row for row in result.rows if row.question_id == "closed-cost"]
    assert {row.response_class for row in closed} == {ResponseClass.WRONG_ANSWER}
    explicit = run(load_config(configuration(freeze)), answers(lambda r: off), tmp_path / "work2", tolerance=0.05)
    assert {row.response_class for row in explicit.rows if row.question_id == "closed-cost"} == {ResponseClass.CORRECT_ANSWER}
