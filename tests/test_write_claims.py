"""The write-claims operation (#50): the agent writes claims about a database from its schema, the
normalised baseline battery output and the business-term list, with no query tool and no
documentation. The prompt teaches each claim kind's subject format and names no slot subject (#50,
2026-10-21). Driven by the scripted fake and by recorded responses; no test reaches a model."""

import dataclasses
import glob
import json
import re
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
import yaml

from warrant.agent.claude import ClaudeClaimWriter
from warrant.agent.config import ModelConfig
from warrant.agent.fake import ScriptedClaimWriter
from warrant.agent.write_claims import (
    WRITE_CLAIMS_PROMPT_VERSION,
    WRITE_CLAIMS_SYSTEM,
    BusinessTerms,
    WriteClaimsRequest,
    business_terms,
    parse,
    user_message,
    write_claims,
)
from warrant.store.claims import ClaimKind

REPO = Path(__file__).resolve().parents[1]
FREEZE = REPO / "freeze" / "write_line.yaml"
CONFIG = ModelConfig(
    provider="bedrock",
    model="anthropic.claude-model-placeholder",
    region="region-placeholder",
    max_tokens=16000,
    effort="high",
    attempts=2,
)
TERMS = BusinessTerms(terms=("wallet balance", "trading fees"), grounding=(("wallet balance", "accountbalances.walletsum"),))
REQUEST = WriteClaimsRequest(
    database="crypto",
    schema='CREATE TABLE "accountbalances" ("walletsum" real);',
    battery_output='{"check":"RULE","evidence":[],"statement":"walletsum equals availsum.","subject":"accountbalances.walletsum"}\n',
    business_terms=TERMS,
)
CLAIM = {
    "claim_kind": "column_formula",
    "subject": "accountbalances.walletsum",
    "statement": "The wallet balance is the available balance plus the frozen balance.",
    "confidence": 0.8,
    "cites": ["walletsum equals availsum."],
}


def answer(*claims, **extra):
    return json.dumps({"claims": list(claims), **extra})


def scripted(*texts):
    """A fake whose calls return the texts in order (None for a failed call)."""
    queue = list(texts)
    return ScriptedClaimWriter(lambda system, user: queue.pop(0))


def test_the_request_carries_the_schema_the_battery_output_and_the_terms_and_nothing_else():
    assert {f.name for f in dataclasses.fields(WriteClaimsRequest)} == {"database", "schema", "battery_output", "business_terms"}
    assert {f.name for f in dataclasses.fields(BusinessTerms)} == {"terms", "grounding"}


def test_the_business_terms_are_read_from_a_run_configurations_entry_for_a_database():
    terms = business_terms({"terms": ["wallet balance", "trading fees"], "grounding": {"wallet balance": "accountbalances.walletsum"}})
    assert terms == TERMS
    assert business_terms({"terms": ["technosignature probability"]}) == BusinessTerms(("technosignature probability",), ())


def test_the_user_message_shows_the_database_its_schema_its_findings_and_its_terms():
    message = user_message(REQUEST)
    assert "Database: crypto" in message
    assert REQUEST.schema in message and REQUEST.battery_output.strip() in message
    assert "- wallet balance (stored in accountbalances.walletsum)" in message and "- trading fees" in message


def _names_of_the_frozen_databases():
    """Every table and column name of crypto and alien the committed battery outputs and the
    freeze's slots name, and their table.column subjects."""
    subjects = {d["slot"]["subject"] for d in yaml.safe_load(FREEZE.read_text())["defects"]}
    for path in glob.glob(str(REPO / "predictions" / "9cfd501f2182-write_line" / "*.jsonl")):
        subjects |= {json.loads(line)["subject"] for line in open(path)}
    return subjects | {part for subject in subjects for part in subject.split(".")}


def test_the_prompt_names_no_slot_subject_and_no_table_or_column_of_the_frozen_databases():
    # The instructions and the message's own framing, not the inputs, which do name the schema.
    empty = WriteClaimsRequest(database="", schema="", battery_output="", business_terms=BusinessTerms((), ()))
    text = (WRITE_CLAIMS_SYSTEM + "\n" + user_message(empty)).lower()
    named = sorted(name for name in _names_of_the_frozen_databases() if re.search(rf"\b{re.escape(name.lower())}\b", text))
    assert named == []


def test_the_prompt_teaches_every_claim_kind_and_its_subject_format():
    for kind in ClaimKind:
        assert f'"{kind.value}"' in WRITE_CLAIMS_SYSTEM
    assert "a table name for coverage" in WRITE_CLAIMS_SYSTEM and "lower-case table.column" in WRITE_CLAIMS_SYSTEM
    assert WRITE_CLAIMS_PROMPT_VERSION == "1"


def test_a_valid_answer_gives_each_claim_with_its_kind_subject_statement_confidence_and_cites():
    output = write_claims(scripted(answer(CLAIM)), REQUEST, attempts=2)
    assert output.failure == ""
    (claim,) = output.claims
    assert (claim.claim_kind, claim.subject, claim.statement, claim.confidence) == (
        "column_formula", "accountbalances.walletsum", CLAIM["statement"], 0.8)
    assert claim.cites == ("walletsum equals availsum.",)
    assert output.outputs == (answer(CLAIM),)


def test_the_answer_is_the_first_json_object_in_the_text_even_after_prose_or_in_a_fence():
    text = "Here are my claims:\n```json\n" + answer(CLAIM) + "\n```\n"
    assert parse(text)[0].subject == "accountbalances.walletsum"


