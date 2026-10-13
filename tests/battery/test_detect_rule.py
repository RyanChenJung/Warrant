import pytest

from warrant.battery.gloss.detect import build_context
from warrant.battery.gloss.detect.rule import RuleDetector, dictionary_resolver
from warrant.battery.gloss.dictionary import load_dictionary
from warrant.battery.gloss.evidence import verify, verify_quote
from warrant.battery.gloss.model import AssertionType, QuoteEvidence, Tier


@pytest.fixture
def ran(mini_conn, mini_paths, tmp_path):
    d = load_dictionary(mini_paths["dict"], "WORKORDER", tmp_path / "c")
    ctx = build_context(mini_conn, "wo_history", "2026-08-23", dictionary=d)
    findings = RuleDetector().run(ctx)
    return [f for f in findings if "dictionary states" in f.assertion.statement], d


def test_finds_the_documented_computed_field(ran):
    findings, _ = ran
    assert [f.assertion.subject for f in findings] == ["wo_history.PCACTHRS"]
    assert findings[0].assertion.type is AssertionType.RULE


def test_the_statement_claims_only_what_can_be_proved(ran):
    findings, _ = ran
    s = findings[0].assertion.statement
    assert "dictionary states" in s          # provable
    assert "unconfirmed" in s                # honest about what is not


def test_carries_both_sql_and_quote_evidence(ran):
    findings, _ = ran
    kinds = {type(e).__name__ for e in findings[0].assertion.evidence}
    assert kinds == {"SqlEvidence", "QuoteEvidence"}
    assert findings[0].assertion.tier is Tier.MEASURED


def test_asks_whether_the_organisation_follows_the_definition(ran):
    findings, _ = ran
    q = findings[0].question
    assert q is not None
    assert "as documented" in q.text
    assert set(q.options) >= {"yes", "no", "unsure"}


def test_quote_evidence_verifies_against_the_real_source(ran, mini_conn):
    findings, dictionary = ran
    quote_ev = [e for e in findings[0].assertion.evidence
                if isinstance(e, QuoteEvidence)][0]
    assert verify_quote(quote_ev, dictionary_resolver(dictionary)).status == "PASS"
    for e in findings[0].assertion.evidence:
        if not isinstance(e, QuoteEvidence):
            assert verify(mini_conn, e).status == "PASS"


def test_a_fabricated_quote_is_caught_by_string_comparison(ran):
    _, dictionary = ran
    fake = QuoteEvidence(quote="calculated by dividing by the phase of the moon",
                         source="vendor_dictionary",
                         locator="WORKORDER.PCACTHRS.REMARKS")
    result = verify_quote(fake, dictionary_resolver(dictionary))
    assert result.status == "DRIFT"
    assert "not present" in result.message


def test_a_quote_citing_a_missing_location_is_an_error(ran):
    _, dictionary = ran
    bad = QuoteEvidence(quote="anything", source="vendor_dictionary",
                        locator="WORKORDER.NOSUCHFIELD.REMARKS")
    assert verify_quote(bad, dictionary_resolver(dictionary)).status == "ERROR"
