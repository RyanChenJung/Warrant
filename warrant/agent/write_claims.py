"""The write-claims operation (#50): the agent writes claims about one database before any question.

It is given the database's schema, its normalised baseline battery output and the business-term list
the probe questions use (freeze, `global.claim_writing`), and nothing else: no condition, rule,
reading set or slot, no query tool and no documentation. Each claim carries a claim kind, a subject,
a statement, a self-reported confidence and the battery findings it cites. The prompt teaches each
claim kind's subject format (a table for coverage, a lower-case table.column otherwise) and names no
slot subject, in its instructions or its examples, so it does not point to where the defects are
(#50, 2026-10-21). A claim's kind and subject are kept exactly as the agent wrote them, a kind
outside the five included (#53); whether a claim fills a slot is decided later, by exact kind and
subject, so such a claim is out-of-slot.

The operation sends the prompt until it has a valid answer, at most `attempts` times, keeping every
attempt's text and tokens; when a call raises, the attempts paid for ride on the error as `partial`.
A claim-writing model makes one call; the Claude claim writer and the scripted fake are the two
models, so parsing and re-sending are the same code for both. Each call of the operation is one
claim-writing sample (CONTEXT.md).
"""

import json
from dataclasses import dataclass
from numbers import Real
from typing import Mapping, Protocol

from warrant.agent.interface import Usage

# Stored with every sample; bump it whenever the wording of the system prompt or the user message
# below changes.
WRITE_CLAIMS_PROMPT_VERSION = "1"

WRITE_CLAIMS_SYSTEM = """\
You write down what a database's data shows about its meaning, before anyone asks a question about \
it. Your claims are kept and given to an analyst who answers questions about this database later, \
so write only what you can state from what you are shown: the schema, the findings of automated \
checks run on the data, and the business terms the questions use. You cannot query the data, and \
there is no documentation.

Each claim is about one subject and is one of five kinds:

- "coverage": what population a table was cut from, what it silently omits, or what data does not \
exist anywhere. The subject is the table, for example "shipments".
- "grain": what one row of a table counts as. The subject is the column that identifies a row, for \
example "shipments.shipmentid".
- "value_meaning": what the stored values of a column stand for, such as codes, units or the \
direction of a scale. The subject is the column, for example "shipments.weightunit".
- "column_formula": which arithmetic relation between columns a business quantity names. The \
subject is the column that holds the quantity, for example "invoices.totaldue".
- "term_boundary": what a business term includes, as an extension or a threshold. The subject is \
the column the term is about, for example "customers.homecountry".

Write a table name as the subject of a coverage claim, and a table.column otherwise, in lower case \
as the schema and the checks write names.

End with one JSON object that has a claims key, and no text after it:

{"claims": [{"claim_kind": "...", "subject": "...", "statement": "...", "confidence": 0.0, \
"cites": ["..."]}]}

- "statement": the claim, in one or two plain sentences.
- "confidence": your own confidence that the claim is true, between 0 and 1.
- "cites": the statements of the check findings the claim rests on, copied as written; an empty \
list when it rests on the schema or the terms alone.

Write every claim the data supports, and none you would only be guessing.\
"""


@dataclass(frozen=True)
class BusinessTerms:
    """The named quantities the probe questions use, without definitions, and the frozen grounding of
    a term to its column (freeze, `global.claim_writing`), as (term, table.column) pairs."""

    terms: tuple[str, ...]
    grounding: tuple[tuple[str, str], ...]


def business_terms(raw: Mapping) -> BusinessTerms:
    """One database's entry of a run configuration's `business_terms`: a list of terms, and a grounding
    from some of those terms to their columns."""
    terms = raw.get("terms", [])
    if not (isinstance(terms, list) and all(isinstance(t, str) and t.strip() for t in terms)):
        raise ValueError(f"business terms must be a list of non-empty strings, not {terms!r}")
    grounding = raw.get("grounding") or {}
    if not isinstance(grounding, Mapping):
        raise ValueError(f"a business-term grounding maps terms to columns, not {grounding!r}")
    for term, column in grounding.items():
        if term not in terms or not (isinstance(column, str) and column.strip()):
            raise ValueError(f"a business-term grounding must map a listed term to a column: {term!r}: {column!r}")
    return BusinessTerms(tuple(terms), tuple(grounding.items()))


@dataclass(frozen=True)
class WriteClaimsRequest:
    """What the agent may see when it writes claims about a database, and nothing else."""

    database: str
    schema: str
    battery_output: str  # the normalised baseline battery output, one JSON record per line
    business_terms: BusinessTerms


def _terms(terms: BusinessTerms) -> str:
    grounded = dict(terms.grounding)
    lines = [f"- {term} (stored in {grounded[term]})" if term in grounded else f"- {term}" for term in terms.terms]
    return "\n".join(lines) if lines else "(none)"


def user_message(request: WriteClaimsRequest) -> str:
    return (
        f"Database: {request.database}\n\n"
        f"Schema:\n{request.schema}\n\n"
        "Findings of the automated checks, one JSON object per line (check, subject, statement, "
        f"evidence):\n{request.battery_output.strip()}\n\n"
        f"Business terms the questions use:\n{_terms(request.business_terms)}"
    )


@dataclass(frozen=True)
class WrittenClaim:
    """One claim as the agent wrote it, its kind and subject exactly as written."""

    claim_kind: str
    subject: str
    statement: str
    confidence: float
    cites: tuple[str, ...]


