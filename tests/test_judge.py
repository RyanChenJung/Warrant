"""The judge operation (#120): three valid calls per claim, re-sent calls for failed or invalid ones,
and each reading's label by the frozen combination, driven by a scripted judge model or by recorded
model responses, so no test reaches the model."""

import hashlib
import json
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
import yaml

from warrant.agent.claude import ClaudeJudge
from warrant.agent.config import ModelConfig
from warrant.agent.fake import ScriptedJudge
from warrant.agent.judge import (
    JUDGE_PROMPT_VERSION,
    RUBRIC_SHA256,
    Judge,
    JudgeMethod,
    JudgeRequest,
    Label,
    parse,
    prompt,
)
from warrant.store.claims import ClaimKind, Slot

REPO = Path(__file__).parents[1]
FREEZE = REPO / "freeze" / "write_line.yaml"
SLOT = Slot(ClaimKind.COVERAGE, "workorders")
REQUEST = JudgeRequest(
    slot=SLOT,
    claim="The work-order table leaves out the open work orders.",
    readings=(
        ("parent-cut", "Open work orders were cut from the work-order table."),
        ("nothing-cut", "Nothing was cut from the work-order table."),
        ("mistyped-references", "Some tasks carry mistyped work-order numbers."),
    ),
)
HOLDS, FAILS, NOT_ADDRESSED = Label.HOLDS, Label.FAILS, Label.NOT_ADDRESSED


@pytest.fixture(scope="module")
def method():
    return JudgeMethod.from_freeze(yaml.safe_load(FREEZE.read_text())["global"])


def answer(**labels):
    return json.dumps(labels)


def scripted(*texts):
    """A judge model that gives these text outputs in order; None stands for a failed call."""
    queue = list(texts)
    return ScriptedJudge(lambda prompt: queue.pop(0))


def test_the_judge_method_is_read_from_the_global_part_of_the_committed_freeze(method):
    judge = yaml.safe_load(FREEZE.read_text())["global"]["judge"]
    rubric = REPO / judge["rubric"]
    assert method.rubric_path == judge["rubric"] == "freeze/judge_rubric.md"
    assert method.template in rubric.read_text()
    # The rubric's SHA-256 at the freeze commit 6676db7, pinned in the code.
    assert method.record()["rubric_sha256"] == RUBRIC_SHA256
    assert RUBRIC_SHA256 == "88f8592557f40ceca47b1a238bdab09bb708de8fa0253133dfc49f7dc46256fc"
    assert (method.valid_calls, method.extra_calls) == (3, 3)
    assert method.record()["prompt_version"] == JUDGE_PROMPT_VERSION


def test_a_rubric_whose_bytes_differ_from_the_one_at_the_freeze_commit_is_refused(tmp_path):
    (tmp_path / "freeze").mkdir()
    edited = (REPO / "freeze" / "judge_rubric.md").read_text().replace("a careful analyst", "an analyst")
    (tmp_path / "freeze" / "judge_rubric.md").write_text(edited)
    assert hashlib.sha256(edited.encode()).hexdigest() != RUBRIC_SHA256
    with pytest.raises(ValueError, match="not the rubric of the freeze commit"):
        JudgeMethod.from_freeze(yaml.safe_load(FREEZE.read_text())["global"], repo=tmp_path)


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"profile": ["holds", "fails"]}, "profile"),
        ({"operation": "the judge operation, one call per slot claim"}, "three calls per slot claim"),
        ({"rubric": "freeze/no_such_rubric.md"}, "no_such_rubric.md"),
    ],
)
def test_a_judge_method_other_than_the_one_built_here_is_refused(change, reason):
    global_part = yaml.safe_load(FREEZE.read_text())["global"]
    global_part["judge"] = {**global_part["judge"], **change}
    with pytest.raises(ValueError, match=reason):
        JudgeMethod.from_freeze(global_part)


def test_the_prompt_fills_the_rubric_with_lettered_reading_statements_and_no_reading_ids(method):
    text, letters = prompt(method.template, REQUEST)
    assert letters == {"A": "parent-cut", "B": "nothing-cut", "C": "mistyped-references"}
    assert "The claim is about workorders (claim kind: coverage)." in text
    assert REQUEST.claim in text
    assert "A. Open work orders were cut from the work-order table.\nB. Nothing was cut" in text
    assert not any(reading_id in text for reading_id in letters.values())
    assert "{claim}" not in text and "{readings}" not in text
    assert '{"A": "holds", "B": "fails", "C": "not_addressed"}' in text  # the rubric's own example


