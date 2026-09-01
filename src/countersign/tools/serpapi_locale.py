"""Which Google market a counterparty check is run in.

Identity disambiguation is the hardest judgement in this pipeline and it is made
entirely on what the SERP returns, so the market that SERP came from is part of
the judgement. Asking google.es in Spanish about a company in Denver is no
cosmetic mismatch: the official site ranks below Spanish-market noise, and the
adverse coverage of a US company is written in English by outlets a Spanish
query barely reaches. So the market is derived from the invoiced address.

The map is short on purpose and covers only what can be named without guessing:
the United States by state, the United Kingdom, Spain, Germany, France and the
Netherlands. Anything else falls back to google.com / gl=us / hl=en, Google's
own default and the widest index, which is a fallback and not a claim that the
counterparty is American. Every result carries what was matched and how firmly,
so a reader can discount an identity call made in an inferred market. Google's
own country code for the United Kingdom is uk, not the ISO gb, and a city is
weaker evidence than a country: a state beside a ZIP is resolved first, so
"Paris, TX 75460" is never searched in France.
"""

import re
from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel


class LocaleConfidence(StrEnum):
    """How firmly the market was established, so a caller can discount it."""

    COUNTRY_NAMED = "country_named"
    REGION_INFERRED = "region_inferred"
    UNRECOGNISED = "unrecognised"


class SearchLocale(StrictBaseModel):
    """The three SerpApi localisation parameters, and what they rest on."""

    google_domain: str
    country_code: str
    language: str
    market: str
    matched: str = ""
    confidence: LocaleConfidence

    @property
    def describe(self) -> str:
        """One line for a trace: which market was searched, and on what evidence."""
        seen = f", from {self.matched!r}" if self.matched else ""
        return (
            f"{self.market} (google_domain={self.google_domain}, gl={self.country_code}, "
            f"hl={self.language}; {self.confidence.value}{seen})"
        )


_US, _GB, _ES = "United States", "United Kingdom", "Spain"
_DE, _FR, _NL = "Germany", "France", "Netherlands"

_MARKETS: dict[str, tuple[str, str, str]] = {
    _US: ("google.com", "us", "en"),
    _GB: ("google.co.uk", "uk", "en"),
    _ES: ("google.es", "es", "es"),
    _DE: ("google.de", "de", "de"),
    _FR: ("google.fr", "fr", "fr"),
    _NL: ("google.nl", "nl", "nl"),
}

_COUNTRIES: dict[str, str] = {
    "united states": _US, "united states of america": _US, "usa": _US, "u s a": _US,
    "estados unidos": _US, "ee uu": _US, "united kingdom": _GB, "uk": _GB, "england": _GB,
    "great britain": _GB, "scotland": _GB, "wales": _GB, "northern ireland": _GB,
    "reino unido": _GB, "spain": _ES, "espana": _ES, "españa": _ES, "germany": _DE,
    "deutschland": _DE, "alemania": _DE, "france": _FR, "francia": _FR, "netherlands": _NL,
    "the netherlands": _NL, "nederland": _NL, "holland": _NL, "paises bajos": _NL,
}

_TRAILING_CODES: dict[str, str] = {
    "us": _US, "uk": _GB, "gb": _GB, "es": _ES, "de": _DE, "fr": _FR, "nl": _NL,
}
"""Two letters are a country only when they close the address: in the middle of
one they are as likely to be a state, a street type or an ordinary word."""

_CITIES: dict[str, str] = {
    "madrid": _ES, "barcelona": _ES, "valencia": _ES, "sevilla": _ES, "bilbao": _ES,
    "zaragoza": _ES, "malaga": _ES, "málaga": _ES, "london": _GB, "manchester": _GB,
    "glasgow": _GB, "edinburgh": _GB, "liverpool": _GB, "leeds": _GB, "berlin": _DE,
    "munich": _DE, "münchen": _DE, "hamburg": _DE, "frankfurt": _DE, "köln": _DE,
    "stuttgart": _DE, "düsseldorf": _DE, "paris": _FR, "lyon": _FR, "marseille": _FR,
    "toulouse": _FR, "bordeaux": _FR, "nantes": _FR, "amsterdam": _NL, "rotterdam": _NL,
    "den haag": _NL, "the hague": _NL, "utrecht": _NL, "eindhoven": _NL,
}
"""Domestic invoices routinely omit the country, and searching a Madrid vendor
from google.com is the same error pointed the other way. Only cities one of
these markets dominates are listed, and a city is the last thing tried."""

