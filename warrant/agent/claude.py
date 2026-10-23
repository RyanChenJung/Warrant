"""The Claude implementations of the answer operation, of the judge model (#120) and of the
claim-writing model (#50).

One request, a tool loop over exactly the tools the request offers, then one structured response
(ADR 0008). The single seam is `create`, a `messages.create`-shaped callable: tests pass a replay of
recorded responses, so nothing but the smoke command reaches the real model. Against the platform,
`create` streams the response and returns its final message (ADR 0013).
"""

import json
import re
import time
from typing import Any, Callable, Mapping

import anthropic
import httpx2 as httpx

from warrant.agent.config import ModelConfig, client
from warrant.agent.interface import AgentOutput, AnswerRequest, Response, ResponseKind, Tool, Usage
from warrant.agent.judge import JudgeCall
from warrant.agent.prompt import SYSTEM, user_message
from warrant.agent.tools import SCHEMAS
from warrant.agent.write_claims import ClaimWritingCall


TRANSIENT_STATUS = frozenset({408, 409, 429})
# An error event inside a stream arrives with the stream's HTTP status, 200, so its type says whether
# it is worth another attempt: the types of the transient statuses above and of 5xx.
TRANSIENT_ERROR_TYPES = frozenset({"rate_limit_error", "api_error", "overloaded_error", "timeout_error"})

# The prompt asks for JSON and no other text, but a model that wraps it in a markdown fence has
# still answered.
FENCE = re.compile(r"\A\s*```[a-zA-Z]*\s*(.*?)```\s*\Z", re.DOTALL)


class CallFailed(Exception):
    """One call did not produce a response: malformed output, or a transient platform error.

    Both end the same way, so they share one type: retried, and then recorded as a failure with
    whatever tokens the attempt spent. A misconfiguration is not one of these — see `_transient`.
    """

    def __init__(self, reason: str, usage: Usage = Usage()):
        super().__init__(reason)
        self.usage = usage


def _transient(error: anthropic.APIError) -> bool:
    """Whether this error is worth another attempt, by the same rule the SDK retries on.

    Everything else - no credentials, no permission, an unknown model, a rejected request - is
    wrong for every question in the run, not for this one, so it is raised and stops the run
    rather than being recorded per question.
    """
    if isinstance(error, anthropic.APIConnectionError):
        return True
    status = getattr(error, "status_code", None)
    if status == 200:  # an error event inside a streamed response
        body = getattr(error, "body", None)
        kind = (body.get("error") or {}).get("type") if isinstance(body, dict) else None
        return kind in TRANSIENT_ERROR_TYPES
    return status is not None and (status in TRANSIENT_STATUS or status >= 500)


def streamed(messages) -> Callable[..., Any]:
    """A `messages.create`-shaped callable that streams the response and returns its final message.

    The SDK refuses a request that is not streamed when its max_tokens could take over ten minutes
    (about 21,000 tokens), and claim writing needs more room than that (ADR 0013). The SDK retries
    the request that opens a stream, with backoff. A failure inside the open stream comes after that
    loop: an error event, or a connection lost mid-stream, which surfaces as the HTTP library's error
    and is turned into the SDK's connection error. So a transient one is retried here, with the SDK's
    count and backoff, as it was when it came back as a failed response."""
    retries = getattr(getattr(messages, "_client", None), "max_retries", anthropic.DEFAULT_MAX_RETRIES)

    def create(**kwargs):
        for retry in range(retries + 1):
            try:
                with messages.stream(**kwargs) as stream:
                    return stream.get_final_message()
            except httpx.TransportError as error:
                failure = _connection_error(error)
            except anthropic.APIStatusError as error:
                if error.status_code != 200:  # the opening request, which the SDK has retried already
                    raise
                failure = error
            if retry == retries or not _transient(failure):
                raise failure
            time.sleep(min(0.5 * 2.0**retry, 8.0))  # the SDK's backoff, without its jitter

    return create


def _connection_error(error: httpx.TransportError) -> anthropic.APIConnectionError:
    try:
        request = error.request
    except RuntimeError:  # an error raised before the request was attached
        request = httpx.Request("POST", "https://bedrock.invalid")
    failure = anthropic.APIConnectionError(message=f"{type(error).__name__}: {error}", request=request)
    failure.__cause__ = error
    return failure


