"""The vendor file as living state: which account a supplier is paid at, and since when.

A phrase in a PDF is not evidence that the bank details changed; it is evidence
that the PDF says so. An attacker simply omits it and the heaviest signal in the
system never fires, while an honest supplier who really did move bank is marked
for having said so out loud. What settles the question is a comparison against a
row a person can open: either this invoice pays the account this vendor has been
paid at since a recorded date, or it does not.

The row holds a fingerprint and never the account. A vendors table full of IBANs
is a payout map, and the last thing an anti-redirection control should become is
a better target than the invoices it screens.
"""

import hashlib
import hmac
import os
from typing import Final

from countersign.agents.document_extractor import ExtractedInvoice
from countersign.agents.document_extractor_fields import normalise
from countersign.agents.risk_weights import SIGNAL_WEIGHTS
from countersign.orchestration.baseline_store import (
    FINGERPRINT_FIELD,
    SINCE_FIELD,
    BaselineUnavailable,
    VendorBaseline,
    known_bank,
)
from countersign.schemas.evidence import Claim, Provider, SourceRef
from countersign.schemas.verdict import RiskSignal, SignalKind
from countersign.tools import xano

SALT_ENV: Final[str] = "COUNTERSIGN_BASELINE_SALT"
FINGERPRINT_CHARS: Final[int] = 32
PRINTED_CHARS: Final[int] = 12

UNKNOWN_BASELINE_WEIGHT: Final[float] = 0.15
"""Not knowing is not the same as knowing something is wrong, so it must not carry
the weight of a mismatch. `risk_weights.score_of` still totals by kind, so for now
this number rides on the signal and on the audit row rather than on the score."""

MISMATCH: Final[str] = (
    "{name} has been on file with the same bank account since {since}, and the account "
    "this invoice directs payment to is not it: the document's account fingerprints as "
    "{seen}, the vendor row holds {known}. The document did not have to announce a "
    "change for this to be one."
)
NO_FILE_IS_NOT_A_FINDING: Final[str] = (
    "A supplier with no file yet raises nothing at all. Measured over the soak "
    "corpus, scoring the absence even weakly took the false positive rate from "
    "49% to 81%, because every first invoice from every supplier carries it. "
    "Not knowing is not evidence of a redirection, and a control that fires on "
    "every new supplier is a control that gets switched off. The absence is "
    "still visible in the vendor row; it simply does not score."
)


def bank_fingerprint(iban: str) -> str:
    """A comparable stand-in for an account, never the account itself.

    Only equality is ever asked of this value, so the account never has to be kept
    to answer it. A bare digest would not be enough: an IBAN prints its country and
    bank code in the clear and the space left over is small enough to enumerate, so
    a leaked table of plain hashes is a leaked table of accounts. Keying the digest
    with a per-instance secret makes that dump useless on its own.
    """
    account = normalise(iban)
    if not account:
        raise ValueError("an account with no alphanumeric content has no fingerprint")
    digest = hmac.new(_salt().encode(), account.encode(), hashlib.sha256)
    return digest.hexdigest()[:FINGERPRINT_CHARS]


def baseline_columns(iban: str, at: str) -> dict[str, str]:
    """The two vendor-row fields that make the next run a comparison.

    The first sighting is what turns this from a phrase match into state: the
    account is fingerprinted once and every later invoice is measured against it.
    """
    return {FINGERPRINT_FIELD: bank_fingerprint(iban), SINCE_FIELD: at}


def baseline_configured() -> bool:
    """Whether a comparison is possible on this instance at all.

    The salt counts as configuration rather than as optional hardening: without it
    no fingerprint exists, so there is nothing to compare and nothing to store.
    """
    names = (
        xano.TOKEN_ENV,
        xano.DOMAIN_ENV,
        xano.WORKSPACE_ENV,
        xano.VENDOR_TABLE_ENV,
        SALT_ENV,
    )
    return all(os.environ.get(name, "").strip() for name in names)


def bank_signal(
    invoice: ExtractedInvoice, baseline: VendorBaseline | None, at: str
) -> RiskSignal | None:
    """Measure the account this invoice pays against the one on file.

    Three answers, and telling them apart is the whole point. A file that
    disagrees is the strongest thing this pipeline can say, and it says it whether
    or not the document admits anything. A file that agrees is silence, even when
    the page announces a change in capitals: a supplier writing to say they have
    moved to the account they already had has redirected nothing. No file at all is
    neither of those, and the text says so instead of borrowing from either.
    """
    account = invoice.iban
    if account is None or not account.value.strip():
        return None
    try:
        seen = bank_fingerprint(account.value)
    except (ValueError, xano.MissingCredential):
        return None
    if baseline is None:
        return None
    if hmac.compare_digest(seen, baseline.fingerprint):
        return None
    statement = MISMATCH.format(
        name=baseline.legal_name,
        since=baseline.since,
        seen=_printed(seen),
        known=_printed(baseline.fingerprint),
    )
    sources = [_xano_source(baseline, at), account.source]
    return _signal(statement, SIGNAL_WEIGHTS[SignalKind.BANK_DETAILS_CHANGED], sources, 1.0)


def _signal(
    statement: str, weight: float, sources: list[SourceRef], confidence: float
) -> RiskSignal:
    return RiskSignal(
        kind=SignalKind.BANK_DETAILS_CHANGED,
        weight=weight,
        claim=Claim(statement=statement, sources=sources, confidence=confidence),
    )


def _xano_source(baseline: VendorBaseline, at: str) -> SourceRef:
    """The row itself, quoted, so a reader can open it and redo the comparison."""
    return SourceRef(
        provider=Provider.XANO,
        locator=baseline.locator,
        snippet=(
            f"{FINGERPRINT_FIELD} {baseline.fingerprint}, {SINCE_FIELD} {baseline.since}, "
            f"legal_name {baseline.legal_name}"
        ),
        retrieved_at=at,
    )


def _subject(invoice: ExtractedInvoice) -> str:
    name = invoice.legal_name.value.strip() if invoice.legal_name is not None else ""
    return name or "this supplier"


def _printed(fingerprint: str) -> str:
    """Enough of the digest to compare two by eye, and no more than that."""
    return f"{fingerprint[:PRINTED_CHARS]}..."


def _salt() -> str:
    return _required(SALT_ENV)


def _required(variable: str) -> str:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise xano.MissingCredential(variable)
    return value


__all__ = [
    "SALT_ENV",
    "UNKNOWN_BASELINE_WEIGHT",
    "BaselineUnavailable",
    "VendorBaseline",
    "bank_fingerprint",
    "bank_signal",
    "baseline_columns",
    "baseline_configured",
    "known_bank",
]
