"""The judge operation (#120): whether a claim holds, fails or is not addressed under each reading of
its slot, by the frozen rubric and the frozen combination (freeze/write_line.yaml, global.judge).

The operation sends the filled rubric until it has three valid answers, re-sending a failed or
invalid call at most three times, and gives each reading the label at least two valid calls give,
else not_addressed. A judge model makes one call; the Claude judge and the scripted fake are the two
judge models, so the combination is the same code for both.
"""

import hashlib
import json
import string
from collections import Counter
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Protocol

from warrant.agent.interface import Usage
from warrant.store.claims import Slot

REPO = Path(__file__).resolve().parents[2]

# How the rubric is filled and sent: one user message, no system prompt, the readings lettered in
# the slot's reading order. Stored with every judgement; bump it whenever the filling below changes.
JUDGE_PROMPT_VERSION = "1"

PLACEHOLDERS = ("{claim_kind}", "{subject}", "{claim}", "{readings}")


class Label(StrEnum):
    HOLDS = "holds"
    FAILS = "fails"
    NOT_ADDRESSED = "not_addressed"


@dataclass(frozen=True)
class JudgeRequest:
    """A claim, its slot and the slot's readings as (reading id, statement), in the slot's reading
    order. The judge model sees the statements only, lettered, never the ids, forms or holds flags."""

    slot: Slot
    claim: str
    readings: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class JudgeCall:
    """One call's text output, or a failure that says why there is none."""

    text: str | None
    usage: Usage = Usage()
    failure: str = ""


class JudgeModel(Protocol):
    def call(self, prompt: str) -> JudgeCall:
        """Send one filled rubric and return the text output."""
        ...


@dataclass(frozen=True)
class JudgeMethod:
    """The judge method of the freeze: its rubric and the numbers of valid and extra calls."""

    rubric_path: str
    template: str
    rubric_sha256: str
    valid_calls: int = 3
    extra_calls: int = 3

    @classmethod
    def from_freeze(cls, global_part: Mapping, repo: Path = REPO) -> "JudgeMethod":
        """Read the method from the freeze's global part, refusing one other than the method built
        here: the rubric file it names, the three labels, three valid calls and three extra."""
        judge = global_part["judge"]
        if list(judge.get("profile") or ()) != [label.value for label in Label]:
            raise ValueError(f"the judge's profile is {judge.get('profile')!r}, not holds, fails, not_addressed")
        if "three calls per slot claim" not in judge.get("operation", ""):
            raise ValueError("the judge operation built here makes three calls per slot claim")
        if "at most three extra calls per claim" not in judge.get("valid_call", ""):
            raise ValueError("the judge operation built here re-sends at most three extra calls per claim")
        path = repo / judge["rubric"]
        if not path.is_file():
            raise ValueError(f"the judge's rubric {judge['rubric']} does not exist")
        text = path.read_text()
        if "## Prompt" not in text:
            raise ValueError(f"{judge['rubric']} has no '## Prompt' section")
        template = text.split("## Prompt", 1)[1].strip()
        if missing := [p for p in PLACEHOLDERS if p not in template]:
            raise ValueError(f"the rubric's prompt lacks {', '.join(missing)}")
        return cls(judge["rubric"], template, hashlib.sha256(path.read_bytes()).hexdigest())

    def record(self) -> dict:
        return {
            "operation": "judge",
            "rubric": self.rubric_path,
            "rubric_sha256": self.rubric_sha256,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "valid_calls": self.valid_calls,
            "extra_calls": self.extra_calls,
            "combination": "the label at least two valid calls give, else not_addressed",
        }


def prompt(template: str, request: JudgeRequest) -> tuple[str, dict[str, str]]:
    """The filled rubric, and which reading id each letter stands for."""
    if len(request.readings) > len(string.ascii_uppercase):
        raise ValueError(f"a slot with {len(request.readings)} readings has more than one letter each")
    letters = dict(zip(string.ascii_uppercase, (reading_id for reading_id, _ in request.readings)))
    readings = "\n".join(f"{letter}. {statement}" for letter, (_, statement) in zip(letters, request.readings))
    # The rubric's own JSON example has braces, so the placeholders are replaced, not formatted.
    text = template
    for placeholder, value in zip(
        PLACEHOLDERS, (request.slot.claim_kind, request.slot.subject, request.claim, readings)
    ):
        text = text.replace(placeholder, value)
    return text, letters


