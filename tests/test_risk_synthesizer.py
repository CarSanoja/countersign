"""The rejection rule is the product claim of this agent, so it is asserted.

Every model here is a fake. The ADC is not the point: a verdict that cannot be
reproduced without a network was never auditable to begin with.
"""

import json

import pytest
from autocurricula.agents.base import parse_model_json

from countersign.agents.risk_draft import DraftVerdict
from countersign.agents.risk_evidence import EvidenceBundle, EvidenceChannel, EvidenceItem
from countersign.agents.risk_grounding import GroundingFailureKind, check_draft
from countersign.agents.risk_synthesizer import UngroundedVerdictError, synthesize_verdict
from countersign.agents.risk_weights import level_for, score_of
from countersign.schemas.evidence import PageBox, Provider, SourceRef
from countersign.schemas.verdict import RiskLevel, SignalKind

AT = "2026-08-31T10:00:00Z"
EXTRACTION = EvidenceChannel.EXTRACTION
SWEEP = EvidenceChannel.DOMAIN_SWEEP
VERIFY = EvidenceChannel.VERIFICATION

DOC = "Remit to IBAN LT12 3250 0000 0000 0001, replacing the account previously on file."
REGISTRY = "acrnecorp.com is registered and held by a third party since 2026-08-02."
NEWS = "Acme Corp has been under investigation for invoice fraud since June."


def item(evidence_id, channel, provider, locator, text, box=None):
    source = SourceRef(
        provider=provider, locator=locator, box=box, snippet="", retrieved_at=AT
    )
    return EvidenceItem(evidence_id=evidence_id, channel=channel, text=text, source=source)


@pytest.fixture
def bundle():
    box = PageBox(page=2, left=0.1, top=0.4, width=0.6, height=0.05)
    return EvidenceBundle(
        run_id="run-7",
        subject="Acme Corp",
        items=[
            item("E1", EXTRACTION, Provider.NUTRIENT, "invoice-2291.pdf", DOC, box),
            item("E2", SWEEP, Provider.NAMECOM, "acrnecorp.com", REGISTRY),
            item("E3", VERIFY, Provider.SERPAPI, "https://news.example/probe", NEWS),
        ],
    )


def signal(kind, statement, citations, confidence=0.8):
    claim = {"statement": statement, "confidence": confidence, "citations": citations}
    return {"kind": kind, "claim": claim}


def draft_json(signals):
    body = {"headline": "Payment redirected on a lookalike domain", "signals": signals}
    return json.dumps(body)


def fixed_model(*responses):
    replies = list(responses)
    prompts: list[str] = []

    async def call(prompt: str) -> str:
        prompts.append(prompt)
        return replies.pop(0) if len(replies) > 1 else replies[0]

    call.prompts = prompts
    return call


BANK = signal(
    "bank_details_changed",
    "The invoice redirects payment to a new IBAN.",
    [{"evidence_id": "E1", "quote": "replacing the account previously on file"}],
)
CONFUSABLE = signal(
    "confusable_already_registered",
    "A homoglyph of the official domain is already held by someone else.",
    [{"evidence_id": "E2", "quote": "held by a third party"}],
)
GOOD = [BANK, CONFUSABLE]


async def test_a_grounded_draft_becomes_a_verdict_a_judge_can_recompute(bundle):
    verdict = await synthesize_verdict(bundle, model=fixed_model(draft_json(GOOD)), decided_at=AT)
    assert verdict.run_id == "run-7"
    assert [s.weight for s in verdict.signals] == [0.45, 0.35]
    assert verdict.score == pytest.approx(0.80)
    assert verdict.level is RiskLevel.HIGH
    assert verdict.signals[0].claim.sources[0].locator == "invoice-2291.pdf"
    assert verdict.signals[0].claim.sources[0].box.page == 2


async def test_an_invented_source_is_rejected_and_the_retry_is_told_why(bundle):
    invented = [
        signal(
            "adverse_media",
            "Acme is under investigation.",
            [{"evidence_id": "E9", "quote": "under investigation for invoice fraud"}],
        )
    ]
    model = fixed_model(draft_json(invented), draft_json(GOOD))
    verdict = await synthesize_verdict(bundle, model=model, decided_at=AT)
    assert verdict.level is RiskLevel.HIGH
    assert "unknown_source" in model.prompts[1] and "E9" in model.prompts[1]


