"""Typed views over the two name.com bodies COUNTERSIGN reads.

The availability body is parsed defensively on one specific point: the API omits
``purchasable`` instead of sending false, so a missing key and an explicit false
mean the same thing, and both mean the name is already owned by someone. Reading
the absence as unknown would silently turn a registered lookalike into a clean
result, which is the single failure this whole check exists to prevent.
"""

from typing import Any

from autocurricula.schemas.common import StrictBaseModel


class AvailabilityResult(StrictBaseModel):
    """One entry of ``POST /domains:checkAvailability``."""

    domain_name: str
    purchasable: bool
    premium: bool
    purchase_price: float | None = None

    @property
    def registered(self) -> bool:
        """True when the name is owned by someone, which is the fraud signal."""
        return not self.purchasable


class DnsRecord(StrictBaseModel):
    """One entry of ``GET /domains/{domain}/records``."""

    record_id: int | None = None
    host: str = ""
    fqdn: str = ""
    type: str = ""
    answer: str = ""
    ttl: int | None = None


def _as_price(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def availability_from(raw: Any) -> AvailabilityResult | None:
    """Read one availability entry, or None when it carries no domain name."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("domainName") or "").strip().lower()
    if not name:
        return None
    return AvailabilityResult(
        domain_name=name,
        purchasable=raw.get("purchasable") is True,
        premium=raw.get("premium") is True,
        purchase_price=_as_price(raw.get("purchasePrice")),
    )


def record_from(raw: Any) -> DnsRecord | None:
    """Read one DNS record entry, or None when the shape is not an object."""
    if not isinstance(raw, dict):
        return None
    record_id = raw.get("id")
    ttl = raw.get("ttl")
    return DnsRecord(
        record_id=record_id if isinstance(record_id, int) else None,
        host=str(raw.get("host") or ""),
        fqdn=str(raw.get("fqdn") or ""),
        type=str(raw.get("type") or "").upper(),
        answer=str(raw.get("answer") or ""),
        ttl=ttl if isinstance(ttl, int) else None,
    )


def normalise_domains(domain_names: list[str]) -> list[str]:
    """Lowercase, trim and de-duplicate while preserving the caller's order."""
    seen: dict[str, None] = {}
    for raw in domain_names:
        name = str(raw).strip().lower().rstrip(".")
        if name and "." in name:
            seen.setdefault(name, None)
    return list(seen)
