"""The market a counterparty is searched in, asserted on the URL that would go out.

Not one of these tests spends a credit: every request is answered by
httpx.MockTransport, and what is checked is the query string SerpApi would have
received. The bug this covers was invisible in the response and only visible
here — three searches pinned to google.es for a company in Denver.
"""

import httpx
import pytest
from autocurricula.tools.base import ToolResult

from countersign.agents.counterparty_evidence import SerpApiSearches, gather_evidence
from countersign.agents.counterparty_verifier import AssessmentStatus, verify_counterparty
from countersign.tools import serpapi_client
from countersign.tools.serpapi_address import serpapi_verify_address
from countersign.tools.serpapi_locale import (
    FALLBACK_LOCALE,
    LocaleConfidence,
    SearchLocale,
    locale_for_address,
)
from countersign.tools.serpapi_search import serpapi_adverse_media, serpapi_find_official_site

DENVER = "1801 California St, Suite 900, Denver, CO 80202"
MADRID = "Calle Mayor 1, 28013 Madrid, España"


@pytest.fixture
def sent() -> list[httpx.Request]:
    return []


@pytest.fixture(autouse=True)
def mocked_serpapi(monkeypatch: pytest.MonkeyPatch, sent: list[httpx.Request]):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"search_metadata": {"id": "search-1"}})

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(serpapi_client.httpx, "AsyncClient", factory)


@pytest.mark.parametrize(
    ("address", "domain", "country", "language"),
    [
        (DENVER, "google.com", "us", "en"),
        ("500 Boylston St, Boston, Massachusetts 02116", "google.com", "us", "en"),
        (MADRID, "google.es", "es", "es"),
        ("Calle Mayor 1, Madrid", "google.es", "es", "es"),
        ("10 Downing Street, London SW1A 2AA", "google.co.uk", "uk", "en"),
        ("221B Baker Street, London, United Kingdom", "google.co.uk", "uk", "en"),
        ("Unter den Linden 1, 10117 Berlin, Deutschland", "google.de", "de", "de"),
        ("12 Rue de Rivoli, 75001 Paris", "google.fr", "fr", "fr"),
        ("Herengracht 100, 1015 BS Amsterdam", "google.nl", "nl", "nl"),
    ],
)
def test_the_market_is_read_off_the_invoiced_address(address, domain, country, language):
    locale = locale_for_address(address)

    assert (locale.google_domain, locale.country_code, locale.language) == (
        domain,
        country,
        language,
    )
    assert locale.confidence is not LocaleConfidence.UNRECOGNISED
    assert locale.matched


def test_an_unrecognised_address_falls_back_and_says_so():
    locale = locale_for_address("Rua Augusta 100, Lisboa")

    assert locale == FALLBACK_LOCALE
    assert locale.google_domain == "google.com"
    assert locale.confidence is LocaleConfidence.UNRECOGNISED
    assert locale_for_address("") == FALLBACK_LOCALE


def test_the_two_names_that_are_traps_are_not_read_as_a_us_state():
    """Georgia is a country before it is a state, and Paris is in Texas too."""
    georgia = locale_for_address("7 Rustaveli Avenue, Tbilisi, Georgia")
    texas = locale_for_address("100 Main St, Paris, TX 75460")

    assert georgia == FALLBACK_LOCALE
    assert (texas.google_domain, texas.country_code) == ("google.com", "us")
    assert texas.matched == "TX 75460"


def test_a_named_country_outranks_an_inferred_one():
    named = locale_for_address(MADRID)
    inferred = locale_for_address("Calle Mayor 1, Madrid")

    assert named.confidence is LocaleConfidence.COUNTRY_NAMED
    assert inferred.confidence is LocaleConfidence.REGION_INFERRED
    assert named.market == inferred.market == "Spain"


async def test_the_organic_search_sends_the_locale_it_was_given(sent):
    locale = locale_for_address(DENVER)

    result = await serpapi_find_official_site(
        "Denver Freight Partners",
        country_code=locale.country_code,
        language=locale.language,
        google_domain=locale.google_domain,
    )

    assert result.ok
    params = sent[0].url.params
    assert (params["gl"], params["hl"], params["google_domain"]) == ("us", "en", "google.com")


async def test_the_news_search_sends_the_locale_it_was_given(sent):
    locale = locale_for_address(DENVER)

    result = await serpapi_adverse_media(
        "Denver Freight Partners",
        country_code=locale.country_code,
        language=locale.language,
    )

    assert result.ok
    params = sent[0].url.params
    assert (params["engine"], params["gl"], params["hl"]) == ("google_news", "us", "en")


async def test_the_maps_search_sends_the_language_it_was_given(sent):
    result = await serpapi_verify_address(
        "Denver Freight Partners", DENVER, language=locale_for_address(DENVER).language
    )

    assert result.ok
    params = sent[0].url.params
    assert params["hl"] == "en"
    assert "google_domain" not in params


async def test_all_three_searches_of_a_us_vendor_leave_the_spanish_market(sent):
    """The whole point: no hop of a Denver check may be taken on google.es."""
    await gather_evidence(
        "Denver Freight Partners",
        DENVER,
        SerpApiSearches(),
        locale=locale_for_address(DENVER),
        when_window="2y",
    )

    assert len(sent) == 3
    for request in sent:
        params = request.url.params
        assert params["hl"] == "en"
        assert params.get("gl", "us") == "us"
        assert params.get("google_domain", "google.com") == "google.com"
        assert "google.es" not in str(request.url)


async def test_a_spanish_vendor_is_still_searched_in_spain(sent):
    await gather_evidence(
        "Acme Corp", MADRID, SerpApiSearches(), locale=locale_for_address(MADRID), when_window="2y"
    )

    assert [request.url.params["hl"] for request in sent] == ["es", "es", "es"]
    assert sent[0].url.params["google_domain"] == "google.es"


async def test_the_verifier_derives_the_market_and_records_it():
    """No caller passes a locale, so the address is the only thing that can decide."""
    seen: list[SearchLocale] = []

    class RecordingSearches:
        async def find_official_site(self, *, legal_name: str, locale: SearchLocale):
            seen.append(locale)
            return ToolResult.failure("no network in this test")

        async def adverse_media(self, *, legal_name: str, locale: SearchLocale, when_window: str):
            seen.append(locale)
            return ToolResult.failure("no network in this test")

        async def verify_address(self, *, legal_name: str, address: str, locale: SearchLocale):
            seen.append(locale)
            return ToolResult.failure("no network in this test")

    assessment = await verify_counterparty(
        "Denver Freight Partners", DENVER, searches=RecordingSearches()
    )

    assert assessment.status is AssessmentStatus.FAILED
    assert {locale.google_domain for locale in seen} == {"google.com"}
    assert assessment.search_locale is not None
    assert assessment.search_locale.market == "United States"
