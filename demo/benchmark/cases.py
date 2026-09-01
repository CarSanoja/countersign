"""The labelled set COUNTERSIGN is measured against.

Every sender domain here is real: its registration status was checked against
the production registry, so the expected outcome rests on fact rather than on a
label we invented. name.com is the impersonated party in the adverse cases and
never the perpetrator; the fraudulent sender is a fictional third party.
"""

from dataclasses import dataclass

OFFICIAL = "name.com"


@dataclass(frozen=True)
class Case:
    case_id: str
    sender_domain: str
    bank_changed: bool
    expect_level: str
    expect_signals: frozenset[str]
    why: str


CASES: tuple[Case, ...] = (
    Case(
        "clean",
        OFFICIAL,
        False,
        "clear",
        frozenset({"confusable_already_registered"}),
        "the real vendor domain, no bank change: only the standing surface signal",
    ),
    Case(
        "bank-change-only",
        OFFICIAL,
        True,
        "review",
        frozenset({"confusable_already_registered", "bank_details_changed"}),
        "right domain but the account changed: worth a human, not an alarm",
    ),
    Case(
        "homoglyph",
        "narne.com",
        True,
        "high",
        frozenset({"sender_domain_not_official", "confusable_already_registered"}),
        "rn/m substitution, registered by someone: the classic BEC lure",
    ),
    Case(
        "tld-swap",
        "name.net",
        True,
        "high",
        frozenset({"sender_domain_not_official", "confusable_already_registered"}),
        "a different TLD of the same label, already taken",
    ),
    Case(
        "hyphen",
        "na-me.com",
        True,
        "high",
        frozenset({"sender_domain_not_official", "confusable_already_registered"}),
        "hyphen insertion, already taken",
    ),
    Case(
        "unregistered-sender",
        "nane.com",
        True,
        "high",
        frozenset(
            {
                "sender_domain_not_official",
                "sender_domain_unregistered",
                "confusable_already_registered",
            }
        ),
        "an invoice from a domain nobody owns is worse, not better",
    ),
)
