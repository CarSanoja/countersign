"""Masking account identifiers before they reach a model.

The mapper's job is to say which span holds which field. It needs the shape of
a line, never the digits: "[p0l34] IBAN: LT## #### ..." is as mappable as the
real thing. So the model never receives an account number, and the real value is
read back from the span store afterwards.

This is the redaction the pipeline actually depends on. Nutrient's redaction API
removes content from the PDF itself, which would make the redacted fields
unextractable — the two are for different jobs and the order matters.
"""

import re

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[ ]?(?:[A-Za-z0-9]{2,6}[ ]?){2,7}\b")
_LONG_DIGITS = re.compile(r"\b\d[\d ]{7,}\d\b")
_SWIFT = re.compile(r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")
_EMAIL_USER = re.compile(r"\b([A-Za-z0-9._%+-]+)@")
_TAX_ID = re.compile(r"\b(VAT|Tax\s*ID|TIN|EIN|NIF|CIF)[:\s-]*([A-Z]{0,2}[-]?[A-Z0-9]{6,})", re.I)


def mask_pii(text: str) -> str:
    """Replace account identifiers with same-shaped placeholders.

    Digits become #, so a length and a grouping survive and a value does not.
    The local part of an email is masked while the domain is kept, because the
    domain is the signal and the mailbox is not.
    """
    masked = _IBAN.sub(lambda m: re.sub(r"[A-Za-z0-9]", "#", m.group(0)), text)
    masked = _LONG_DIGITS.sub(lambda m: re.sub(r"\d", "#", m.group(0)), masked)
    masked = _SWIFT.sub(lambda m: "#" * len(m.group(0)), masked)
    masked = _TAX_ID.sub(
        lambda m: f"{m.group(1)} " + re.sub(r"[A-Za-z0-9]", "#", m.group(2)), masked
    )
    return _EMAIL_USER.sub(lambda m: "#" * len(m.group(1)) + "@", masked)


def carries_pii(text: str) -> bool:
    return mask_pii(text) != text


def iban_in(text: str) -> str | None:
    """The IBAN a span carries, read by rule so no model ever handles one."""
    found = _IBAN.search(text)
    return re.sub(r"\s+", " ", found.group(0)).strip() if found else None
