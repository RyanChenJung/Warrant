"""The judge's validation (#120): before the first claim-writing call, the judge's labels on every
reference claim and drift-reading statement of the committed freeze are compared with its holds
flags, and mismatches are reported, not fixed. Each slot's readings reach the judge in one order,
drawn once from the freeze's seed. No test reaches the model."""

import json
import random
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from warrant.agent.fake import ScriptedJudge
from warrant.agent.judge import JUDGE_PROMPT_VERSION, JudgeMethod, Label
from warrant.data.release import sha256
from warrant.defects.build import build
from warrant.defects.inject import load_defect
from warrant.freeze.validate import clean_databases
from warrant.store.results import Provenance
from warrant.write_line.judging import reading_orders
from warrant.write_line.validate_judge import main, validate, validation_claims, write_validation

REPO = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
FROZEN = yaml.safe_load((REPO / "freeze" / "write_line.yaml").read_text())
DEFECTS = tuple(load_defect(d) for d in FROZEN["defects"])
SEED = FROZEN["global"]["seeds"]["judge_reading_order"]
METHOD = JudgeMethod.from_freeze(FROZEN["global"])
LETTER = re.compile(r"^([A-Z])\. (.*)$", re.M)


def statements(prompt):
    """The reading statements a prompt lists, in its order."""
    return [statement for _, statement in LETTER.findall(prompt.split("Readings:", 1)[1])]


def by_statement(answer_for):
    """A scripted judge model that labels each reading of a prompt by its statement."""

    def call(prompt):
        lettered = dict(LETTER.findall(prompt.split("Readings:", 1)[1]))
        return json.dumps({letter: answer_for(prompt, statement) for letter, statement in lettered.items()})

    return ScriptedJudge(call)


def statement_of(defect_id, reading_id):
    (defect,) = [d for d in DEFECTS if d.id == defect_id]
    return {r["id"]: r["statement"].strip() for r in defect.readings}[reading_id]


def claim_of(prompt):
    return prompt.split("Claim:\n", 1)[1].split("\n\nReadings:", 1)[0]


def as_frozen(prompt, statement):
    """What the frozen holds flags expect: the reference claim by its flags, a drift-reading
    statement holding on its own drift reading and failing elsewhere."""
    for defect in DEFECTS:
        readings = {r["statement"].strip(): r for r in defect.readings}
        if statement not in readings:
            continue
        if claim_of(prompt) == defect.reference_claim.strip():
            return "holds" if readings[statement]["holds"] else "fails"
        drift = defect.drift_reading["reading"]
        return "holds" if readings[statement]["id"] == drift else "fails"
    raise AssertionError(statement)


def test_each_slots_reading_order_is_drawn_once_from_one_generator_over_the_slots_in_order():
    rng = random.Random(SEED)
    expected = {}
    for defect in sorted(DEFECTS, key=lambda d: (d.database, d.slot.claim_kind, d.slot.subject)):
        ids = [r["id"] for r in defect.readings]
        rng.shuffle(ids)
        expected[defect.id] = tuple(ids)
    assert reading_orders(DEFECTS, SEED) == expected
    assert reading_orders(tuple(reversed(DEFECTS)), SEED) == expected


def test_every_call_on_a_slot_lists_its_readings_in_the_slots_one_order():
    judge_model = by_statement(as_frozen)
    validate(DEFECTS, judge_model, METHOD, SEED)
    orders = reading_orders(DEFECTS, SEED)
    for defect in DEFECTS:
        expected = [statement_of(defect.id, r) for r in orders[defect.id]]
        on_slot = [p for p in judge_model.prompts if f"The claim is about {defect.slot.subject} " in p]
        assert len(on_slot) == 2 * 3  # the reference claim and the drift-reading statement, three calls each
        assert all(statements(p) == expected for p in on_slot)


def test_the_validation_claims_are_every_reference_claim_on_every_reading_and_each_drift_statement_on_two():
    claims = validation_claims(DEFECTS)
    assert [(c.defect, c.role) for c in claims] == [
        ("wallet-sum", "reference_claim"),
        ("wallet-sum", "drift_reading"),
        ("orders-cut", "reference_claim"),
        ("orders-cut", "drift_reading"),
        ("seeing-recode", "reference_claim"),
        ("seeing-recode", "drift_reading"),
    ]
    wallet, wallet_drift, orders, orders_drift, seeing, seeing_drift = claims
    assert wallet.expected == {
        "with-margin": Label.HOLDS,
        "without-margin": Label.FAILS,
        "without-frozen": Label.FAILS,
        "with-unrealised-pnl": Label.FAILS,
        "four-terms": Label.FAILS,
    }
    assert len(orders.expected) == 7
    assert orders_drift.claim == statement_of("orders-cut", "nothing-cut")
    assert orders_drift.expected == {"nothing-cut": Label.HOLDS, "cancelled-cut": Label.FAILS}
    assert wallet_drift.expected == {"without-margin": Label.HOLDS, "with-margin": Label.FAILS}
    # A meaning-only drift reading has the reference claim a person would state under it.
    assert seeing_drift.claim == FROZEN["defects"][2]["drift_reading"]["reference_claim"].strip()
    assert seeing_drift.expected == {"three-is-best": Label.HOLDS, "one-is-best": Label.FAILS}


