"""The SerpApi budget, the tightest quota a soak can touch.

Identity costs three searches per counterparty, and the corpus draws its twenty
invoices from three suppliers on purpose, so one pass costs nine credits of a
monthly two hundred and fifty rather than sixty. Repetition inside a pass is
served from a memo held here rather than from the provider; repetition across
passes is left to the provider, because whether a later pass still resolves the
same identity is one of the things the soak is measuring.

The cap is carried rather than assumed. When it is reached the verification is
not attempted and says so in an error, because an identity check that never ran
must never be readable as one that came back clean.
"""

import asyncio

from autocurricula.schemas.common import utc_now

from countersign.agents.counterparty_model import CounterpartyModelClient
from countersign.agents.counterparty_verifier import (
    AssessmentStatus,
    CounterpartyAssessment,
    verify_counterparty,
)

SEARCHES_PER_VERIFICATION = 3

EXHAUSTED = (
    "soak budget: the SerpApi cap of {cap} search(es) is reached, so identity was not "
    "attempted for this run; this is a withheld check, not a clean one"
)


class IdentityBudget:
    """One live verification per counterparty per pass, under a hard ceiling."""

    def __init__(self, cap: int) -> None:
        if cap < 0:
            raise ValueError("the SerpApi cap cannot be negative")
        self.cap = cap
        self.spent = 0
        self.live_verifications = 0
        self.memo_hits = 0
        self._memo: dict[tuple[str, str], CounterpartyAssessment] = {}
        self._lock = asyncio.Lock()

    def start_pass(self) -> None:
        """Forget the pass's memo so the next pass verifies against the live web."""
        self._memo.clear()

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.spent)

    async def verify(
        self, legal_name: str, address: str, model: CounterpartyModelClient | None = None
    ) -> tuple[CounterpartyAssessment, int]:
        """The identity port, with the assessment and what it actually cost."""
        key = (legal_name.strip().lower(), address.strip().lower())
        async with self._lock:
            cached = self._memo.get(key)
            if cached is not None:
                self.memo_hits += 1
                return cached, 0
            if self.remaining < SEARCHES_PER_VERIFICATION:
                return _withheld(legal_name, address, self.cap), 0
            assessment = await verify_counterparty(legal_name, address, model=model)
            spent = assessment.searches_spent or SEARCHES_PER_VERIFICATION
            self.spent += spent
            self.live_verifications += 1
            self._memo[key] = assessment
            return assessment, spent


def _withheld(legal_name: str, address: str, cap: int) -> CounterpartyAssessment:
    return CounterpartyAssessment(
        legal_name=legal_name,
        address=address,
        status=AssessmentStatus.FAILED,
        assessed_at=utc_now().isoformat(),
        errors=[EXHAUSTED.format(cap=cap)],
    )


__all__ = ["EXHAUSTED", "SEARCHES_PER_VERIFICATION", "IdentityBudget"]