def test_a_subject_is_kept_exactly_as_written_even_outside_the_schema():
    odd = {**CLAIM, "subject": "AccountBalances.WalletSum "}
    assert parse(answer(odd))[0].subject == "AccountBalances.WalletSum "


def test_an_answer_with_no_claims_is_valid():
    output = write_claims(scripted(answer()), REQUEST, attempts=2)
    assert output.claims == () and output.failure == ""


@pytest.mark.parametrize("change", [
    {"claim_kind": "row_meaning"},
    {"claim_kind": "Coverage"},
    {"subject": ""},
    {"subject": 3},
    {"statement": "  "},
    {"confidence": 1.5},
    {"confidence": True},
    {"confidence": "0.8"},
    {"cites": "walletsum equals availsum."},
    {"cites": [1]},
])
def test_an_invalid_claim_makes_the_answer_invalid(change):
    with pytest.raises(ValueError):
        parse(answer({**CLAIM, **change}))


@pytest.mark.parametrize("key", ["claim_kind", "subject", "statement", "confidence", "cites"])
def test_a_claim_lacking_a_field_makes_the_answer_invalid(key):
    with pytest.raises(ValueError):
        parse(answer({k: v for k, v in CLAIM.items() if k != key}))


@pytest.mark.parametrize("text", ["no json here", '{"claim": []}', '{"claims": {"a": 1}}', '{"claims": [], "claims": []}', '{"claims": ["a claim"]}'])
def test_an_answer_without_a_claims_list_is_invalid(text):
    with pytest.raises(ValueError):
        parse(text)


def test_an_invalid_answer_is_re_sent_and_every_attempts_text_is_kept():
    output = write_claims(scripted("not json", answer(CLAIM)), REQUEST, attempts=2)
    assert output.failure == "" and len(output.claims) == 1
    assert output.outputs == ("not json", answer(CLAIM))


def test_when_every_attempt_fails_the_output_is_a_failure_with_no_claims_and_every_text_kept():
    output = write_claims(scripted("not json", None), REQUEST, attempts=2)
    assert output.claims == () and output.failure
    assert output.outputs[0] == "not json" and output.outputs[1].startswith("failed: ")


def test_the_fake_receives_the_system_prompt_and_the_user_message():
    fake = scripted(answer())
    write_claims(fake, REQUEST, attempts=1)
    assert fake.prompts == [(WRITE_CLAIMS_SYSTEM, user_message(REQUEST))]


def test_the_sample_record_holds_the_claims_without_their_cites_the_outputs_and_the_tokens():
    record = write_claims(scripted(answer(CLAIM)), REQUEST, attempts=1).record()
    assert record == {
        "claims": [{"slot": {"claim_kind": "column_formula", "subject": "accountbalances.walletsum"},
                    "statement": CLAIM["statement"], "confidence": 0.8}],
        "outputs": [answer(CLAIM)],
        "input_tokens": 0,
        "output_tokens": 0,
        "failure": "",
    }


def status_error(cls, status):
    request = httpx.Request("POST", "https://bedrock.example/v1/messages")
    return cls(f"status {status}", response=httpx.Response(status, request=request), body=None)


def test_the_claude_claim_writer_sends_one_user_message_with_the_system_prompt_and_no_sampling_parameter(replay):
    create = replay("write_claims")
    output = write_claims(ClaudeClaimWriter(CONFIG, create), REQUEST, attempts=2)
    assert output.failure == "" and output.claims[0].subject == "accountbalances.walletsum"
    assert (output.usage.input_tokens, output.usage.output_tokens) == (3000, 400)
    (sent,) = create.calls
    assert sent["model"] == CONFIG.model and sent["max_tokens"] == 16000
    assert sent["system"] == WRITE_CLAIMS_SYSTEM
    assert sent["messages"] == [{"role": "user", "content": user_message(REQUEST)}]
    assert sent["output_config"] == {"effort": "high"}
    assert not {"temperature", "top_p", "top_k", "extra_body", "thinking", "tools"} & sent.keys()


def test_an_invalid_recorded_answer_is_re_sent_and_the_usage_of_both_attempts_is_summed(replay):
    output = write_claims(ClaudeClaimWriter(CONFIG, replay("write_claims_invalid", "write_claims")), REQUEST, attempts=2)
    assert output.failure == "" and len(output.outputs) == 2
    assert (output.usage.input_tokens, output.usage.output_tokens) == (3000 + 3000, 300 + 400)


def test_a_transient_platform_error_is_a_failed_attempt_that_is_re_sent(replay):
    recorded = replay("write_claims")
    errors = [status_error(anthropic.RateLimitError, 429)]

    def create(**kwargs):
        if errors:
            raise errors.pop()
        return recorded(**kwargs)

    output = write_claims(ClaudeClaimWriter(CONFIG, create), REQUEST, attempts=2)
    assert output.failure == "" and output.outputs[0].startswith("failed: RateLimitError")


def test_a_misconfiguration_stops_the_operation_instead_of_being_re_sent():
    def create(**kwargs):
        raise status_error(anthropic.PermissionDeniedError, 403)

    with pytest.raises(anthropic.PermissionDeniedError):
        write_claims(ClaudeClaimWriter(CONFIG, create), REQUEST, attempts=2)


def test_a_claim_writer_configuration_that_names_a_temperature_is_refused(replay):
    with pytest.raises(ValueError, match="temperature"):
        ClaudeClaimWriter(dataclasses.replace(CONFIG, temperature=0.0), replay("write_claims"))
