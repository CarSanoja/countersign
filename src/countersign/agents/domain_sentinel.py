"""Fleet agent 4: the domain sentinel. Deliberately no model.

Generating confusable variants of a domain and asking a registry which of them
are already owned is deterministic, reproducible and cheap. A model here would
add nondeterminism to the one signal in the pipeline that has to survive an
audit: run this twice on the same invoice and the same names must come back,
because a finance team is going to be asked to justify holding a payment.

Three decisions are load-bearing:

- One call, against PRODUCTION. The sandbox keeps its own registry where almost
  every name is free, so a sweep answered there inverts the signal.
- The sender and the official domain go into the request ahead of the variants,
  so the fifty-name ceiling can only ever drop a generated variant, never the
  two names the sender signals depend on.
- A name the registry did not answer for is recorded as unanswered, never as
  free. Silence is not evidence of availability.
"""

from typing import Any, Protocol

from autocurricula.schemas.common import utc_now
from autocurricula.tools.base import ToolResult

from countersign.agents.capability_gate import gate
from countersign.agents.domain_sentinel_models import DomainSweep, VariantStatus
from countersign.agents.domain_sentinel_signals import sweep_evidence_items, sweep_signals
from countersign.domain.lookalike import HIGH_RISK_KINDS, Variant, generate_variants
from countersign.fleet.roster import DOMAIN_SENTINEL_ID, grants
from countersign.tools.namecom import namecom_check_availability
from countersign.tools.namecom_client import MAX_DOMAINS_PER_CHECK
from countersign.tools.namecom_models import AvailabilityResult, normalise_domains

AGENT_ID = DOMAIN_SENTINEL_ID
TOOL = "namecom_check_availability"
PRODUCTION = "production"
VARIANT_LIMIT = 40

__all__ = [
    "AGENT_ID",
    "PRODUCTION",
    "VARIANT_LIMIT",
    "AvailabilityCheck",
    "DomainSweep",
    "VariantStatus",
    "domain_of",
    "sweep_domains",
    "sweep_evidence_items",
]


class AvailabilityCheck(Protocol):
    """The one tool this agent holds, injectable so a test spends no request."""

    async def __call__(
        self, domain_names: list[str], environment: str = PRODUCTION
    ) -> ToolResult: ...


async def sweep_domains(
    sender_domain: str,
    official_domain: str,
    *,
    check: AvailabilityCheck = namecom_check_availability,
    limit: int = VARIANT_LIMIT,
    environment: str = PRODUCTION,
) -> DomainSweep:
    """Sweep the confusables of the official domain and place the sender among them."""
    sender = domain_of(sender_domain)
    official = domain_of(official_domain)
    at = utc_now().isoformat()
    if not official or "." not in official:
        return _unswept(
            sender,
            official,
            environment,
            at,
            f"{official_domain!r} is not a usable domain, so there is nothing to sweep",
        )
    denial = gate(AGENT_ID, TOOL, grants().get(AGENT_ID, frozenset()))
    if denial is not None:
        return _unswept(sender, official, environment, at, denial.reason)

    variants = generate_variants(official, limit)
    queried = _query_list(sender, official, variants)
    result = await check(domain_names=queried, environment=environment)
    if not result.ok:
        return _unswept(
            sender, official, environment, at, result.error or "the registry gave no answer"
        )

    answers = _answers(result.payload)
    statuses, unanswered = _statuses(variants, answers)
    sender_answer = answers.get(sender)
    sender_is_official = bool(sender) and sender == official
    return DomainSweep(
        sender_domain=sender,
        official_domain=official,
        environment=str(result.payload.get("environment") or environment),
        checked_at=at,
        sender_is_official=sender_is_official,
        sender_registered=None if sender_answer is None else sender_answer.registered,
        official_registered=_registered(answers.get(official)),
        variants=statuses,
        signals=sweep_signals(
            sender_domain=sender,
            official_domain=official,
            sender_is_official=sender_is_official,
            sender_registered=None if sender_answer is None else sender_answer.registered,
            variants=statuses,
            environment=environment,
            at=at,
        ),
        unanswered=unanswered,
        errors=[],
    )


def domain_of(raw: str) -> str:
    """Reduce whatever the extractor found to a bare registrable name."""
    text = raw.strip().lower()
    text = text.split("//")[-1].split("/")[0].split("@")[-1]
    return text.strip().rstrip(".").removeprefix("www.")


def _query_list(sender: str, official: str, variants: list[Variant]) -> list[str]:
    """One request body. The two anchors first, the generated variants after."""
    names = [official]
    if sender and "." in sender and sender != official:
        names.append(sender)
    names.extend(variant.domain_name for variant in variants)
    return normalise_domains(names)[:MAX_DOMAINS_PER_CHECK]


def _answers(payload: dict[str, Any]) -> dict[str, AvailabilityResult]:
    """Read the tool's own parsed entries; an unreadable entry is dropped, not guessed."""
    answers: dict[str, AvailabilityResult] = {}
    for raw in payload.get("results") or []:
        try:
            entry = AvailabilityResult.model_validate(raw)
        except ValueError:
            continue
        answers[entry.domain_name] = entry
    return answers


def _statuses(
    variants: list[Variant], answers: dict[str, AvailabilityResult]
) -> tuple[list[VariantStatus], list[str]]:
    statuses: list[VariantStatus] = []
    unanswered: list[str] = []
    for variant in variants:
        answer = answers.get(variant.domain_name)
        if answer is None:
            unanswered.append(variant.domain_name)
            continue
        statuses.append(
            VariantStatus(
                domain_name=variant.domain_name,
                kind=variant.kind,
                registered=answer.registered,
                high_risk=variant.kind in HIGH_RISK_KINDS,
                premium=answer.premium,
                purchase_price=answer.purchase_price,
            )
        )
    return statuses, unanswered


def _registered(answer: AvailabilityResult | None) -> bool | None:
    return None if answer is None else answer.registered


def _unswept(
    sender: str, official: str, environment: str, at: str, reason: str
) -> DomainSweep:
    """A sweep that did not happen raises no signal and says why."""
    return DomainSweep(
        sender_domain=sender,
        official_domain=official,
        environment=environment,
        checked_at=at,
        sender_is_official=bool(sender) and sender == official,
        errors=[reason],
    )
