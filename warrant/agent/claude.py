"""The Claude implementation of the answer operation.

One request, a tool loop over exactly the tools the request offers, then one structured response
(ADR 0008). The single seam is `create`, a `messages.create`-shaped callable: tests pass a replay of
recorded responses, so nothing but the smoke command reaches the real model.
"""

import json
from typing import Any, Callable, Mapping

import anthropic

from warrant.agent.config import ModelConfig, client
from warrant.agent.interface import AgentOutput, AnswerRequest, Response, ResponseKind, Tool, Usage
from warrant.agent.prompt import SYSTEM, user_message
from warrant.agent.tools import SCHEMAS


class CallFailed(Exception):
    """One call did not produce a response: malformed output, or the platform would not serve it.

    Both end the same way, so they share one type: retried, and then recorded as a failure with
    whatever tokens the attempt spent. The SDK has already retried its own retryable errors.
    """

    def __init__(self, reason: str, usage: Usage = Usage()):
        super().__init__(reason)
        self.usage = usage


def _parse(text: str) -> Response:
    try:
        raw = json.loads(text)
        kind = ResponseKind(raw["kind"])
    except (KeyError, TypeError, ValueError) as error:
        raise CallFailed(f"malformed response: {error}") from error
    confidence = raw.get("confidence")
    return Response(
        kind=kind,
        final_sql=raw.get("final_sql") if kind == ResponseKind.ANSWER else None,
        value=raw.get("value"),
        missing=raw.get("missing", "") or "",
        alternative=raw.get("alternative", "") or "",
        clarification=raw.get("clarification", "") or "",
        confidence=None if confidence is None else float(confidence),
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