def test_a_judge_that_agrees_with_the_holds_flags_leaves_no_mismatch():
    report = validate(DEFECTS, by_statement(as_frozen), METHOD, SEED)
    assert len(report.rows) == 5 + 2 + 7 + 2 + 2 + 2
    assert report.mismatches == []
    assert all(row["expected"] == row["judged"] for row in report.rows)


def test_every_mismatch_is_reported_with_its_expected_and_judged_label_and_not_addressed_is_one():
    def wrong_on_orders(prompt, statement):
        if "orders table only holds" in claim_of(prompt) and statement == statement_of("orders-cut", "archived"):
            return "holds"  # the frozen flag says fails
        if "walletsum in accountbalances includes" in claim_of(prompt):
            return "not_addressed"
        return as_frozen(prompt, statement)

    report = validate(DEFECTS, by_statement(wrong_on_orders), METHOD, SEED)
    assert {(m["defect"], m["role"], m["reading"], m["expected"], m["judged"]) for m in report.mismatches} == {
        ("orders-cut", "reference_claim", "archived", "fails", "holds"),
        *{("wallet-sum", "reference_claim", r, "holds" if r == "with-margin" else "fails", "not_addressed")
          for r in ("with-margin", "without-margin", "without-frozen", "with-unrealised-pnl", "four-terms")},
    }


def test_splits_and_pairs_whose_three_calls_differ_are_counted():
    seen = Counter()

    def unsteady(prompt):
        seen[prompt] += 1
        lettered = dict(LETTER.findall(prompt.split("Readings:", 1)[1]))
        # The third call on the wallet's reference claim disagrees on every reading.
        if "walletsum in accountbalances includes" in claim_of(prompt) and seen[prompt] == 3:
            return json.dumps(dict.fromkeys(lettered, "not_addressed"))
        return json.dumps({letter: as_frozen(prompt, statement) for letter, statement in lettered.items()})

    report = validate(DEFECTS, ScriptedJudge(unsteady), METHOD, SEED)
    assert report.mismatches == [] and report.splits == 0
    assert report.unsteady_pairs == 5  # (claim, reading) pairs whose valid calls do not all agree


def test_the_records_carry_the_judgement_its_method_and_each_comparison_and_the_rubric_is_untouched(tmp_path):
    rubric = REPO / "freeze" / "judge_rubric.md"
    before = rubric.read_bytes()
    results = tmp_path / "validation.jsonl"
    provenance = Provenance(config_hash="0" * 64, repo_commit="abc1234", model="placeholder", prompt_version=JUDGE_PROMPT_VERSION)
    report = validate(DEFECTS, by_statement(as_frozen), METHOD, SEED)
    write_validation(report, results, provenance)

    records = [json.loads(line) for line in results.read_text().splitlines()]
    assert len(records) == 6
    assert {r["operation"] for r in records} == {"judge_validation"}
    assert {r["prompt_version"] for r in records} == {JUDGE_PROMPT_VERSION}
    assert all(r["method"] == METHOD.record() for r in records)
    assert all(r["mismatches"] == [] and len(r["answers"]) == 3 for r in records)
    assert all(set(r["expected"]) <= set(r["labels"]) for r in records)
    assert rubric.read_bytes() == before


# The command reads the freeze through a run configuration that names it and its recorded
# injection, so it judges only the freeze the injection was built from.


@pytest.fixture
def freeze(workorders_db):
    """The whole-freeze fixture with the committed freeze's judge method, next to its databases."""
    raw = yaml.safe_load((FIXTURES / "freeze_predictions.yaml").read_text())
    raw["global"]["judge"] = FROZEN["global"]["judge"]
    path = workorders_db.parent / "freeze.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


def injection_record(freeze, out):
    raw = yaml.safe_load(freeze.read_text())
    built = build([load_defect(d) for d in raw["defects"]], clean_databases(raw, freeze), out)
    record = {"outcome": "built", "freeze_sha256": sha256(freeze), "injected": built.injected, "readings": built.readings}
    path = freeze.parent / "injection.json"
    path.write_text(json.dumps(record))
    return path


def configuration(freeze, **extra):
    path = freeze.parent / "judge.yaml"
    raw = {
        "freeze": freeze.name,
        "rules": ["empty"],
        "runs": 1,
        "questions": [],
        "model": {"provider": "bedrock", "model": "anthropic.claude-sonnet-5", "region": "us-east-1", "max_tokens": 16000, "effort": "high"},
        **extra,
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


def test_the_command_refuses_a_configuration_without_the_freezes_recorded_injection(freeze, tmp_path):
    with pytest.raises(SystemExit):
        main(["--config", str(configuration(freeze)), "--results", str(tmp_path / "out.jsonl"), "--dry-run"])


def test_the_command_refuses_a_freeze_other_than_the_one_its_injection_was_built_from(freeze, tmp_path):
    record = injection_record(freeze, tmp_path / "built")
    freeze.write_text(freeze.read_text() + "\n# edited after the injection\n")
    with pytest.raises(ValueError, match="not of this freeze"):
        main(["--config", str(configuration(freeze, injection=record.name)), "--dry-run"])


def test_a_dry_run_prints_every_prompt_it_would_send_and_makes_no_model_call(freeze, tmp_path, capsys):
    record = injection_record(freeze, tmp_path / "built")
    results = tmp_path / "out.jsonl"
    assert main(["--config", str(configuration(freeze, injection=record.name)), "--results", str(results), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("Readings:") == 8  # four defects, a reference claim and a drift statement each
    assert "at most 6 calls each" in out
    assert not results.exists()
