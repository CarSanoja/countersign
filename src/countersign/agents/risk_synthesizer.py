"""Fleet agent 5: the risk synthesiser.

It fuses extraction, counterparty verification and the domain sweep into one
`Verdict`, and it is defined by what it refuses. A draft whose claims do not
cite a span that was actually collected is rejected and asked for again. It is
not downgraded to a lower confidence, not annotated with a warning, not passed
on for a human to catch: the draft does not become a verdict. After the last
attempt the agent raises, because a verdict nobody can trace is worse than no
verdict at all.

The division of labour is deliberate. The model writes the headline, the
statements and the citations. Every number, the weight of each signal, the
score, the risk level and the action that follows from it, comes from the fixed
table in `risk_weights`, so a judge can recompute the level by hand from the
signals printed on the verdict.

Model: `gemini-3.5-flash`, the slot the roster calls `gemini_pro_model`.
"""

from autocurricula.agents.base import parse_model_json
from autocurricula.core.harness.faithfulness import DEFAULT_MATCH_THRESHOLD
from autocurricula.schemas.common import utc_now

from countersign.agents.risk_draft import DraftSignal, DraftVerdict
from countersign.agents.risk_evidence import EvidenceBundle
from countersign.agents.risk_grounding import GroundingFailure, check_draft, resolve_sources
from countersign.agents.risk_model import FLASH_MODEL, VerdictModel, vertex_model
from countersign.agents.risk_prompt import build_prompt, build_repair, build_schema_repair
from countersign.agents.risk_weights import (
    distinct_kinds,
    level_for,
    recommended_action,
    score_of,
    weight_for,
)
from countersign.fleet.roster import RISK_SYNTHESIZER_ID
from countersign.schemas.evidence import Claim
from countersign.schemas.verdict import RiskSignal, SignalKind, Verdict

AGENT_ID = RISK_SYNTHESIZER_ID
MAX_ATTEMPTS = 3

__all__ = [
    "AGENT_ID",
    "MAX_ATTEMPTS",
    "UngroundedVerdictError",
    "assemble_verdict",
    "synthesize_verdict",
]


class UngroundedVerdictError(RuntimeError):
    """No draft survived the citation check, so no verdict is produced."""

    def __init__(
        self,
        run_id: str,
        attempts: int,
        reason: str,
        failures: list[GroundingFailure] | None = None,
        raw: str = "",
    ) -> None:
        super().__init__(f"verdict for {run_id} rejected after {attempts} attempt(s): {reason}")
        self.run_id = run_id
        self.attempts = attempts
        self.reason = reason
        self.failures = failures or []
        self.raw = raw


async def synthesize_verdict(
    bundle: EvidenceBundle,
    *,
    model: VerdictModel | None = None,
    attempts: int = MAX_ATTEMPTS,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    decided_at: str | None = None,
) -> Verdict:
    """Draft, check every citation against the collected evidence, retry, or refuse.

    `model` is injected so the rule can be exercised without a network; when it
    is omitted the Vertex client is built at call time.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    client = model if model is not None else vertex_model(FLASH_MODEL)
    prompt = build_prompt(bundle)
    failures: list[GroundingFailure] = []
    reason = "the model was never asked"
    raw = ""

    for _ in range(attempts):
        raw = await client(prompt)
        try:
            draft = DraftVerdict.model_validate(parse_model_json(raw))
        except ValueError as error:
            failures = []
            reason = f"the response did not parse as a draft verdict: {error}"
            prompt = build_schema_repair(bundle, str(error))
            continue
        failures = check_draft(draft, bundle, match_threshold=match_threshold)
        if not failures:
            return assemble_verdict(
                draft, bundle, match_threshold=match_threshold, decided_at=decided_at
            )
        reason = "; ".join(failure.as_line() for failure in failures)
        prompt = build_repair(bundle, failures)

    raise UngroundedVerdictError(bundle.run_id, attempts, reason, failures, raw)


def _merge_established(
    bundle: EvidenceBundle, drafted: list[RiskSignal]
) -> list[RiskSignal]:
    """Settled signals win; the model may only add kinds it did not settle.

    The model is asked to reason, not to re-decide a string comparison. Letting
    its draft silently drop an established signal is what made the same invoice
    score differently between runs.
    """
    established = {signal.kind: signal for signal in bundle.established_signals}
    additions = [signal for signal in drafted if signal.kind not in established]
    return list(established.values()) + additions


def assemble_verdict(
    draft: DraftVerdict,
    bundle: EvidenceBundle,
    *,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    decided_at: str | None = None,
) -> Verdict:
    """Turn an accepted draft into a verdict, re-checking on the way in.

    The check runs here as well as in the retry loop, so this stays the only
    door into a Verdict and an ungrounded draft cannot enter through it.
    """
    failures = check_draft(draft, bundle, match_threshold=match_threshold)
    if failures:
        raise UngroundedVerdictError(
            bundle.run_id,
            1,
            "; ".join(failure.as_line() for failure in failures),
            failures,
        )
    signals = _merge_established(bundle, _signals_from(draft, bundle))
    level = level_for(score_of(signal.kind for signal in signals))
    return Verdict(
        run_id=bundle.run_id,
        level=level,
        headline=draft.headline.strip(),
        signals=signals,
        recommended_action=recommended_action(level),
        decided_at=decided_at or utc_now().isoformat(),
    )


def _signals_from(draft: DraftVerdict, bundle: EvidenceBundle) -> list[RiskSignal]:
    """One signal per kind. A repeated kind is a repeated argument, not more risk."""
    index = bundle.index()
    picked = _first_of_each_kind(draft)
    signals: list[RiskSignal] = []
    for kind in distinct_kinds(draft.kinds):
        drafted = picked[kind]
        claim = Claim(
            statement=drafted.claim.statement.strip(),
            sources=resolve_sources(drafted.claim.citations, index),
            confidence=drafted.claim.confidence,
        )
        signals.append(RiskSignal(kind=kind, weight=weight_for(kind), claim=claim))
    return signals


def _first_of_each_kind(draft: DraftVerdict) -> dict[SignalKind, DraftSignal]:
    picked: dict[SignalKind, DraftSignal] = {}
    for signal in draft.signals:
        picked.setdefault(signal.kind, signal)
    return picked