def test_the_placeholders_are_filled_in_one_pass_so_a_claim_or_statement_naming_one_stays_as_written(method):
    request = JudgeRequest(SLOT, "The {readings} column lists {subject} codes.", (("odd", "It says {claim}."),))
    text, _ = prompt(method.template, request)
    assert "Claim:\nThe {readings} column lists {subject} codes.\n" in text
    assert "A. It says {claim}." in text


@pytest.mark.parametrize(
    "text, labels",
    [
        ('{"A": "holds", "B": "fails"}', {"A": HOLDS, "B": FAILS}),
        ('Here is my answer: {"A": "not_addressed", "B": "holds"} and {"A": "fails", "B": "fails"}', {"A": NOT_ADDRESSED, "B": HOLDS}),
        ('```json\n{"A": "fails", "B": "fails"}\n```', {"A": FAILS, "B": FAILS}),
        ('{not json} {"A": "holds", "B": "holds"}', {"A": HOLDS, "B": HOLDS}),
    ],
)
def test_a_calls_answer_is_the_first_json_object_in_its_text_output(text, labels):
    assert parse(text, ("A", "B")) == labels


@pytest.mark.parametrize(
    "text",
    [
        "no object at all",
        '{"A": "holds"}',  # a letter without a label
        '{"A": "holds", "B": "fails", "C": "holds"}',  # a key that is no reading letter
        '{"A": "Holds", "B": "fails"}',  # labels are matched exactly, in lower case
        '{"A": "holds", "B": "not addressed"}',
        '{"A": "holds", "B": ["fails"]}',
        '{"A": "holds", "B": "fails"',  # the first object never closes
        '{"A": "holds", "B": "fails", "A": "fails"}',  # a letter labelled twice
        '{"A": "holds", "B": "fails", "A": "holds"}',
    ],
)
def test_an_answer_that_does_not_label_every_reading_letter_exactly_once_validly_is_invalid(text):
    with pytest.raises(ValueError):
        parse(text, ("A", "B"))


def test_each_readings_label_is_the_one_at_least_two_of_the_three_valid_calls_give(method):
    model = scripted(
        answer(A="holds", B="fails", C="fails"),
        answer(A="holds", B="fails", C="not_addressed"),
        answer(A="fails", B="fails", C="not_addressed"),
    )
    judgement = Judge(model, method).judge(REQUEST)
    assert judgement.labels == {"parent-cut": HOLDS, "nothing-cut": FAILS, "mistyped-references": NOT_ADDRESSED}
    assert judgement.splits == ()
    assert len(model.prompts) == 3 and judgement.resent == 0


def test_three_different_labels_on_a_reading_give_not_addressed_and_count_as_a_split(method):
    model = scripted(
        answer(A="holds", B="fails", C="holds"),
        answer(A="fails", B="fails", C="holds"),
        answer(A="not_addressed", B="fails", C="holds"),
    )
    judgement = Judge(model, method).judge(REQUEST)
    assert judgement.labels["parent-cut"] == NOT_ADDRESSED
    assert judgement.splits == ("parent-cut",)


def test_a_failed_or_invalid_call_is_discarded_and_re_sent_until_there_are_three_valid_answers(method):
    model = scripted(
        None,
        "I cannot judge this.",
        answer(A="holds", B="fails", C="fails"),
        answer(A="holds", B="fails"),  # a letter missing
        answer(A="holds", B="fails", C="fails"),
        answer(A="holds", B="holds", C="fails"),
    )
    judgement = Judge(model, method).judge(REQUEST)
    assert len(model.prompts) == 6 and judgement.resent == 3
    assert len(judgement.valid) == 3
    assert judgement.labels == {"parent-cut": HOLDS, "nothing-cut": FAILS, "mistyped-references": FAILS}
    assert len(judgement.answers) == 6  # every answer is kept, the discarded ones included


def test_at_most_three_extra_calls_are_sent_and_a_reading_without_a_shared_label_is_not_addressed(method):
    model = scripted(None, None, None, None, answer(A="holds", B="fails", C="fails"), "nonsense", "unused")
    judgement = Judge(model, method).judge(REQUEST)
    assert len(model.prompts) == 6 and judgement.resent == 3
    assert len(judgement.valid) == 1
    assert judgement.labels == dict.fromkeys(("parent-cut", "nothing-cut", "mistyped-references"), NOT_ADDRESSED)
    assert judgement.splits == ("parent-cut", "nothing-cut", "mistyped-references")


def test_two_valid_calls_that_agree_still_settle_a_reading_after_the_extra_calls(method):
    model = scripted(None, None, None, None, answer(A="holds", B="fails", C="fails"), answer(A="holds", B="holds", C="fails"))
    judgement = Judge(model, method).judge(REQUEST)
    assert judgement.labels == {"parent-cut": HOLDS, "nothing-cut": NOT_ADDRESSED, "mistyped-references": FAILS}
    assert judgement.splits == ("nothing-cut",)


