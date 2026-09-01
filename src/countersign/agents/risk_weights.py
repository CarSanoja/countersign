"""The arithmetic of the verdict. No model touches a number in this file.

A judge has to be able to recompute the level with the table below and a pen:
look up each distinct signal kind, add the weights, clamp at 1.0, compare
against two thresholds. The model contributes prose and citations; it does not
contribute a weight, a score, a level, or the action that follows from them.

Confidence is recorded on the claim because the schema asks for it, and is
deliberately excluded from the arithmetic: a model that could lower a weight by
lowering its own confidence would be deciding the risk after all.
"""

from collections.abc import Iterable

from countersign.schemas.evidence import Provider
from countersign.schemas.verdict import RiskLevel, SignalKind

SIGNAL_WEIGHTS: dict[SignalKind, float] = {
    SignalKind.BANK_DETAILS_CHANGED: 0.45,
    SignalKind.CONFUSABLE_ALREADY_REGISTERED: 0.35,
    SignalKind.SENDER_DOMAIN_NOT_OFFICIAL: 0.30,
    SignalKind.ENTITY_NOT_FOUND: 0.30,
    SignalKind.ADVERSE_MEDIA: 0.25,
    SignalKind.ADDRESS_NOT_A_BUSINESS: 0.20,
    SignalKind.SENDER_DOMAIN_UNREGISTERED: 0.15,
}

HIGH_THRESHOLD = 0.60
REVIEW_THRESHOLD = 0.25

DECIDING_PROVIDERS: dict[SignalKind, frozenset[Provider]] = {
    SignalKind.SENDER_DOMAIN_NOT_OFFICIAL: frozenset({Provider.SERPAPI, Provider.NAMECOM}),
    SignalKind.SENDER_DOMAIN_UNREGISTERED: frozenset({Provider.NAMECOM}),
    SignalKind.CONFUSABLE_ALREADY_REGISTERED: frozenset({Provider.NAMECOM}),
    SignalKind.BANK_DETAILS_CHANGED: frozenset({Provider.NUTRIENT, Provider.XANO}),
    SignalKind.ENTITY_NOT_FOUND: frozenset({Provider.SERPAPI}),
    SignalKind.ADVERSE_MEDIA: frozenset({Provider.SERPAPI}),
    SignalKind.ADDRESS_NOT_A_BUSINESS: frozenset({Provider.SERPAPI}),
}

ACTION_BY_LEVEL: dict[RiskLevel, str] = {
    RiskLevel.CLEAR: (
        "Proceed on the existing payment instructions. No out-of-band step is required."
    ),
    RiskLevel.REVIEW: (
        "Hold the payment and have a person confirm the bank details out of band, on a "
        "number taken from the existing contract rather than from this document."
    ),
    RiskLevel.HIGH: (
        "Do not pay. Send the counter-document for out-of-band confirmation and route the "
        "envelope to a human signer; no agent in this fleet may execute it."
    ),
}

_MISSING_WEIGHTS = set(SignalKind) - set(SIGNAL_WEIGHTS)
if _MISSING_WEIGHTS:
    raise RuntimeError(f"no weight declared for {sorted(_MISSING_WEIGHTS)}")

_MISSING_PROVIDERS = set(SignalKind) - set(DECIDING_PROVIDERS)
if _MISSING_PROVIDERS:
    raise RuntimeError(f"no deciding provider declared for {sorted(_MISSING_PROVIDERS)}")


def weight_for(kind: SignalKind) -> float:
    return SIGNAL_WEIGHTS[kind]


def deciding_providers(kind: SignalKind) -> frozenset[Provider]:
    """Which provider must back this kind for the signal to mean anything.

    A domain sweep result is the only thing that establishes who holds a
    confusable; a SERP snippet that merely mentions one does not.
    """
    return DECIDING_PROVIDERS[kind]


def distinct_kinds(kinds: Iterable[SignalKind]) -> list[SignalKind]:
    """First occurrence wins, so a repeated kind cannot inflate the score."""
    seen: set[SignalKind] = set()
    ordered: list[SignalKind] = []
    for kind in kinds:
        if kind not in seen:
            seen.add(kind)
            ordered.append(kind)
    return ordered


def score_of(kinds: Iterable[SignalKind]) -> float:
    return min(1.0, sum(weight_for(kind) for kind in distinct_kinds(kinds)))


def level_for(score: float) -> RiskLevel:
    if score >= HIGH_THRESHOLD:
        return RiskLevel.HIGH
    if score >= REVIEW_THRESHOLD:
        return RiskLevel.REVIEW
    return RiskLevel.CLEAR


def recommended_action(level: RiskLevel) -> str:
    return ACTION_BY_LEVEL[level]


def weight_table_lines() -> list[str]:
    """The table as a judge would read it, for the audit record."""
    return [f"{kind.value} = {weight:.2f}" for kind, weight in SIGNAL_WEIGHTS.items()]