def _unfenced(text: str) -> str:
    """The JSON inside a markdown fence, when the model wrapped it in one."""
    fence = FENCE.match(text)
    return fence.group(1) if fence else text


def _confidence(value) -> float | None:
    """A self-reported confidence between 0 and 1, or none at all."""
    if value is None:
        return None
    confidence = float(value)  # TypeError or ValueError when it is not a number at all
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence outside [0, 1]: {value!r}")
    return confidence


def _text(raw: dict, field: str) -> str:
    """A text field, empty when absent. The scorer reads a refusal's fields as text."""
    value = raw.get(field) or ""
    if not isinstance(value, str):
        raise TypeError(f"{field} is not text: {value!r}")
    return value


def _parse(text: str) -> Response:
    try:
        raw = json.loads(_unfenced(text))
        kind = ResponseKind(raw["kind"])
        confidence = _confidence(raw.get("confidence"))
        missing, alternative, clarification = (_text(raw, f) for f in ("missing", "alternative", "clarification"))
    except (KeyError, TypeError, ValueError, OverflowError) as error:  # OverflowError: a confidence no float holds
        raise CallFailed(f"malformed response: {error}") from error

    # An answer is scored by re-executing its SQL, so an answer without any is not one.
    final_sql = raw.get("final_sql") if kind == ResponseKind.ANSWER else None
    if kind == ResponseKind.ANSWER and not (isinstance(final_sql, str) and final_sql.strip()):
        raise CallFailed("malformed response: an answer with no final SQL")

    return Response(
        kind=kind,
        final_sql=final_sql,
        value=raw.get("value"),
        missing=missing,
        alternative=alternative,
        clarification=clarification,
        confidence=confidence,
    )


class ClaudeAgent:
    def __init__(self, config: ModelConfig, create: Callable[..., Any] | None = None):
        self._config = config
        self._create = create or streamed(client(config).messages)

    def answer(self, request: AnswerRequest, tools: Mapping[str, Tool]) -> AgentOutput:
        spent = Usage()
        failure = ""
        for _ in range(self._config.attempts):
            try:
                response, usage = self._one_call(request, tools)
            except CallFailed as error:
                failure = str(error)
                spent = _add(spent, error.usage)
                continue
            except BaseException as error:
                # An error that stops the run (a misconfiguration, an interrupt) carries the tokens
                # already paid for this answer, so the run can record and count them (#54).
                error.usage = _add(spent, getattr(error, "usage", Usage()))
                raise
            return AgentOutput(response, _add(spent, usage))
        return AgentOutput(None, spent, failure=failure)

    def _one_call(self, request: AnswerRequest, tools: Mapping[str, Tool]) -> tuple[Response, Usage]:
        """One conversation: tool calls until the model stops asking, then its final response."""
        messages: list[dict] = [{"role": "user", "content": user_message(request)}]
        usage = Usage()

        try:
            # ponytail: a flat call ceiling, enough for the single-turn setting; make it a token or
            # wall-clock budget if a condition ever needs the agent to explore further.
            for _ in range(self._config.max_tool_calls + 1):
                try:
                    message = self._create(**self._request(request, messages))
                except anthropic.APIError as error:
                    if not _transient(error):
                        raise
                    raise CallFailed(f"{type(error).__name__}: {error}", usage) from error
                usage = _add(usage, Usage(message.usage.input_tokens, message.usage.output_tokens))
                if message.stop_reason != "tool_use":
                    try:
                        return _parse(_final_text(message)), usage
                    except CallFailed as error:
                        raise CallFailed(str(error), usage) from error
                content = [block.model_dump(exclude_none=True) for block in message.content]
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": _results(message, request, tools)})
        except CallFailed:
            raise
        except BaseException as error:
            # A misconfiguration, or an interrupt during a call or a tool: every turn of the
            # conversation so far was paid for.
            error.usage = usage
            raise

        raise CallFailed(f"the model asked for more than {self._config.max_tool_calls} tool calls", usage)

    def _request(self, request: AnswerRequest, messages: list[dict]) -> dict:
        config = self._config
        sent: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "system": SYSTEM,
            "messages": messages,
            "tools": [SCHEMAS[name] for name in request.tools],
        }
        if config.effort:
            sent["output_config"] = {"effort": config.effort}
        if config.temperature is not None:
            # The SDK dropped `temperature`, which current models reject; send it only when a
            # configuration names a model that still takes one.
            sent["extra_body"] = {"temperature": config.temperature}
        return sent