def _first_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        return value
    raise ValueError("no JSON object in the text output")


def parse(text: str, letters) -> dict[str, Label]:
    """A call's answer: the first JSON object in its text output, valid when it gives exactly one
    label, matched exactly, for every reading letter and no other key."""
    answer = _first_object(text)
    if set(answer) != set(letters):
        raise ValueError(f"the answer's keys {sorted(answer)} are not the reading letters {sorted(letters)}")
    labels = {}
    for letter in letters:
        if answer[letter] not in tuple(Label):
            raise ValueError(f"reading {letter} has no valid label: {answer[letter]!r}")
        labels[letter] = Label(answer[letter])
    return labels


@dataclass(frozen=True)
class Judgement:
    """A claim's combined labels per reading id, with every answer of its run and its method."""

    slot: Slot
    claim: str
    reading_order: tuple[str, ...]
    labels: dict[str, Label]
    # Each valid call's labels, by reading id.
    valid: tuple[dict[str, Label], ...]
    # Every call's text output, or "failed: <why>", in the order sent; discarded calls included.
    answers: tuple[str, ...]
    resent: int
    # The readings with no label two valid calls share, three-way splits included.
    splits: tuple[str, ...]
    usage: Usage
    method: dict = field(default_factory=dict)
    # An identical claim string on the slot was judged before, so this one agrees without a call.
    without_a_call: bool = False

    def record(self) -> dict:
        return {
            "slot": {"claim_kind": self.slot.claim_kind, "subject": self.slot.subject},
            "claim": self.claim,
            "reading_order": list(self.reading_order),
            "labels": {reading: label.value for reading, label in self.labels.items()},
            "valid": [{reading: label.value for reading, label in call.items()} for call in self.valid],
            "answers": list(self.answers),
            "resent": self.resent,
            "splits": list(self.splits),
            "without_a_call": self.without_a_call,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "method": self.method,
        }


def combine(valid: list[dict[str, Label]], readings: tuple[str, ...]) -> tuple[dict[str, Label], tuple[str, ...]]:
    """Each reading's label at least two valid calls give, else not_addressed, and the readings split."""
    labels, splits = {}, []
    for reading in readings:
        counts = Counter(call[reading] for call in valid).most_common(1)
        if counts and counts[0][1] >= 2:
            labels[reading] = counts[0][0]
        else:
            labels[reading] = Label.NOT_ADDRESSED
            splits.append(reading)
    return labels, tuple(splits)


class Judge:
    """The judge operation for one run: each claim on a slot is judged once, and an identical claim
    string on the same slot agrees with it without a call."""

    def __init__(self, model: JudgeModel, method: JudgeMethod):
        self._model = model
        self._method = method
        self._judged: dict[tuple[Slot, str], Judgement] = {}

    def judge(self, request: JudgeRequest) -> Judgement:
        key = (request.slot, request.claim)
        if key in self._judged:
            return replace(self._judged[key], valid=(), answers=(), resent=0, usage=Usage(), without_a_call=True)
        text, letters = prompt(self._method.template, request)
        valid, answers, usage = [], [], Usage()
        limit = self._method.valid_calls + self._method.extra_calls
        while len(valid) < self._method.valid_calls and len(answers) < limit:
            call = self._model.call(text)
            usage = Usage(usage.input_tokens + call.usage.input_tokens, usage.output_tokens + call.usage.output_tokens)
            if call.text is None:
                answers.append(f"failed: {call.failure}")
                continue
            answers.append(call.text)
            try:
                labels = parse(call.text, letters)
            except ValueError:
                continue
            valid.append({letters[letter]: label for letter, label in labels.items()})
        order = tuple(reading_id for reading_id, _ in request.readings)
        labels, splits = combine(valid, order)
        judgement = Judgement(
            slot=request.slot,
            claim=request.claim,
            reading_order=order,
            labels=labels,
            valid=tuple(valid),
            answers=tuple(answers),
            resent=max(0, len(answers) - self._method.valid_calls),
            splits=splits,
            usage=usage,
            method=self._method.record(),
        )
        self._judged[key] = judgement
        return judgement
