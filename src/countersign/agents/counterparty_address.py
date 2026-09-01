"""Is the invoiced address premises, or a mailbox with a company name on it?

Maps is cited by place id rather than by the SERP, because a place id resolves
to the same listing tomorrow and a search-result position does not.
"""

from countersign.agents.counterparty_claims import signal_weight, source_ref
from countersign.agents.counterparty_evidence import CounterpartyEvidence, archive_locator
from countersign.agents.counterparty_judgement import AddressJudgement, CounterpartyJudgement
from countersign.schemas.evidence import Claim
from countersign.schemas.verdict import RiskSignal, SignalKind
from countersign.tools.serpapi_models import PlaceRecord

MAIL_DROP_WEIGHT = 0.65
ADDRESS_UNMATCHED_WEIGHT = 0.45
MAPS_PLACE_URL = "https://www.google.com/maps/place/?q=place_id:{place_id}"


def _place_locator(place: PlaceRecord | None, fallback: str) -> str:
    if place is None:
        return fallback
    if place.maps_place_id:
        return MAPS_PLACE_URL.format(place_id=place.maps_place_id)
    return place.website or fallback


def _place_snippet(place: PlaceRecord | None, query: str) -> str:
    if place is None:
        return query
    parts = (place.title, place.address, place.place_type, place.open_state)
    return " — ".join(part for part in parts if part) or query


def address_findings(
    legal_name: str,
    address: str,
    judgement: CounterpartyJudgement,
    evidence: CounterpartyEvidence,
    at: str,
) -> tuple[list[Claim], list[RiskSignal], list[str]]:
    """One claim about the address, plus a signal when it is not real premises."""
    maps = evidence.address
    if maps is None:
        return [], [], []
    call = judgement.address
    if call is None:
        return [], [], ["the maps search returned results but the judgement skipped the address"]
    index = call.place_index
    place = maps.places[index] if index is not None and 0 <= index < len(maps.places) else None
    errors = (
        [f"the judgement cites maps listing {index}, which was not retrieved"]
        if index is not None and place is None
        else []
    )
    claim = Claim(
        statement=_statement(legal_name, address, call),
        sources=[
            source_ref(
                _place_locator(place, archive_locator(maps.search_id, maps.query)),
                _place_snippet(place, maps.query),
                at,
            )
        ],
        confidence=call.confidence,
    )
    if call.matches_entity and call.is_real_business and not call.is_mail_drop:
        return [claim], [], errors
    if not _is_adverse(call, place):
        return [claim], [], errors
    base = MAIL_DROP_WEIGHT if call.is_mail_drop else ADDRESS_UNMATCHED_WEIGHT
    signal = RiskSignal(
        kind=SignalKind.ADDRESS_NOT_A_BUSINESS,
        weight=signal_weight(base, call.confidence),
        claim=claim,
    )
    return [claim], [signal], errors


def _is_adverse(call: AddressJudgement, place: object | None) -> bool:
    """Absence of a map listing is not evidence the premises are fake.

    Plenty of real companies have no Maps entry, and a vendor whose own site
    states the invoiced address is corroborated by another channel. So the
    signal needs something positive: a mail drop, or a listing that shows some
    other business trading there. "Maps found nothing" leaves the question open
    and must not push the verdict.
    """
    if call.is_mail_drop:
        return True
    return place is not None


def _statement(legal_name: str, address: str, call: AddressJudgement) -> str:
    if call.is_mail_drop:
        head = f"The address invoiced by {legal_name} is a mail drop or virtual office"
    elif not call.matches_entity:
        head = f"No business listing for {legal_name} was found at the invoiced address"
    elif not call.is_real_business:
        head = f"The address invoiced by {legal_name} does not read as trading premises"
    else:
        head = f"{legal_name} trades from the invoiced address as a listed business"
    return f"{head} ({address.strip() or 'no address given'}): {call.reasoning}"
