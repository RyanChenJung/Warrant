"""The Claude agent, driven by the recorded model responses the `replay` fixture returns."""

import json

import anthropic
import httpx2 as httpx
import pytest

from warrant.agent.claude import ClaudeAgent
from warrant.agent.config import ModelConfig
from warrant.agent.interface import AnswerRequest, ResponseKind
from warrant.agent.tools import SCHEMAS, ReadOnlySQL
from warrant.data.sqlite import query, schema
from warrant.store.claims import KnowledgeStore

CONFIG = ModelConfig(
    provider="bedrock",
    model="anthropic.claude-model-placeholder",
    region="region-placeholder",
    attempts=2,
)


@pytest.fixture
def request_for(workorders_db):
    def build(tools=(ReadOnlySQL.name,)):
        return AnswerRequest(
            database="workorders",
            question_id="open-orders",
            question="How many open work orders are there?",
            run=0,
            schema=schema(workorders_db),
            store=KnowledgeStore(),
            tools=tools,
        )

    return build


@pytest.fixture
def sql_tool(workorders_db):
    return {ReadOnlySQL.name: ReadOnlySQL(workorders_db)}


def tool_results(call):
    """The tool results the agent sent back in one request."""
    return [block for block in call["messages"][-1]["content"] if block["type"] == "tool_result"]


def test_a_recorded_answer_returns_the_structured_response_and_the_usage_of_every_call(
    replay, request_for, sql_tool
):
    create = replay("tool_use_sql", "answer")
    output = ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    assert output.failure == ""
    assert output.response.kind == ResponseKind.ANSWER
    assert output.response.final_sql == "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'"
    assert output.response.value == 4
    assert output.response.confidence == 0.8
    assert (output.usage.input_tokens, output.usage.output_tokens) == (1200 + 1400, 40 + 90)


def test_a_recorded_refusal_returns_what_is_missing_and_what_can_be_answered_instead(
    replay, request_for, sql_tool
):
    output = ClaudeAgent(CONFIG, replay("refusal")).answer(request_for(), sql_tool)

    assert output.response.kind == ResponseKind.REFUSAL
    assert output.response.missing == "which statuses count as open"
    assert output.response.alternative == "the number of work orders per status"
    assert output.response.final_sql is None


def test_malformed_output_is_retried_and_then_recorded_as_a_failure_with_its_usage(
    replay, request_for, sql_tool
):
    create = replay("malformed", "malformed")
    output = ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    assert len(create.calls) == CONFIG.attempts == 2
    assert output.response is None
    assert "malformed" in output.failure
    assert (output.usage.input_tokens, output.usage.output_tokens) == (1400 + 1400, 20 + 20)


REQUEST = httpx.Request("POST", "http://example.invalid")


def raising(error):
    """A `messages.create` that always raises, and counts how often it was asked."""
    attempts = []

    def create(**kwargs):
        attempts.append(kwargs)
        raise error

    return create, attempts


def status_error(kind, status):
    return kind("boom", response=httpx.Response(status, request=REQUEST), body=None)


TRANSIENT = [
    anthropic.APIConnectionError(request=REQUEST),
    anthropic.APITimeoutError(request=REQUEST),
    status_error(anthropic.RateLimitError, 429),
    status_error(anthropic.InternalServerError, 503),
]

PERMANENT = [
    status_error(anthropic.AuthenticationError, 401),
    status_error(anthropic.PermissionDeniedError, 403),
    status_error(anthropic.NotFoundError, 404),
    status_error(anthropic.BadRequestError, 400),
    status_error(anthropic.UnprocessableEntityError, 422),
]


@pytest.mark.parametrize("error", TRANSIENT, ids=lambda e: type(e).__name__)
def test_a_transient_error_is_retried_and_then_recorded_as_a_failure(error, request_for, sql_tool):
    create, attempts = raising(error)
    output = ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    assert len(attempts) == CONFIG.attempts == 2
    assert output.response is None
    assert type(error).__name__ in output.failure


@pytest.mark.parametrize("error", PERMANENT, ids=lambda e: type(e).__name__)
def test_a_misconfiguration_stops_the_run_instead_of_being_recorded_per_question(
    error, request_for, sql_tool
):
    """Bad credentials, an unknown model or a bad region are wrong for every question, not one."""
    create, attempts = raising(error)

    with pytest.raises(type(error)):
        ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    assert len(attempts) == 1  # not retried, and no second question is asked


def test_an_answer_wrapped_in_a_markdown_fence_is_still_read(replay, request_for, sql_tool):
    output = ClaudeAgent(CONFIG, replay("answer_fenced")).answer(request_for(), sql_tool)

    assert output.failure == ""
    assert output.response.kind == ResponseKind.ANSWER
    assert output.response.final_sql == "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'"
    assert output.response.confidence == 0.8


