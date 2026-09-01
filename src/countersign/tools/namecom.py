"""name.com tools for COUNTERSIGN. Capabilities: domain.query and domain.register.

Which registry answers is a product decision, not a setting, so it travels as an
argument on every function instead of a process-wide flag:

- Availability is asked of PRODUCTION. The signal a lookalike sweep is after is
  whether a confusable name is already owned in the real world, and the sandbox
  keeps its own registry where almost everything is free.
- The defensive registration is placed in SANDBOX. A demo that buys real domains
  spends real money, so production is refused on this path and the refusal is
  returned as a failure rather than made unrepresentable.
"""

from typing import Any, Final

from autocurricula.tools.base import ToolResult, as_function_tool

from countersign.tools import namecom_client as client
from countersign.tools.namecom_availability import (
    CHECK_AVAILABILITY_PATH,
    MAX_DOMAINS_PER_CALL,
    namecom_check_availability,
)
from countersign.tools.namecom_client import NamecomEnvironment, NamecomError
from countersign.tools.namecom_models import record_from

__all__ = [
    "CHECK_AVAILABILITY_PATH",
    "MAX_DOMAINS_PER_CALL",
    "build_namecom_tools",
    "check_availability_tool",
    "list_records_tool",
    "namecom_account_balance",
    "namecom_check_availability",
    "namecom_hello",
    "namecom_list_records",
    "namecom_register_domain",
    "register_domain_tool",
]

REGISTER_PATH: Final[str] = "/domains"
HELLO_PATH: Final[str] = "/hello"
BALANCE_PATH: Final[str] = "/accountinfo/balance"


async def namecom_list_records(domain_name: str, environment: str = "production") -> ToolResult:
    """List the DNS records of a domain the account owns. Does not mutate.

    The environment must match where the domain lives: a name registered
    defensively through this module is in the sandbox, not in production.
    """
    name = domain_name.strip().lower().rstrip(".")
    if not name or "." not in name:
        return ToolResult.failure(f"{domain_name!r} is not a domain name")
    try:
        target = client.resolve_environment(environment)
    except NamecomError as error:
        return ToolResult.failure(str(error))
    document, error = await client.attempt(target, "GET", f"/domains/{name}/records")
    if document is None:
        return ToolResult.failure(error or "name.com returned no body")
    raw_records = document.get("records")
    parsed = (record_from(raw) for raw in raw_records or [])
    records = [entry for entry in parsed if entry is not None]
    return ToolResult.success(
        {
            "environment": target.value,
            "domain_name": name,
            "records": [record.model_dump(mode="json") for record in records],
            "txt_answers": [record.answer for record in records if record.type == "TXT"],
        }
    )


async def namecom_register_domain(
    domain_name: str, purchase_price: float, environment: str = "sandbox"
) -> ToolResult:
    """Register a lookalike domain defensively. MUTATES external state.

    Sandbox only. Production is refused here because that path buys a real
    domain with real money and no agent in this fleet is trusted with a
    purchase; the refusal is returned so the attempt stays on the record.

    Args:
        domain_name: the name to take, as checked against production.
        purchase_price: the price the availability check quoted, in USD.
        environment: must be 'sandbox'.
    """
    name = domain_name.strip().lower().rstrip(".")
    if not name or "." not in name:
        return ToolResult.failure(f"{domain_name!r} is not a domain name")
    if not purchase_price > 0:
        return ToolResult.failure(
            "purchase_price must be the positive price quoted by the availability check"
        )
    try:
        target = client.resolve_environment(environment)
    except NamecomError as error:
        return ToolResult.failure(str(error))
    if target is not NamecomEnvironment.SANDBOX:
        return ToolResult.failure(
            f"refusing to register {name} against {target.value}: a defensive registration "
            "runs in the name.com sandbox, and the production path spends real money on a "
            "real domain, which is a purchase no agent in this fleet may make"
        )
    document, error = await client.attempt(
        target,
        "POST",
        REGISTER_PATH,
        {"domain": {"domainName": name}, "purchasePrice": purchase_price},
    )
    if document is None:
        return ToolResult.failure(error or "name.com returned no body")
    return ToolResult.success(
        {
            "environment": target.value,
            "domain_name": name,
            "domain": document.get("domain"),
            "order": document.get("order"),
            "total_paid": document.get("totalPaid"),
        }
    )


async def namecom_hello(environment: str = "production") -> ToolResult:
    """Confirm the credentials of one environment. Diagnostic, does not mutate."""
    return await _diagnostic(environment, HELLO_PATH)


async def namecom_account_balance(environment: str = "production") -> ToolResult:
    """Read the account balance of one environment. Diagnostic, does not mutate."""
    return await _diagnostic(environment, BALANCE_PATH)


async def _diagnostic(environment: str, path: str) -> ToolResult:
    try:
        target = client.resolve_environment(environment)
    except NamecomError as error:
        return ToolResult.failure(str(error))
    document, error = await client.attempt(target, "GET", path)
    if document is None:
        return ToolResult.failure(error or "name.com returned no body")
    return ToolResult.success({"environment": target.value, "path": path, "account": document})


check_availability_tool = as_function_tool(namecom_check_availability)
list_records_tool = as_function_tool(namecom_list_records)
register_domain_tool = as_function_tool(namecom_register_domain)


def build_namecom_tools() -> list[Any]:
    """The read-only pair. Registration is left out on purpose: domain.register is
    approval gated, so it is handed to a runner deliberately, never by default."""
    return [check_availability_tool, list_records_tool]
