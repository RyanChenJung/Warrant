"""The prompt the Claude agent sends, and its version.

The version is stored with every result, so a change here is visible in the records. Bump it
whenever the wording below changes.
"""

from warrant.agent.interface import AnswerRequest
from warrant.store.claims import KnowledgeStore

PROMPT_VERSION = "1"

SYSTEM = """\
You answer one question about a database in a single turn, and your answer is scored by \
re-executing the SQL you report.

Call the tools you are offered as often as you need, then finish with one JSON object and no other \
text. The object has these keys:

- "kind": "answer", "refusal" or "clarification".
- "final_sql": for an answer, the single SQL statement whose result is the answer.
- "value": for an answer, the value or values you report.
- "missing": for a refusal, what you would need in order to answer.
- "alternative": for a refusal, what you can answer instead.
- "clarification": for a clarification request, the one question you would ask.
- "confidence": your own confidence in the response, between 0 and 1.

Refuse rather than guess when the database cannot support an answer, and ask for clarification \
rather than guess when the question itself is ambiguous.\
"""


def _store(store: KnowledgeStore) -> str:
    if not store.claims:
        return "Your knowledge store is empty."
    claims = "\n".join(
        f"- [{claim.slot.claim_kind} of {claim.slot.subject}] {claim.statement}" for claim in store.claims
    )
    return f"What you already know about this database:\n{claims}"


def user_message(request: AnswerRequest) -> str:
    offered = ", ".join(request.tools) if request.tools else "none"
    return (
        f"Database: {request.database}\n\n"
        f"Schema:\n{request.schema}\n\n"
        f"{_store(request.store)}\n\n"
        f"Tools you may call: {offered}\n\n"
        f"Question: {request.question}"
    )
