"""The Claude models stream their responses (ADR 0013): the SDK refuses a non-streamed request whose
max_tokens could take over ten minutes, and claim writing needs more room than that allows. An error
event inside a stream arrives with HTTP status 200, so its type says whether it is worth another
attempt. The SDK retries only the request that opens a stream, so a transient failure inside one is
retried here with the SDK's count and backoff, before it uses up one of the caller's attempts. No
test calls a model.
"""

import json
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
from anthropic.types import Message

from warrant.agent import claude
from warrant.agent.claude import ClaudeAgent, ClaudeClaimWriter, ClaudeJudge
from warrant.agent.config import ModelConfig
from warrant.agent.interface import AnswerRequest, ResponseKind
from warrant.agent.tools import ReadOnlySQL
from warrant.data.sqlite import schema
from warrant.store.claims import KnowledgeStore

RESPONSES = Path(__file__).parent / "fixtures" / "responses"
CONFIG = ModelConfig(provider="bedrock", model="anthropic.claude-model-placeholder", region="region-placeholder",
                     attempts=2, max_tokens=64000)
REQUEST = httpx.Request("POST", "http://example.invalid")


def recorded(name):
    return Message.model_validate(json.loads((RESPONSES / f"{name}.json").read_text()))


def mid_stream(kind):
    """The error the SDK raises for an `error` event inside a stream: the stream's status is 200."""
    body = {"type": "error", "error": {"type": kind, "message": "boom"}}
    return anthropic.APIStatusError(f"{body}", response=httpx.Response(200, request=REQUEST), body=body)


class Messages:
    """Stands in for the client's `messages`: `stream` hands back each step's message, or raises it."""

    def __init__(self, *steps):
        self.steps, self.sent = list(steps), []

    def stream(self, **kwargs):
        self.sent.append(kwargs)
        step = self.steps.pop(0)

        class Stream:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_final_message(self):
                if isinstance(step, BaseException):
                    raise step
                return step

        return Stream()


RETRIES = anthropic.DEFAULT_MAX_RETRIES  # the SDK's, which a failure inside a stream gets too


@pytest.fixture
def platform(monkeypatch):
    """The client factory, giving the models a stand-in `messages` set up by each test; the waits
    between retries are recorded, not slept."""
    holder = {"waits": []}
    monkeypatch.setattr(claude.time, "sleep", holder["waits"].append)

    class Client:
        @property
        def messages(self):
            return holder["messages"]

    monkeypatch.setattr(claude, "client", lambda config: Client())
    return holder


@pytest.fixture
def request_for(workorders_db):
    return AnswerRequest(database="workorders", question_id="open-orders", question="How many open work orders are there?",
                         run=0, schema=schema(workorders_db), store=KnowledgeStore(), tools=(ReadOnlySQL.name,))


@pytest.fixture
def sql_tool(workorders_db):
    return {ReadOnlySQL.name: ReadOnlySQL(workorders_db)}


def test_each_model_streams_its_response_and_reads_the_final_message(platform, request_for, sql_tool):
    platform["messages"] = Messages(recorded("tool_use_sql"), recorded("answer"))
    output = ClaudeAgent(CONFIG).answer(request_for, sql_tool)
    assert output.response.kind == ResponseKind.ANSWER and output.usage.input_tokens > 0
    assert [sent["max_tokens"] for sent in platform["messages"].sent] == [64000, 64000]
    assert all("stream" not in sent for sent in platform["messages"].sent)

    platform["messages"] = Messages(recorded("write_claims"))
    assert ClaudeClaimWriter(CONFIG).call("system", "user").text
    platform["messages"] = Messages(recorded("judge_labels"))
    assert ClaudeJudge(CONFIG).call("a filled rubric").text


@pytest.mark.parametrize("kind", ["overloaded_error", "api_error", "rate_limit_error", "timeout_error"])
def test_a_transient_error_event_mid_stream_is_retried_and_then_recorded_as_a_failure(platform, request_for, sql_tool, kind):
    # Each of the agent's two attempts tries the SDK's 1 + RETRIES times before it fails.
    platform["messages"] = Messages(*[mid_stream(kind)] * (2 * (1 + RETRIES)))
    output = ClaudeAgent(CONFIG).answer(request_for, sql_tool)
    assert output.response is None and kind in output.failure and platform["messages"].steps == []
    platform["messages"] = Messages(*[mid_stream(kind)] * (1 + RETRIES))
    assert ClaudeClaimWriter(CONFIG).call("system", "user").text is None


def test_a_short_overload_inside_a_stream_is_absorbed_with_the_sdks_backoff(platform):
    platform["messages"] = Messages(mid_stream("overloaded_error"), mid_stream("overloaded_error"),
                                    recorded("write_claims"))
    assert ClaudeClaimWriter(CONFIG).call("system", "user").text
    assert platform["waits"] == [0.5, 1.0]


def test_another_error_event_mid_stream_stops_the_run(platform, request_for, sql_tool):
    platform["messages"] = Messages(mid_stream("invalid_request_error"), recorded("answer"))
    with pytest.raises(anthropic.APIStatusError):
        ClaudeAgent(CONFIG).answer(request_for, sql_tool)
    assert platform["waits"] == []  # not retried


def test_a_request_that_fails_before_its_stream_opens_is_left_to_the_sdk(platform, request_for, sql_tool):
    # The SDK has retried it already, so it is not retried again here; a 5xx is still transient.
    platform["messages"] = Messages(anthropic.InternalServerError(
        "boom", response=httpx.Response(503, request=REQUEST), body=None), recorded("answer"))
    output = ClaudeAgent(CONFIG).answer(request_for, sql_tool)
    assert output.failure == "" and platform["waits"] == []


def test_a_connection_lost_mid_stream_is_retried_like_any_lost_connection(platform, request_for, sql_tool):
    platform["messages"] = Messages(httpx.RemoteProtocolError("peer closed the connection", request=REQUEST),
                                    recorded("answer"))
    output = ClaudeAgent(CONFIG).answer(request_for, sql_tool)
    assert output.failure == "" and output.response.kind == ResponseKind.ANSWER
    assert platform["waits"] == [0.5]  # retried inside the attempt
    platform["messages"] = Messages(*[httpx.ReadTimeout("timed out")] * (1 + RETRIES))
    judged = ClaudeJudge(CONFIG).call("a filled rubric")
    assert judged.text is None and "APIConnectionError" in judged.failure
