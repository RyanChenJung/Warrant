"""Scripted fakes for tests: no model call, and every request they receive is kept."""

from typing import Callable, Mapping

from warrant.agent.interface import AgentOutput, AnswerRequest, Response, Tool, Usage
from warrant.agent.judge import JudgeCall


class ScriptedAgent:
    def __init__(self, script: Callable[[AnswerRequest, Mapping[str, Tool]], Response]):
        self._script = script
        self.requests: list[AnswerRequest] = []

    def answer(self, request: AnswerRequest, tools: Mapping[str, Tool]) -> AgentOutput:
        self.requests.append(request)
        return AgentOutput(self._script(request, tools), Usage())


class ScriptedJudge:
    """A judge model whose script gives each call's text output for the filled rubric it is sent,
    or None for a failed call."""

    def __init__(self, script: Callable[[str], str | None]):
        self._script = script
        self.prompts: list[str] = []

    def call(self, prompt: str) -> JudgeCall:
        self.prompts.append(prompt)
        text = self._script(prompt)
        return JudgeCall(text) if text is not None else JudgeCall(None, failure="scripted failure")
