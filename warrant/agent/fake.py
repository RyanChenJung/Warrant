"""A scripted fake agent for tests: no model call, and every request it receives is kept."""

from typing import Callable, Mapping

from warrant.agent.interface import AgentOutput, AnswerRequest, Response, Tool, Usage


class ScriptedAgent:
    def __init__(self, script: Callable[[AnswerRequest, Mapping[str, Tool]], Response]):
        self._script = script
        self.requests: list[AnswerRequest] = []

    def answer(self, request: AnswerRequest, tools: Mapping[str, Tool]) -> AgentOutput:
        self.requests.append(request)
        return AgentOutput(self._script(request, tools), Usage())
