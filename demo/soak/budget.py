"""What a soak of this size will cost, worked out before anything is spent.

Both figures that matter are asked of the provider rather than assumed. Nutrient
prices the exact /build request through /analyze_build, which is free and takes
no document, and SerpApi reports the searches left on the plan through
/account.json, which is also free. So the estimate printed before a soak starts
is the provider's own arithmetic, and a soak that would not fit inside the
remaining SerpApi quota is refused rather than started and regretted.
"""

from corpus import COUNTERPARTIES, SoakCase

from countersign.agents.document_extractor_nutrient import price_request
from countersign.orchestration.domain_sweep import SWEEP_LIMIT
from countersign.tools.serpapi_client import ACCOUNT_PATH, serpapi_get
from identity import SEARCHES_PER_VERIFICATION

VERTEX_CALLS_PER_RUN = 3
"""One mapping, one counterparty judgement, one verdict draft, before any retry."""

NUTRIENT_CREDITS_PER_RUN = 5.0
"""The fallback when /analyze_build cannot be reached; the live quote replaces it."""


async def measured_prices() -> dict[str, object]:
    """The two prices the providers will quote for free, and nothing else."""
    quote = await price_request()
    analysis = quote.payload.get("analysis") if quote.ok else {}
    credits = analysis.get("cost") if isinstance(analysis, dict) else None
    account = await serpapi_get(ACCOUNT_PATH, {})
    document = account.payload.get("document") if account.ok else {}
    left = document.get("total_searches_left") if isinstance(document, dict) else None
    return {
        "nutrient_credits_per_run": float(credits) if credits else NUTRIENT_CREDITS_PER_RUN,
        "nutrient_quote_live": bool(credits),
        "serpapi_searches_left": int(left) if isinstance(left, int) else None,
        "serpapi_quote_error": None if account.ok else account.error,
    }


def projection(
    cases: tuple[SoakCase, ...], passes: int, prices: dict[str, object]
) -> dict[str, object]:
    """What the soak will ask of each provider if nothing is served from a cache."""
    runs = len(cases) * passes
    counterparties = len({case.counterparty.key for case in cases})
    per_run = float(prices["nutrient_credits_per_run"])
    return {
        "runs": runs,
        "passes": passes,
        "cases_per_pass": len(cases),
        "distinct_counterparties": counterparties,
        "nutrient_credits": round(runs * per_run, 1),
        "serpapi_searches_max": counterparties * SEARCHES_PER_VERIFICATION * passes,
        "namecom_lookups": runs * (SWEEP_LIMIT + 1),
        "vertex_calls_min": runs * VERTEX_CALLS_PER_RUN,
        "foxit_envelopes": 0,
        "render_credits": 0,
    }


def blockers(plan: dict[str, object], prices: dict[str, object], cap: int) -> list[str]:
    """Why this soak must not start, if it must not."""
    reasons: list[str] = []
    searches = int(plan["serpapi_searches_max"])
    if searches > cap:
        reasons.append(
            f"the plan would spend up to {searches} SerpApi searches and the cap is {cap}; "
            "raise --serpapi-cap deliberately or run fewer passes"
        )
    left = prices.get("serpapi_searches_left")
    if isinstance(left, int) and searches > left:
        reasons.append(
            f"the plan would spend up to {searches} SerpApi searches and only {left} "
            "remain on the plan this month"
        )
    return reasons


def lines(plan: dict[str, object], prices: dict[str, object], cap: int) -> list[str]:
    """The estimate as it is printed, before a single provider is touched."""
    left = prices.get("serpapi_searches_left")
    quoted = "live quote" if prices["nutrient_quote_live"] else "fallback, /analyze_build failed"
    return [
        f"passes                 {plan['passes']}  ({plan['cases_per_pass']} invoices each, "
        f"{plan['runs']} runs)",
        f"nutrient credits       ~{plan['nutrient_credits']} "
        f"({prices['nutrient_credits_per_run']} per run, {quoted})",
        f"serpapi searches       <= {plan['serpapi_searches_max']} "
        f"({plan['distinct_counterparties']} counterparties x {SEARCHES_PER_VERIFICATION} x "
        f"{plan['passes']} passes), cap {cap}, "
        f"{left if left is not None else 'unknown'} left on the plan",
        f"name.com lookups       ~{plan['namecom_lookups']} (production reads, no charge)",
        f"vertex calls           >= {plan['vertex_calls_min']} (retries add to this)",
        "foxit esign envelopes  0 (no signing party is configured; the seam is closed)",
        "render credits         0 (no template is configured; the seam is closed)",
    ]


def counterparty_lines() -> list[str]:
    """Which suppliers the searches will be spent on, so the queries are foreseeable."""
    return [
        f"{party.legal_name} ({party.official_domain}) — {party.address}"
        for party in COUNTERPARTIES
    ]


__all__ = [
    "NUTRIENT_CREDITS_PER_RUN",
    "VERTEX_CALLS_PER_RUN",
    "blockers",
    "counterparty_lines",
    "lines",
    "measured_prices",
    "projection",
]