@pytest.mark.parametrize(
    "recorded",
    [
        "answer_without_sql",
        "answer_blank_sql",
        "answer_sql_not_text",
        "confidence_not_a_number",
        "confidence_out_of_range",
        "refusal_missing_not_text",
    ],
)
def test_a_response_the_prompt_asked_for_differently_is_malformed(
    recorded, replay, request_for, sql_tool
):
    """An answer is scored by re-executing its SQL, a refusal by reading its text fields, and the
    confidence is a number in [0, 1]: a response missing any of these is no more usable than one
    that is not JSON at all."""
    create = replay(recorded, recorded)
    output = ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    assert len(create.calls) == CONFIG.attempts == 2
    assert output.response is None
    assert "malformed" in output.failure


def test_a_retry_after_malformed_output_still_answers(replay, request_for, sql_tool):
    create = replay("malformed", "answer")
    output = ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    assert len(create.calls) == 2
    assert output.failure == ""
    assert output.response.kind == ResponseKind.ANSWER


def test_the_agent_declares_exactly_the_tools_the_request_offers(replay, request_for, sql_tool):
    create = replay("tool_use_sql", "answer")
    ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)
    assert create.calls[0]["tools"] == [SCHEMAS[ReadOnlySQL.name]]

    no_tools = replay("answer")
    ClaudeAgent(CONFIG, no_tools).answer(request_for(tools=()), {})
    assert no_tools.calls[0]["tools"] == []


def test_a_tool_the_request_does_not_offer_is_refused_without_being_called(
    replay, request_for, workorders_db
):
    asked = []
    bound_in_code_but_not_offered_in_the_request = {
        ReadOnlySQL.name: ReadOnlySQL(workorders_db),
        "escalate": lambda question: asked.append(question),
    }

    create = replay("tool_use_unoffered", "answer")
    output = ClaudeAgent(CONFIG, create).answer(
        request_for(tools=(ReadOnlySQL.name,)), bound_in_code_but_not_offered_in_the_request
    )

    assert asked == []
    (result,) = tool_results(create.calls[1])
    assert result["is_error"] is True
    assert "escalate" in result["content"]
    assert output.response.kind == ResponseKind.ANSWER


def test_the_read_only_sql_tool_rejects_writes_and_the_loop_carries_on(
    replay, request_for, sql_tool, workorders_db
):
    create = replay("tool_use_write", "answer")
    output = ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    (result,) = tool_results(create.calls[1])
    assert result["is_error"] is True
    assert "readonly" in result["content"]
    assert query(workorders_db, "SELECT COUNT(*) FROM tasks") == [(23,)]
    assert output.response.kind == ResponseKind.ANSWER


def test_a_tool_result_carries_the_rows_back_to_the_model(replay, request_for, sql_tool):
    create = replay("tool_use_sql", "answer")
    ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    (result,) = tool_results(create.calls[1])
    assert result.get("is_error") is not True
    assert json.loads(result["content"]) == [[4]]


def test_the_tool_loop_stops_at_the_configured_ceiling(replay, request_for, sql_tool):
    config = ModelConfig(provider="bedrock", model="m", attempts=1, max_tool_calls=1)
    create = replay("tool_use_sql", "tool_use_sql")
    output = ClaudeAgent(config, create).answer(request_for(), sql_tool)

    assert output.response is None
    assert "tool call" in output.failure


def test_sampling_parameters_come_from_the_configuration(replay, request_for, sql_tool):
    plain = replay("answer")
    ClaudeAgent(ModelConfig(provider="bedrock", model="m"), plain).answer(request_for(), sql_tool)
    assert "output_config" not in plain.calls[0]
    assert "extra_body" not in plain.calls[0]

    tuned = replay("answer")
    config = ModelConfig(provider="bedrock", model="m", max_tokens=2048, effort="low", temperature=0.0)
    ClaudeAgent(config, tuned).answer(request_for(), sql_tool)
    assert tuned.calls[0]["model"] == "m"
    assert tuned.calls[0]["max_tokens"] == 2048
    assert tuned.calls[0]["output_config"] == {"effort": "low"}
    assert tuned.calls[0]["extra_body"] == {"temperature": 0.0}


def test_the_prompt_carries_the_question_the_schema_and_the_store_but_never_the_rule(
    replay, request_for, sql_tool
):
    create = replay("answer")
    ClaudeAgent(CONFIG, create).answer(request_for(), sql_tool)

    sent = create.calls[0]
    prompt = sent["messages"][0]["content"]
    assert "How many open work orders are there?" in prompt
    assert "CREATE TABLE workorders" in prompt
    assert ReadOnlySQL.name in prompt
    assert sent["system"]
    assert "all_person" not in prompt and "all_person" not in sent["system"]