class ClaudeJudge:
    """The Claude judge model (#120): one call per filled rubric, as one user message with no system
    prompt and no tools. Effort, thinking and max_tokens are the configuration's, which for the
    write line are those fixed for claim writing. No sampling parameter is ever sent (freeze,
    global.judge.sampling), so a configuration that names a temperature is refused."""

    def __init__(self, config: ModelConfig, create: Callable[..., Any] | None = None):
        if config.temperature is not None:
            raise ValueError(f"the judge sends no sampling parameter, but the configuration names temperature {config.temperature}")
        self._config = config
        self._create = create or streamed(client(config).messages)

    def call(self, prompt: str) -> JudgeCall:
        text, usage, failure, _ = _text_call(self._create, self._config, prompt)
        return JudgeCall(text, usage, failure)


class ClaudeClaimWriter:
    """The Claude claim-writing model (#50): one call per sample, the write-claims system prompt and
    one user message, no tools. Effort and max_tokens are the configuration's: effort as fixed before
    the first model call on the freeze's defects, max_tokens as raised before the run's first call
    (ADR 0013); thinking is the model's default and no thinking parameter is sent. No sampling parameter is ever sent (freeze, global.claim_writing.sampling), so a
    configuration that names a temperature is refused."""

    def __init__(self, config: ModelConfig, create: Callable[..., Any] | None = None):
        if config.temperature is not None:
            raise ValueError(f"claim writing sends no sampling parameter, but the configuration names temperature {config.temperature}")
        self._config = config
        self._create = create or streamed(client(config).messages)

    def call(self, system: str, user: str) -> ClaimWritingCall:
        text, usage, failure, stop_reason = _text_call(self._create, self._config, user, system)
        return ClaimWritingCall(text, usage, failure, stop_reason)


def _text_call(create, config: ModelConfig, user: str, system: str | None = None) -> tuple[str | None, Usage, str, str]:
    """One call with no tools and no sampling parameter, for the judge and the claim writer: its text
    output or None, its usage, a failure when there is no text, and its stop reason. A transient
    platform error is a failed call; any other is raised."""
    sent: dict[str, Any] = {"model": config.model, "max_tokens": config.max_tokens}
    if system is not None:
        sent["system"] = system
    sent["messages"] = [{"role": "user", "content": user}]
    if config.effort:
        sent["output_config"] = {"effort": config.effort}
    try:
        message = create(**sent)
    except anthropic.APIError as error:
        if not _transient(error):
            raise
        return None, Usage(), f"{type(error).__name__}: {error}", ""
    usage = Usage(message.usage.input_tokens, message.usage.output_tokens)
    stop_reason = message.stop_reason or ""
    try:
        return _final_text(message), usage, "", stop_reason
    except CallFailed as error:
        return None, usage, str(error), stop_reason


def _add(left: Usage, right: Usage) -> Usage:
    return Usage(
        left.input_tokens + right.input_tokens,
        left.output_tokens + right.output_tokens,
    )


def _final_text(message) -> str:
    text = "\n".join(block.text for block in message.content if block.type == "text")
    if not text.strip():
        raise CallFailed(f"malformed response: no text, stop reason {message.stop_reason}")
    return text


def _results(message, request: AnswerRequest, tools: Mapping[str, Tool]) -> list[dict]:
    """Run every tool call in one assistant message and answer them all in one user message."""
    results = []
    for block in message.content:
        if block.type != "tool_use":
            continue
        results.append({"type": "tool_result", "tool_use_id": block.id, **_run(block, request, tools)})
    return results


def _run(block, request: AnswerRequest, tools: Mapping[str, Tool]) -> dict:
    tool = tools.get(block.name) if block.name in request.tools else None
    if tool is None:
        return {"content": f"the tool {block.name!r} is not offered for this question", "is_error": True}
    try:
        return {"content": json.dumps(tool(**block.input), default=str)}
    except Exception as error:  # a tool's own refusal is the model's to read, not the run's to die on
        return {"content": f"{type(error).__name__}: {error}", "is_error": True}
