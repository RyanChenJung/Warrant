"""A write-line configuration on a committed freeze (#49): the defects and the global part come from
the freeze, the run's databases must be the recorded injection's, answers are scored with the
freeze's numeric tolerance, and every probe names the readings it separates, each with the SQL that
answers it under that reading (#34, round 2). The freeze here is the whole-freeze fixture of the
predicted outcomes, on copies of the work-order fixture."""

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
from warrant.write_line.run import main, run

FIXTURES = Path(__file__).parent / "fixtures"
CLOSED_COST = "SELECT SUM(total_cost) FROM workorders WHERE status = 'CLOSED'"
QUESTIONS = [
    {
        "id": "open-orders",
        "database": "depot",
        "defect": "open-orders-cut",
        "text": "How many open work orders are there?",
        "gold_sql": "SELECT COUNT(DISTINCT wonum) FROM tasks WHERE wonum NOT IN (SELECT wonum FROM workorders)",
        # Read as if nothing was cut, the work-order table holds every order: none of them open.
        "separates": {"nothing-cut": "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'"},
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


# The probes' reading tags (#34, round 2): each probe of a defect with a reading set names the
# readings it separates, with the SQL that answers it under each, and every such answer is more than
# 2 percent from the gold answer on the injected copy.


def with_probe(**change):
    probe = {**QUESTIONS[0], **change}
    return [probe, QUESTIONS[1]]


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"separates": None}, "names no reading it separates"),
        ({"separates": {"parent-cut": "SELECT 0"}}, "'parent-cut' is the true reading"),
        ({"separates": {"no-such-reading": "SELECT 0"}}, "'no-such-reading' is not a reading of open-orders-cut"),
        ({"separates": {"nothing-cut": QUESTIONS[0]["gold_sql"]}}, "within 2 percent of the gold answer under reading 'nothing-cut'"),
        ({"separates": {"nothing-cut": "SELECT 4.05"}}, "within 2 percent of the gold answer under reading 'nothing-cut'"),
        ({"separates": {"nothing-cut": "SELECT * FROM no_such_table"}}, "its SQL for reading 'nothing-cut' fails"),
    ],
    ids=["untagged", "true-reading", "unknown-reading", "same-answer", "within-2-percent", "failing-sql"],
)
def test_a_probe_whose_reading_tags_do_not_separate_stops_the_run_before_any_agent_call(freeze, tmp_path, change, reason):
    probe = {k: v for k, v in {**QUESTIONS[0], **change}.items() if v is not None}
    calls = []
    agent = answers(lambda r: calls.append(r) or CLOSED_COST)
    with pytest.raises(ValueError, match=reason):
        run(load_config(configuration(freeze, questions=[probe, QUESTIONS[1]])), agent, tmp_path / "work")
    assert calls == []


def test_an_answer_just_over_2_percent_from_the_gold_answer_separates(freeze, tmp_path):
    """The gold answer is 4 open orders; 4.1 is 2.5 percent off."""
    config = load_config(configuration(freeze, questions=with_probe(separates={"nothing-cut": "SELECT 4.1"})))
    assert len(run(config, answers(lambda r: CLOSED_COST), tmp_path / "work").rows) == 4


@pytest.mark.parametrize("question", [QUESTIONS[1], {**QUESTIONS[1], "gold_sql": None, "missing_terms": ["x"]}], ids=["control", "refusal"])
def test_only_a_probe_with_a_gold_answer_can_name_readings_it_separates(freeze, question):
    with pytest.raises(ValueError, match="only a probe with a gold answer"):
        load_config(configuration(freeze, questions=[QUESTIONS[0], {**question, "separates": {"nothing-cut": "SELECT 0"}}]))


def test_the_check_command_prints_each_probes_answers_under_its_readings_with_no_model_call(freeze, tmp_path, capsys):
    record = injection_record(freeze, tmp_path / "recorded")
    path = configuration(freeze, injection=record.name)
    assert main(["--config", str(path), "--work-dir", str(tmp_path / "work"), "--check"]) == 0
    out = capsys.readouterr().out
    assert "open-orders" in out and "gold: [(4,)]" in out and "nothing-cut: [(0,)]" in out
    assert "0 problems" in out


def test_the_check_command_fails_on_a_probe_that_does_not_separate(freeze, tmp_path, capsys):
    path = configuration(freeze, questions=with_probe(separates={"nothing-cut": "SELECT 4"}))
    assert main(["--config", str(path), "--work-dir", str(tmp_path / "work"), "--check"]) == 1
    assert "within 2 percent" in capsys.readouterr().out


def test_the_check_command_fails_on_a_control_whose_gold_answer_differs_on_the_injected_copy_and_prints_both(
    freeze, tmp_path, capsys
):
    # The cut removes the open work orders, so counting every work order is no control.
    control = {**QUESTIONS[1], "id": "all-orders", "gold_sql": "SELECT COUNT(*) FROM workorders"}
    path = configuration(freeze, questions=[QUESTIONS[0], control])
    assert main(["--config", str(path), "--work-dir", str(tmp_path / "work"), "--check"]) == 1
    out = capsys.readouterr().out
    assert "a control question whose gold answer differs between clean and injected copy" in out
    assert "all-orders: gold: [(8,)]\n  clean copy: [(12,)]\n" in out, out


@pytest.mark.parametrize("defect", ["open-order-cut", "Open-Orders-Cut"])
def test_a_question_naming_a_defect_the_configuration_does_not_have_is_refused_when_loaded(freeze, defect):
    # A misspelled id would make the probe look like neither a probe of a defect with a reading set
    # nor a control, and skip both checks.
    with pytest.raises(ValueError, match=f"a defect the configuration does not have: open-orders \\('{defect}'\\)"):
        load_config(configuration(freeze, questions=with_probe(defect=defect)))


@pytest.mark.parametrize("defect", [["open-orders-cut"], "", 3])
def test_a_question_whose_defect_is_not_one_defect_id_is_refused_when_loaded(freeze, defect):
    with pytest.raises(ValueError, match="defect must be one defect id"):
        load_config(configuration(freeze, questions=with_probe(defect=defect)))


def test_a_question_naming_an_unknown_defect_is_refused_without_a_freeze_too(write_line_config):
    raw = yaml.safe_load(write_line_config.read_text())
    raw["questions"][0]["defect"] = "open-order-cut"
    write_line_config.write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(ValueError, match="a defect the configuration does not have"):
        load_config(write_line_config)


def test_the_pilot_configuration_is_eight_coverage_probes_on_the_committed_freeze_with_its_model_settings():
    """The pilot (#49): the probes of orders-cut under the empty store and everything from a person, once,
    with the settings the freeze requires before the first model call on its defects."""
    config = load_config(Path(__file__).parents[1] / "configs" / "write_line_pilot.yaml")
    assert [q.defect for q in config.questions] == ["orders-cut"] * 8
    assert all(q.separates for q in config.questions)
    assert config.rules == ("empty", "all_person") and config.runs == 1
    assert config.injection is not None and config.injection["outcome"] == "built"
    model = config.model
    assert (model.model, model.region, model.max_tokens, model.effort) == ("anthropic.claude-sonnet-5", "us-east-1", 16000, "high")
    assert model.temperature is None
