"""The named fields, and the rule that tells an anchored value from a plausible one.

A model that may only point at spans can still point at the wrong one, so every value
it returns is checked back against the text of the span it cited. A value the cited
span does not carry is dropped, never repaired: a repaired value is a guess wearing a
citation.
"""

import re
from enum import StrEnum
from typing import Final


class InvoiceField(StrEnum):
    LEGAL_NAME = "legal_name"
    ADDRESS = "address"
    IBAN = "iban"
    ACCOUNT_NUMBER = "account_number"
    ROUTING_NUMBER = "routing_number"
    TOTAL_AMOUNT = "total_amount"
    INVOICE_NUMBER = "invoice_number"
    SENDER_DOMAIN = "sender_domain"


FIELD_GUIDANCE: Final[dict[InvoiceField, str]] = {
    InvoiceField.LEGAL_NAME: "registered name of the party issuing the document",
    InvoiceField.ADDRESS: "postal address of the issuing party",
    InvoiceField.IBAN: "international bank account number, when the document prints one",
    InvoiceField.ACCOUNT_NUMBER: "domestic account number, when there is no IBAN",
    InvoiceField.ROUTING_NUMBER: "routing, sort, ABA or SWIFT/BIC code paired with the account",
    InvoiceField.TOTAL_AMOUNT: "total amount payable, with the currency as printed",
    InvoiceField.INVOICE_NUMBER: "invoice or contract reference number",
    InvoiceField.SENDER_DOMAIN: "internet domain of the issuer, from its email address or website",
}

BANK_FIELDS: Final[frozenset[InvoiceField]] = frozenset(
    {InvoiceField.IBAN, InvoiceField.ACCOUNT_NUMBER, InvoiceField.ROUTING_NUMBER}
)

MIN_ANCHOR_CHARS: Final[int] = 2

_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")
_DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}", re.IGNORECASE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def normalise(value: str) -> str:
    """Drop everything typography can move: case, spacing, punctuation.

    'ES91 2100 0418 4502 0005 1332' and 'ES9121000418450200051332' are the same
    account, and '1.234,56' and '1234.56' are the same total.
    """
    return _ALPHANUMERIC.sub("", value.casefold())


def value_is_anchored(value: str, span_text: str) -> bool:
    """True only if the cited span literally contains the value."""
    needle = normalise(value)
    if len(needle) < MIN_ANCHOR_CHARS:
        return False
    return needle in normalise(span_text)


def normalise_domain(value: str) -> str:
    """Reduce whatever the model wrote to a bare host name."""
    text = _SCHEME.sub("", value.strip().casefold())
    text = text.rsplit("@", 1)[-1]
    for separator in ("/", "?", "#", ":", ","):
        text = text.split(separator, 1)[0]
    text = text.strip().strip("<>()[]").rstrip(".")
    return text[4:] if text.startswith("www.") else text


def domains_in(text: str) -> set[str]:
    """Every host name the span prints, with and without its www prefix."""
    found: set[str] = set()
    for match in _DOMAIN.finditer(text):
        name = match.group(0).casefold().rstrip(".")
        found.add(name)
        if name.startswith("www."):
            found.add(name[4:])
    return found


def anchored_domain(value: str, span_text: str) -> str | None:
    """The sender domain, only when the cited span carries it as a domain.

    Substring anchoring is too weak here: 'acme.com' is a substring of the text of
    'acme.company-invoices.net', and that is exactly the confusion being defended
    against, so the value has to match a host name the span actually prints.
    """
    candidate = normalise_domain(value)
    if not candidate or not _DOMAIN.fullmatch(candidate):
        return None
    return candidate if candidate in domains_in(span_text) else None


def anchor_value(field: InvoiceField, value: str, span_text: str) -> str | None:
    """The value as the cited span supports it, or nothing at all.

    The sender domain is anchored as a host name rather than as a substring, because
    'acmecorp.com' sits inside 'acmecorp.com-invoices.net' and that confusion is the
    whole attack this pipeline exists to catch.
    """
    if field is InvoiceField.SENDER_DOMAIN:
        return anchored_domain(value, span_text)
    cleaned = value.strip()
    return cleaned if value_is_anchored(cleaned, span_text) else None