def test_a_claim_is_judged_once_and_an_identical_claim_string_agrees_without_a_call(method):
    model = scripted(*[answer(A="holds", B="fails", C="fails")] * 3)
    judge = Judge(model, method)
    first = judge.judge(REQUEST)
    again = judge.judge(JudgeRequest(SLOT, REQUEST.claim, REQUEST.readings))
    assert len(model.prompts) == 3
    assert again.labels == first.labels and again.without_a_call and not first.without_a_call
    # The copy made without a call carries no calls, so no splits either.
    assert (again.valid, again.answers, again.splits, again.resent) == ((), (), (), 0)


def test_a_repeated_answer_to_a_split_claim_carries_no_split_of_its_own(method):
    model = scripted(answer(A="holds", B="fails", C="holds"), answer(A="fails", B="fails", C="holds"),
                     answer(A="not_addressed", B="fails", C="holds"))
    judge = Judge(model, method)
    assert judge.judge(REQUEST).splits == ("parent-cut",)
    assert judge.judge(REQUEST).splits == ()


def test_every_judgement_is_stored_with_its_method_its_answers_and_its_combined_labels(method):
    model = scripted(*[answer(A="holds", B="fails", C="fails")] * 3)
    record = Judge(model, method).judge(REQUEST).record()
    assert record["method"] == method.record()
    assert record["method"]["operation"] == "judge"
    assert record["labels"] == {"parent-cut": "holds", "nothing-cut": "fails", "mistyped-references": "fails"}
    assert record["reading_order"] == ["parent-cut", "nothing-cut", "mistyped-references"]
    assert len(record["answers"]) == 3 and record["resent"] == 0 and record["splits"] == []
    assert json.loads(json.dumps(record)) == record


HTTP_REQUEST = httpx.Request("POST", "https://bedrock-runtime.region-placeholder.amazonaws.com")


def status_error(kind, status):
    return kind("boom", response=httpx.Response(status, request=HTTP_REQUEST), body=None)


CONFIG = ModelConfig(
    provider="bedrock",
    model="anthropic.claude-model-placeholder",
    region="region-placeholder",
    max_tokens=16000,
    effort="high",
)


def test_the_claude_judge_sends_the_filled_rubric_with_the_claim_writing_settings_and_no_sampling_parameter(
    replay, method
):
    create = replay("judge_labels", "judge_labels", "judge_labels")
    judgement = Judge(ClaudeJudge(CONFIG, create), method).judge(REQUEST)

    assert judgement.labels == {"parent-cut": HOLDS, "nothing-cut": FAILS, "mistyped-references": NOT_ADDRESSED}
    assert (judgement.usage.input_tokens, judgement.usage.output_tokens) == (3 * 900, 3 * 30)
    sent = create.calls[0]
    assert sent["model"] == CONFIG.model and sent["max_tokens"] == 16000
    assert sent["output_config"] == {"effort": "high"}
    assert sent["messages"] == [{"role": "user", "content": prompt(method.template, REQUEST)[0]}]
    assert not {"temperature", "top_p", "top_k", "extra_body", "thinking", "tools", "system"} & sent.keys()


def test_a_transient_platform_error_is_a_failed_call_that_is_re_sent(replay, method):
    recorded = replay("judge_labels", "judge_labels", "judge_labels")
    errors = [status_error(anthropic.RateLimitError, 429)]

    def create(**kwargs):
        if errors:
            raise errors.pop()
        return recorded(**kwargs)

    judgement = Judge(ClaudeJudge(CONFIG, create), method).judge(REQUEST)
    assert judgement.resent == 1 and len(judgement.valid) == 3
    assert judgement.answers[0].startswith("failed: RateLimitError")


def test_a_misconfiguration_stops_the_judge_instead_of_being_re_sent(method):
    def create(**kwargs):
        raise status_error(anthropic.PermissionDeniedError, 403)

    with pytest.raises(anthropic.PermissionDeniedError):
        Judge(ClaudeJudge(CONFIG, create), method).judge(REQUEST)


def test_a_judge_configuration_that_names_a_temperature_is_refused_since_the_freeze_sends_none(replay):
    with pytest.raises(ValueError, match="temperature"):
        ClaudeJudge(ModelConfig(**{**CONFIG.__dict__, "temperature": 0.0}), replay("judge_labels"))


def test_the_claude_judge_reaches_the_model_only_through_the_configured_client(method):
    with pytest.raises(AssertionError, match="tried to reach the real model"):
        ClaudeJudge(CONFIG)