_US_STATES: dict[str, str] = dict(
    pair.replace("_", " ").split(":")
    for pair in (
        "AL:Alabama AK:Alaska AZ:Arizona AR:Arkansas CA:California CO:Colorado IA:Iowa "
        "CT:Connecticut DE:Delaware DC:District_of_Columbia FL:Florida GA:Georgia HI:Hawaii "
        "ID:Idaho IL:Illinois IN:Indiana KS:Kansas KY:Kentucky LA:Louisiana ME:Maine OH:Ohio "
        "MD:Maryland MA:Massachusetts MI:Michigan MN:Minnesota MS:Mississippi MO:Missouri "
        "MT:Montana NE:Nebraska NV:Nevada NY:New_York NJ:New_Jersey NM:New_Mexico UT:Utah "
        "NH:New_Hampshire NC:North_Carolina ND:North_Dakota OK:Oklahoma OR:Oregon VT:Vermont "
        "PA:Pennsylvania RI:Rhode_Island SC:South_Carolina SD:South_Dakota TN:Tennessee "
        "TX:Texas VA:Virginia WA:Washington WI:Wisconsin WV:West_Virginia WY:Wyoming"
    ).split()
)

_AMBIGUOUS_STATE_NAMES = frozenset({"georgia", "washington", "delaware"})
"""Georgia is also a country, Washington names streets everywhere, and Delaware
sits inside company names. Spelled out, these three count only beside a ZIP."""

_WORD_BREAK = re.compile(r"[^\w]+")
_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_STATE_AND_ZIP = re.compile(r"\b([A-Z]{2})[ ,]+\d{5}(?:-\d{4})?\b")
_UK_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b")
_NL_POSTCODE = re.compile(r"\b\d{4} ?[A-Z]{2}\b")

FALLBACK_LOCALE = SearchLocale(
    google_domain="google.com",
    country_code="us",
    language="en",
    market="unrecognised",
    confidence=LocaleConfidence.UNRECOGNISED,
)
"""The documented default, used when the address names no market this map
covers. It says so in its confidence, so it is never read as an assertion."""


def locale_for_address(address: str) -> SearchLocale:
    """Derive the Google market to search from the address on the invoice.

    Never raises and never returns nothing: an address whose market cannot be
    named yields a weaker search, not a failed stage, and confidence says which.
    """
    text = address.strip()
    if not text:
        return FALLBACK_LOCALE
    words = f" {_WORD_BREAK.sub(' ', text.lower()).strip()} "
    named = _first_hint(words, _COUNTRIES) or _trailing_code(words)
    if named is not None:
        return _locale(*named, LocaleConfidence.COUNTRY_NAMED)
    inferred = _postcode_market(text, words) or _first_hint(words, _CITIES)
    if inferred is not None:
        return _locale(*inferred, LocaleConfidence.REGION_INFERRED)
    return FALLBACK_LOCALE


def _first_hint(words: str, hints: dict[str, str]) -> tuple[str, str] | None:
    """Longest hint first, so "northern ireland" is never read as "ireland"."""
    for hint in sorted(hints, key=len, reverse=True):
        if f" {hint} " in words:
            return hints[hint], hint
    return None


def _trailing_code(words: str) -> tuple[str, str] | None:
    tokens = words.split()
    if tokens and tokens[-1] in _TRAILING_CODES:
        return _TRAILING_CODES[tokens[-1]], tokens[-1]
    return None


def _postcode_market(text: str, words: str) -> tuple[str, str] | None:
    """Postal shapes belonging to one market, read on the original casing."""
    state = _STATE_AND_ZIP.search(text)
    if state is not None and state.group(1) in _US_STATES:
        return _US, state.group(0)
    spelled = _us_state_by_name(text, words)
    if spelled is not None:
        return _US, spelled
    for pattern, market in ((_UK_POSTCODE, _GB), (_NL_POSTCODE, _NL)):
        found = pattern.search(text)
        if found is not None:
            return market, found.group(0)
    return None


def _us_state_by_name(text: str, words: str) -> str | None:
    """A state spelled out, with the three names that are traps held back."""
    has_zip = _ZIP.search(text) is not None
    for name in sorted({value.lower() for value in _US_STATES.values()}, key=len, reverse=True):
        if f" {name} " in words and (has_zip or name not in _AMBIGUOUS_STATE_NAMES):
            return name
    return None


def _locale(market: str, matched: str, confidence: LocaleConfidence) -> SearchLocale:
    domain, country_code, language = _MARKETS[market]
    return SearchLocale(
        google_domain=domain,
        country_code=country_code,
        language=language,
        market=market,
        matched=matched,
        confidence=confidence,
    )


__all__ = ["FALLBACK_LOCALE", "LocaleConfidence", "SearchLocale", "locale_for_address"]