async def test_a_plausible_url_that_was_never_fetched_does_not_pass(bundle):
    """The shape of a locator proves nothing. Only the index does."""
    forged = [
        signal(
            "adverse_media",
            "Acme is under investigation.",
            [{"evidence_id": "https://news.example/probe", "quote": "invoice fraud"}],
        )
    ]
    with pytest.raises(UngroundedVerdictError) as raised:
        await synthesize_verdict(bundle, model=fixed_model(draft_json(forged)), attempts=2)
    assert raised.value.attempts == 2
    assert raised.value.failures[0].kind is GroundingFailureKind.UNKNOWN_SOURCE


async def test_a_quote_that_is_not_in_the_collected_text_is_rejected(bundle):
    made_up = [
        signal(
            "adverse_media",
            "Acme was fined by the regulator.",
            [{"evidence_id": "E3", "quote": "fined 4 million euros by the regulator"}],
        )
    ]
    with pytest.raises(UngroundedVerdictError) as raised:
        await synthesize_verdict(bundle, model=fixed_model(draft_json(made_up)), attempts=1)
    assert raised.value.failures[0].kind is GroundingFailureKind.QUOTE_NOT_IN_EVIDENCE


async def test_a_claim_with_no_citation_is_rejected_not_downgraded(bundle):
    uncited = [signal("entity_not_found", "Acme does not exist.", [])]
    with pytest.raises(UngroundedVerdictError) as raised:
        await synthesize_verdict(bundle, model=fixed_model(draft_json(uncited)), attempts=1)
    assert raised.value.failures[0].kind is GroundingFailureKind.NO_CITATION


def test_a_signal_cited_to_the_wrong_kind_of_provider_is_rejected(bundle):
    misattributed = [
        signal(
            "confusable_already_registered",
            "A lookalike domain is held by someone else.",
            [{"evidence_id": "E1", "quote": "replacing the account previously on file"}],
        )
    ]
    draft = DraftVerdict.model_validate(parse_model_json(draft_json(misattributed)))
    assert check_draft(draft, bundle)[0].kind is GroundingFailureKind.WRONG_PROVIDER


async def test_a_deterministically_established_signal_cannot_be_dropped(bundle):
    required = bundle.model_copy(
        update={"required_signals": [SignalKind.CONFUSABLE_ALREADY_REGISTERED]}
    )
    with pytest.raises(UngroundedVerdictError) as raised:
        await synthesize_verdict(required, model=fixed_model(draft_json([BANK])), attempts=1)
    assert raised.value.failures[0].kind is GroundingFailureKind.MISSING_REQUIRED_SIGNAL


async def test_a_repeated_kind_cannot_inflate_the_score(bundle):
    repeated = draft_json([BANK, BANK, CONFUSABLE])
    verdict = await synthesize_verdict(bundle, model=fixed_model(repeated), decided_at=AT)
    assert len(verdict.signals) == 2
    assert verdict.score == pytest.approx(0.80)


async def test_the_model_cannot_move_the_level_by_lowering_its_confidence(bundle):
    timid = draft_json([dict(BANK, claim=dict(BANK["claim"], confidence=0.01))])
    verdict = await synthesize_verdict(bundle, model=fixed_model(timid), decided_at=AT)
    assert verdict.signals[0].weight == 0.45
    assert verdict.level is RiskLevel.REVIEW


async def test_an_unparsable_response_is_retried_then_refused(bundle):
    with pytest.raises(UngroundedVerdictError) as raised:
        await synthesize_verdict(bundle, model=fixed_model("not json at all"), attempts=2)
    assert "did not parse" in raised.value.reason


def test_the_threshold_table_is_the_one_a_judge_would_apply():
    assert level_for(score_of([SignalKind.SENDER_DOMAIN_UNREGISTERED])) is RiskLevel.CLEAR
    assert level_for(score_of([SignalKind.ADVERSE_MEDIA])) is RiskLevel.REVIEW
    both = [SignalKind.BANK_DETAILS_CHANGED, SignalKind.ENTITY_NOT_FOUND]
    assert level_for(score_of(both)) is RiskLevel.HIGH
