"""The Claude implementations of the answer operation and of the judge model (#120).

One request, a tool loop over exactly the tools the request offers, then one structured response
(ADR 0008). The single seam is `create`, a `messages.create`-shaped callable: tests pass a replay of
recorded responses, so nothing but the smoke command reaches the real model.
"""

import json
import re
from typing import Any, Callable, Mapping

import anthropic

from warrant.agent.config import ModelConfig, client
from warrant.agent.interface import AgentOutput, AnswerRequest, Response, ResponseKind, Tool, Usage
from warrant.agent.judge import JudgeCall
from warrant.agent.prompt import SYSTEM, user_message
from warrant.agent.tools import SCHEMAS


TRANSIENT_STATUS = frozenset({408, 409, 429})

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
    return status is not None and (status in TRANSIENT_STATUS or status >= 500)


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
    except (KeyError, TypeError, ValueError) as error:
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
        self._create = create or client(config).messages.create

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
            return AgentOutput(response, _add(spent, usage))
        return AgentOutput(None, spent, failure=failure)

    def _one_call(self, request: AnswerRequest, tools: Mapping[str, Tool]) -> tuple[Response, Usage]:
        """One conversation: tool calls until the model stops asking, then its final response."""
        messages: list[dict] = [{"role": "user", "content": user_message(request)}]
        usage = Usage()

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
    write line are those fixed for claim writing; no sampling parameter is sent unless the
    configuration names one, as for the answer operation."""

    def __init__(self, config: ModelConfig, create: Callable[..., Any] | None = None):
        self._config = config
        self._create = create or client(config).messages.create

    def call(self, prompt: str) -> JudgeCall:
        config = self._config
        sent: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if config.effort:
            sent["output_config"] = {"effort": config.effort}
        if config.temperature is not None:
            sent["extra_body"] = {"temperature": config.temperature}
        try:
            message = self._create(**sent)
        except anthropic.APIError as error:
            if not _transient(error):
                raise
            return JudgeCall(None, failure=f"{type(error).__name__}: {error}")
        usage = Usage(message.usage.input_tokens, message.usage.output_tokens)
        try:
            return JudgeCall(_final_text(message), usage)
        except CallFailed as error:
            return JudgeCall(None, usage, failure=str(error))


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
