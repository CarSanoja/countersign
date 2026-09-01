"""What the synthesiser is told, and what it is told after it gets it wrong.

The evidence reaches the model as a numbered index rather than as prose, so the
only way to cite is to name an id that exists. The repair prompt names every
failure by position and kind, because "try again" produces the same draft.
"""

from countersign.agents.risk_draft import RESPONSE_SHAPE
from countersign.agents.risk_evidence import EvidenceBundle, EvidenceItem
from countersign.agents.risk_grounding import GroundingFailure
from countersign.schemas.verdict import SignalKind

SIGNAL_MEANINGS: dict[SignalKind, str] = {
    SignalKind.SENDER_DOMAIN_NOT_OFFICIAL: (
        "the domain the document was sent from is not the counterparty's official domain"
    ),
    SignalKind.SENDER_DOMAIN_UNREGISTERED: (
        "the sender domain is not registered with any registry"
    ),
    SignalKind.CONFUSABLE_ALREADY_REGISTERED: (
        "a confusable variant of the official domain is already held by someone else"
    ),
    SignalKind.BANK_DETAILS_CHANGED: (
        "the payment details differ from the ones previously on record"
    ),
    SignalKind.ENTITY_NOT_FOUND: (
        "the legal entity could not be found as an operating business"
    ),
    SignalKind.ADVERSE_MEDIA: (
        "published reporting about this entity is adverse: fraud, insolvency, sanctions, litigation"
    ),
    SignalKind.ADDRESS_NOT_A_BUSINESS: (
        "the stated address is not a business premises"
    ),
}

INSTRUCTIONS = """You are the risk synthesiser of the COUNTERSIGN fleet. You fuse the
evidence below into a draft verdict about a supplier payment.

Rules, in order of importance:
1. Every claim must cite at least one evidence id from the index and quote the exact
   words it relies on, copied verbatim from that item's text.
2. Never invent an id, a URL, a domain, a document reference or a quote. A citation that
   does not resolve against the index gets the whole draft rejected and asked for again.
3. Raise a signal only when the evidence establishes it. Do not raise one on suspicion,
   and do not omit one the evidence plainly supports.
4. Do not assign weights, scores, a risk level or a recommended action. Those are
   computed in code from a fixed table, and anything you write about them is discarded.
5. Reply with one JSON object and nothing else. No prose outside it, no code fences."""


def render_item(item: EvidenceItem) -> str:
    header = (
        f"[{item.evidence_id}] {item.channel.value} | "
        f"{item.source.provider.value} | {item.source.locator}"
    )
    if item.page is not None:
        header = f"{header} | page {item.page}"
    return f"{header}\n    {item.text.strip()}"


def render_evidence(bundle: EvidenceBundle) -> str:
    return "\n".join(render_item(item) for item in bundle.items)


def render_signal_kinds() -> str:
    return "\n".join(f"- {kind.value}: {meaning}" for kind, meaning in SIGNAL_MEANINGS.items())


def build_prompt(bundle: EvidenceBundle) -> str:
    sections = [
        INSTRUCTIONS,
        f"Counterparty under review: {bundle.subject}\nRun: {bundle.run_id}",
        f"Signal kinds you may use:\n{render_signal_kinds()}",
        f"Evidence collected in this run:\n{render_evidence(bundle)}",
    ]
    if bundle.required_signals:
        established = ", ".join(kind.value for kind in bundle.required_signals)
        sections.append(
            "The deterministic sweep already established these kinds, so your draft must "
            f"include them: {established}"
        )
    sections.append(f"Return exactly this shape:\n{RESPONSE_SHAPE}")
    return "\n\n".join(sections)


def build_repair(bundle: EvidenceBundle, failures: list[GroundingFailure]) -> str:
    """The previous draft was rejected. Say why, per claim, then ask again."""
    reasons = "\n".join(failure.as_line() for failure in failures)
    return "\n\n".join(
        [
            build_prompt(bundle),
            "Your previous draft was REJECTED and is not recoverable by editing the "
            "wording. Each line below is a claim that did not rest on collected "
            "evidence:",
            reasons,
            "Write the draft again. Drop any signal you cannot support with a verbatim "
            f"quote from one of {bundle.evidence_ids}. A shorter, fully cited verdict is "
            "correct; a longer one with an uncited claim is not.",
        ]
    )


def build_schema_repair(bundle: EvidenceBundle, error: str) -> str:
    return "\n\n".join(
        [
            build_prompt(bundle),
            f"Your previous response did not parse as the required object: {error}",
            "Return only the JSON object, with no surrounding text.",
        ]
    )