REQUIRED = ("claim_kind", "subject", "statement", "confidence")


class _Object(dict):
    """A decoded JSON object that remembers whether one of its keys was given more than once."""

    repeated = False


def _object(pairs: list) -> _Object:
    obj = _Object(pairs)
    obj.repeated = len(obj) != len(pairs)
    return obj


def _repeated(value) -> bool:
    if isinstance(value, _Object) and value.repeated:
        return True
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return any(_repeated(child) for child in children)


def _answer_object(text: str) -> dict:
    """The first JSON object in the text that has a claims key. The message shows the battery's
    findings as JSON objects, so an answer that quotes one before its own object is read past it."""
    decoder = json.JSONDecoder(object_pairs_hook=_object)
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "claims" in value:
            return value
    raise ValueError("no JSON object with a claims key in the text output")


def _claim(raw) -> WrittenClaim:
    if not isinstance(raw, dict):
        raise ValueError(f"a claim is not an object: {raw!r}")
    if missing := [field for field in REQUIRED if field not in raw]:
        raise ValueError(f"a claim lacks {', '.join(missing)}")
    for field in ("claim_kind", "subject", "statement"):
        if not (isinstance(raw[field], str) and raw[field].strip()):
            raise ValueError(f"a claim's {field} is not text: {raw[field]!r}")
    confidence = raw["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, Real) or not 0 <= confidence <= 1:
        raise ValueError(f"a claim's confidence is not a number from 0 to 1: {confidence!r}")
    cites = raw.get("cites", [])
    if not (isinstance(cites, list) and all(isinstance(cite, str) for cite in cites)):
        raise ValueError(f"a claim's cites are not a list of text: {cites!r}")
    return WrittenClaim(raw["claim_kind"], raw["subject"], raw["statement"], float(confidence), tuple(cites))


def parse(text: str) -> tuple[WrittenClaim, ...]:
    """An answer: the first JSON object in the text output that has a claims key, its `claims` a list
    whose every claim is well formed. A key given twice anywhere in that object, or a malformed claim,
    makes the whole answer invalid; any other key is ignored. A kind outside the five is kept."""
    answer = _answer_object(text)
    if _repeated(answer):
        raise ValueError("a key is given more than once in the answer")
    claims = answer["claims"]
    if not isinstance(claims, list):
        raise ValueError(f"the answer's claims are not a list: {claims!r}")
    return tuple(_claim(raw) for raw in claims)


@dataclass(frozen=True)
class ClaimWritingCall:
    """One call's text output, or a failure that says why there is none, with the call's stop
    reason."""

    text: str | None
    usage: Usage = Usage()
    failure: str = ""
    stop_reason: str = ""


class ClaimWritingModel(Protocol):
    def call(self, system: str, user: str) -> ClaimWritingCall:
        """Send the system prompt and one user message and return the text output."""
        ...


@dataclass(frozen=True)
class WriteClaimsOutput:
    """The claims of a valid answer, every attempt's text output (or "failed: <why>") in the order
    sent, the tokens of every attempt, and a failure when no attempt gave a valid answer."""

    claims: tuple[WrittenClaim, ...]
    outputs: tuple[str, ...]
    usage: Usage
    failure: str = ""

    def record(self) -> dict:
        """The claim-writing sample's fields for a `sample` record (#53); the run adds the database,
        the sample number and the record type. A claim's cites are not repeated: they are in the
        outputs, and the store's Toulmin data takes them from sample 1."""
        return {
            "claims": [{"slot": {"claim_kind": c.claim_kind, "subject": c.subject}, "statement": c.statement,
                        "confidence": c.confidence} for c in self.claims],
            "outputs": list(self.outputs),
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "failure": self.failure,
        }


def write_claims(model: ClaimWritingModel, request: WriteClaimsRequest, attempts: int) -> WriteClaimsOutput:
    """One claim-writing sample: the prompt sent until an answer is valid, at most `attempts` times.

    An invalid answer whose call stopped for another reason than the end of its turn, such as
    max_tokens, says so in its failure. A call that raises (an error that stops the run, or Ctrl-C)
    carries the attempts paid for so far as `partial` before it goes on."""
    if attempts < 1:
        raise ValueError(f"attempts must be at least 1, not {attempts}")
    user = user_message(request)
    outputs, spent, failure = [], Usage(), ""
    for _ in range(attempts):
        try:
            call = model.call(WRITE_CLAIMS_SYSTEM, user)
        except BaseException as error:
            error.partial = WriteClaimsOutput((), tuple(outputs), spent, failure=f"{type(error).__name__}: {error}")
            raise
        spent = Usage(spent.input_tokens + call.usage.input_tokens, spent.output_tokens + call.usage.output_tokens)
        if call.text is None:
            failure = call.failure or "failed call"
            outputs.append(f"failed: {failure}")
            continue
        outputs.append(call.text)
        try:
            claims = parse(call.text)
        except ValueError as error:
            failure = f"invalid answer: {error}"
            if call.stop_reason not in ("", "end_turn"):
                failure += f"; stop reason {call.stop_reason}"
            continue
        return WriteClaimsOutput(claims, tuple(outputs), spent)
    return WriteClaimsOutput((), tuple(outputs), spent, failure=failure)
