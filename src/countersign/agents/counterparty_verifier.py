"""The counterparty verifier: is this the entity on the invoice, and is it in trouble?

Three searches, one model call, and a rule that shapes everything else: identity
is decided before adversity. "Acme Corp" returns hundreds of results belonging to
unrelated companies, and a namesake's lawsuit is not this counterparty's problem.
Confusing the two blocks a legitimate payment on invented grounds, which is the
most expensive error this agent can make, so an unresolved identity is reported
as unresolved and never as adverse.

Two things are injected because both are scarce: the model, so the judgement can
be exercised without an ADC, and the searches, so the logic can be exercised
without spending a credit of the 250 the month allows.

A failed assessment is not a clean one. Status says which it was, and nothing
here returns an empty signal list that could be mistaken for a clearance.
"""

from enum import StrEnum

from autocurricula.agents.base import structured_output_with_retry
from autocurricula.schemas.common import StrictBaseModel, utc_now
from pydantic import Field

from countersign.agents.counterparty_address import address_findings
from countersign.agents.counterparty_adverse import adverse_media_findings
from countersign.agents.counterparty_claims import official_site_findings
from countersign.agents.counterparty_evidence import (
    CounterpartyEvidence,
    CounterpartySearches,
    SerpApiSearches,
    gather_evidence,
    search_denials,
)
from countersign.agents.counterparty_judgement import CounterpartyJudgement
from countersign.agents.counterparty_model import (
    CounterpartyModelClient,
    CounterpartyModelError,
    VertexCounterpartyModel,
)
from countersign.agents.counterparty_prompt import SYSTEM_PROMPT, build_user_prompt
from countersign.schemas.evidence import Claim
from countersign.schemas.verdict import RiskSignal

DEFAULT_COUNTRY = "es"
DEFAULT_LANGUAGE = "es"
DEFAULT_WHEN_WINDOW = "2y"
JUDGEMENT_ATTEMPTS = 2


class AssessmentStatus(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    FAILED = "failed"


class CounterpartyAssessment(StrictBaseModel):
    """What the verifier is willing to hand to the risk synthesiser."""

    legal_name: str
    address: str
    status: AssessmentStatus
    official_domain: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    signals: list[RiskSignal] = Field(default_factory=list)
    dismissed_namesakes: list[Claim] = Field(default_factory=list)
    summary: str = ""
    searches_spent: int = 0
    assessed_at: str = Field(min_length=1)
    errors: list[str] = Field(default_factory=list)

    @property
    def usable_for_verdict(self) -> bool:
        """A failed run has no opinion. Reading it as 'no signals' would be a lie."""
        return self.status is not AssessmentStatus.FAILED


async def verify_counterparty(
    legal_name: str,
    address: str,
    *,
    model: CounterpartyModelClient | None = None,
    searches: CounterpartySearches | None = None,
    country_code: str = DEFAULT_COUNTRY,
    language: str = DEFAULT_LANGUAGE,
    when_window: str = DEFAULT_WHEN_WINDOW,
) -> CounterpartyAssessment:
    """Verify one counterparty for three SerpApi credits and one judgement."""
    at = utc_now().isoformat()
    name = legal_name.strip()
    if not name:
        return _failed("", address, at, ["no legal name was extracted; nothing to verify"])
    denials = search_denials()
    if denials:
        return _failed(name, address, at, denials)
    evidence = await gather_evidence(
        name,
        address,
        searches if searches is not None else SerpApiSearches(),
        country_code=country_code,
        language=language,
        when_window=when_window,
    )
    if not evidence.anything_retrieved:
        return _failed(name, address, at, evidence.errors, evidence.searches_spent)
    try:
        judgement = await _judge(name, address, evidence, model or VertexCounterpartyModel())
    except (CounterpartyModelError, ValueError) as error:
        reason = f"{type(error).__name__}: {error}"
        return _failed(name, address, at, [*evidence.errors, reason], evidence.searches_spent)
    return _assemble(name, address, evidence, judgement, at)


async def _judge(
    legal_name: str,
    address: str,
    evidence: CounterpartyEvidence,
    model: CounterpartyModelClient,
) -> CounterpartyJudgement:
    """One call to the strong model, with a single repair attempt on bad JSON."""
    prompt = build_user_prompt(legal_name, address, evidence)

    async def call(repair: str | None) -> str:
        user = prompt if repair is None else f"{prompt}\n\n{repair}"
        return await model.complete(system=SYSTEM_PROMPT, user=user)

    def as_error(message: str, raw: str, cause: Exception) -> Exception:
        return CounterpartyModelError(f"{message}: {cause}")

    return await structured_output_with_retry(
        call, CounterpartyJudgement, as_error, attempts=JUDGEMENT_ATTEMPTS
    )


def _assemble(
    legal_name: str,
    address: str,
    evidence: CounterpartyEvidence,
    judgement: CounterpartyJudgement,
    at: str,
) -> CounterpartyAssessment:
    site_claims, site_signals, domain, site_errors = official_site_findings(
        legal_name, judgement, evidence, at
    )
    media_signals, dismissed, media_errors = adverse_media_findings(
        legal_name, judgement, evidence, at
    )
    address_claims, address_signals, address_errors = address_findings(
        legal_name, address, judgement, evidence, at
    )
    errors = [*evidence.errors, *site_errors, *media_errors, *address_errors]
    signals = [*site_signals, *media_signals, *address_signals]
    return CounterpartyAssessment(
        legal_name=legal_name,
        address=address,
        status=AssessmentStatus.DEGRADED if errors else AssessmentStatus.COMPLETE,
        official_domain=domain,
        claims=[*site_claims, *[signal.claim for signal in media_signals], *address_claims],
        signals=signals,
        dismissed_namesakes=dismissed,
        summary=judgement.summary,
        searches_spent=evidence.searches_spent,
        assessed_at=at,
        errors=errors,
    )


def _failed(
    legal_name: str, address: str, at: str, errors: list[str], spent: int = 0
) -> CounterpartyAssessment:
    return CounterpartyAssessment(
        legal_name=legal_name,
        address=address,
        status=AssessmentStatus.FAILED,
        searches_spent=spent,
        assessed_at=at,
        errors=errors or ["the counterparty could not be verified"],
    )
