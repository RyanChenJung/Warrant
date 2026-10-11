"""The agent boundary: a request record goes in, a structured response and token usage come out.

A request record carries what the agent may see and nothing else: never the condition, the
allocation rule, the reading set or the drift state. The tools it names are bound by the harness
and passed beside the record.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol

from warrant.store.claims import KnowledgeStore

Tool = Callable[..., Any]


@dataclass(frozen=True)
class AnswerRequest:
    database: str
    question_id: str
    question: str
    run: int
    schema: str
    store: KnowledgeStore
    tools: tuple[str, ...]


class ResponseKind(StrEnum):
    ANSWER = "answer"
    REFUSAL = "refusal"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class Response:
    """One final response. An answer carries its final SQL, which the pipeline re-executes and scores."""

    kind: ResponseKind
    final_sql: str | None = None
    value: Any = None
    missing: str = ""
    alternative: str = ""
    clarification: str = ""
    confidence: float | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class AgentOutput:
    response: Response
    usage: Usage


class Agent(Protocol):
    def answer(self, request: AnswerRequest, tools: Mapping[str, Tool]) -> AgentOutput:
        """Answer one question in a single turn, calling only the tools offered."""
        ...
