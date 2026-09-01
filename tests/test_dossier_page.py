"""What the page must show, asserted rather than eyeballed.

The three claims the demo makes are that the verdict leads, that no statement
appears without its source, and that the refused decision is impossible to miss.
Each one is a test here.
"""

import pytest
from pydantic import ValidationError

from countersign.api.dossier_claims import UNSOURCED, render_claim, render_sources
from countersign.api.dossier_page import render_dossier
from countersign.api.dossier_sample import load_sample
from countersign.api.dossier_verdict import NO_VERDICT, no_verdict_reason
from countersign.orchestration.result import AssessmentResult
from countersign.orchestration.stages import SkippedStage, Stage
from countersign.schemas.evidence import Claim, Provider
from countersign.schemas.verdict import RiskLevel, Verdict

STARTED = "2026-08-31T00:00:00Z"


def partial(**overrides: object) -> AssessmentResult:
    return AssessmentResult(
        run_id="run-2",
        document_ref="INV-1.pdf",
        started_at=STARTED,
        finished_at=STARTED,
        **overrides,
    )


@pytest.fixture
def dossier() -> AssessmentResult:
    return load_sample()


def test_sample_is_a_high_verdict_with_a_denied_decision(dossier: AssessmentResult) -> None:
    assert dossier.verdict is not None
    assert dossier.verdict.level is RiskLevel.HIGH
    denials = dossier.denials
    assert [entry.tool for entry in denials] == ["foxit_execute_signature"]
    assert denials[0].capability == "signature.execute"


def test_verdict_leads_the_page(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    verdict_at = page.index('class="verdict verdict--high"')
    trace_at = page.index("<h2>The trace")
    assert verdict_at < page.index("Every claim, with its source") < trace_at
    assert "high risk" in page


def test_score_is_shown_as_arithmetic_a_judge_can_redo(dossier: AssessmentResult) -> None:
    assert "score 0.80 = 0.45 + 0.35" in render_dossier(dossier)


def test_every_claim_carries_a_linked_source(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    assert 'href="https://x8ki-letl-twmt.n7.xano.io/api:v1/vendors/4471"' in page
    assert 'href="https://acrne-supply.com"' in page
    assert UNSOURCED not in page


def test_a_document_id_is_printed_but_never_linked(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    assert '<code class="locator">doc_9f2c1a7e/INV-88214.pdf</code>' in page
    assert 'href="doc_9f2c1a7e' not in page


def test_a_page_box_is_shown_in_human_page_numbers(dossier: AssessmentResult) -> None:
    assert "page 1 · 56%,71%" in render_dossier(dossier)


def test_a_claim_cannot_be_built_without_a_source() -> None:
    with pytest.raises(ValidationError):
        Claim(statement="unsupported", sources=[], confidence=0.5)


def test_an_unsourced_claim_renders_as_a_visible_defect() -> None:
    broken = Claim.model_construct(statement="lost its provenance", sources=[], confidence=0.5)
    assert UNSOURCED in render_claim(broken)
    assert 'class="unsourced"' in render_sources(broken)


def test_the_denied_decision_is_marked_and_explained(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    assert 'class="step step--denied"' in page
    assert '<span class="pill">denied</span>' in page
    assert "held by no agent in the fleet" in page
    assert "a capability reserved to a person" in page
    assert '<span class="tally tally--seal">1 denied</span>' in page


def test_the_agent_is_named_from_the_roster(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    assert "Envelope preparer" in page
    assert "Run harness" in page


def test_skipped_stages_name_the_variable_that_was_missing(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    assert "unset: DOCTAVIAN_API_KEY, DOCTAVIAN_ACCESS_TOKEN" in page
    assert 'class="chip chip--skipped"' in page


def test_a_run_with_nothing_skipped_says_so(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier.model_copy(update={"skipped": []}))
    assert "Nothing was omitted for a missing credential." in page


def test_the_envelope_is_shown_as_a_draft_awaiting_a_person(dossier: AssessmentResult) -> None:
    page = render_dossier(dossier)
    assert "fld_7Kq2ZR8m4pWc" in page
    assert "no email was sent and no signing session exists" in page


def test_a_run_without_a_verdict_says_so_instead_of_reading_as_clear() -> None:
    skipped = SkippedStage(
        stage=Stage.RISK,
        provider=Provider.NUTRIENT,
        reason="no earlier stage produced citable evidence, so no verdict is possible",
    )
    result = partial(skipped=[skipped])
    page = render_dossier(result)
    assert NO_VERDICT in page
    assert "verdict--none" in page
    assert "no verdict" in page
    assert "no earlier stage produced citable evidence" in page
    assert "clear" not in page.split("</style>", 1)[1]
    assert no_verdict_reason(result) == skipped.reason


def test_errors_are_printed_rather_than_swallowed() -> None:
    page = render_dossier(partial(errors=["risk: the model returned nothing"]))
    assert "Stages that failed" in page
    assert "risk: the model returned nothing" in page


def test_hostile_text_is_escaped() -> None:
    verdict = Verdict(
        run_id="run-1",
        level=RiskLevel.REVIEW,
        headline="<img src=x onerror=alert(1)>",
        recommended_action="hold it",
        decided_at=STARTED,
    )
    page = render_dossier(partial(verdict=verdict))
    assert "<img" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page


def test_an_empty_run_still_renders_every_section() -> None:
    page = render_dossier(partial())
    assert "This run recorded no gate decision." in page
    assert "Every claim, with its source" in page
    assert 'class="step step--denied"' not in page
