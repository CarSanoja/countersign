"""The lookalike sweep: which confusable names are already owned.

This is the only name.com call whose answer is evidence rather than plumbing, so
it defaults to PRODUCTION and says so in the payload. The sandbox registry knows
nothing about who owns a domain in the world, and a sweep pointed at it would
report every lookalike as free, which reads as safe when it means nothing at all.
"""

import asyncio
from typing import Final

from autocurricula.tools.base import ToolResult

from countersign.tools import namecom_client as client
from countersign.tools.namecom_client import NamecomEnvironment, NamecomError
from countersign.tools.namecom_models import (
    AvailabilityResult,
    availability_from,
    normalise_domains,
)

CHECK_AVAILABILITY_PATH: Final[str] = "/domains:checkAvailability"
MAX_DOMAINS_PER_CALL: Final[int] = 200


async def namecom_check_availability(
    domain_names: list[str], environment: str = "production"
) -> ToolResult:
    """Ask a registry which of these names are already owned. Does not mutate.

    An entry whose ``purchasable`` is false or absent is registered by someone,
    and for a confusable variant of a supplier domain that is the finding. Names
    go out in batches of fifty, paced under the twenty per second ceiling.

    Args:
        domain_names: the names to check, deduplicated and lowercased here.
        environment: 'production' for a real ownership answer, 'sandbox' only to
            inspect the test registry, where the answer carries no evidence.
    """
    names = normalise_domains(domain_names)
    if not names:
        return ToolResult.failure("no usable domain names given; each must contain a dot")
    if len(names) > MAX_DOMAINS_PER_CALL:
        return ToolResult.failure(
            f"{len(names)} names exceeds the {MAX_DOMAINS_PER_CALL} this tool checks in one "
            "call; narrow the sweep rather than spending the hourly request budget here"
        )
    try:
        target = client.resolve_environment(environment)
    except NamecomError as error:
        return ToolResult.failure(str(error))
    results, error = await _check_in_batches(target, names)
    if error is not None:
        return ToolResult.failure(error)
    answered = {result.domain_name for result in results}
    return ToolResult.success(
        {
            "environment": target.value,
            "requested": names,
            "results": [result.model_dump(mode="json") for result in results],
            "registered": [r.domain_name for r in results if r.registered],
            "available": [r.domain_name for r in results if not r.registered],
            "premium": [r.domain_name for r in results if r.premium],
            "unanswered": [name for name in names if name not in answered],
        }
    )


async def _check_in_batches(
    target: NamecomEnvironment, names: list[str]
) -> tuple[list[AvailabilityResult], str | None]:
    size = client.MAX_DOMAINS_PER_CHECK
    batches = [names[start : start + size] for start in range(0, len(names), size)]
    collected: list[AvailabilityResult] = []
    for index, batch in enumerate(batches):
        if index:
            await asyncio.sleep(client.SECONDS_BETWEEN_REQUESTS)
        document, error = await client.attempt(
            target, "POST", CHECK_AVAILABILITY_PATH, {"domainNames": batch}
        )
        if document is None:
            return collected, error
        raw_results = document.get("results")
        if not isinstance(raw_results, list):
            return collected, f"name.com {CHECK_AVAILABILITY_PATH} returned no results array"
        parsed = (availability_from(raw) for raw in raw_results)
        collected.extend(entry for entry in parsed if entry is not None)
    return collected, None
