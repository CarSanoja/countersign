"""The COUNTERSIGN fleet.

Two of the seven never call a model: the domain sentinel is a deterministic
sweep, and the envelope preparer is plumbing. The other five are where the
reasoning lives, and each one is bounded by the capabilities it holds.
"""

from dataclasses import dataclass

from countersign.fleet.capabilities import CountersignCapability as Cap

STAGE_INGEST = "ingest"
STAGE_VERIFY = "verify"
STAGE_ASSESS = "assess"
STAGE_DRAFT = "draft"
STAGE_HANDOFF = "handoff"

PRO = "gemini_pro_model"
FLASH = "gemini_flash_model"

ARMOR_SCREENER_ID = "invoice-armor-screener"
DOCUMENT_EXTRACTOR_ID = "document-extractor"
COUNTERPARTY_VERIFIER_ID = "counterparty-verifier"
DOMAIN_SENTINEL_ID = "domain-sentinel"
RISK_SYNTHESIZER_ID = "risk-synthesizer"
DOCUMENT_DRAFTER_ID = "document-drafter"
ENVELOPE_PREPARER_ID = "envelope-preparer"


@dataclass(frozen=True)
class CountersignAgent:
    agent_id: str
    fleet_index: int
    display_name: str
    role: str
    runs_when: str
    stages: tuple[str, ...]
    capabilities: tuple[str, ...]
    model_setting: str | None = None
    reasoning: str = ""

    @property
    def calls_a_model(self) -> bool:
        return self.model_setting is not None

    @property
    def principal_id(self) -> str:
        return f"countersign-principal-{self.agent_id}"


FLEET: tuple[CountersignAgent, ...] = (
    CountersignAgent(
        agent_id=ARMOR_SCREENER_ID,
        fleet_index=1,
        display_name="Invoice armor screener",
        role="Screens the uploaded invoice for prompt injection before any agent reads it",
        runs_when="on every document, before extraction",
        stages=(STAGE_INGEST,),
        capabilities=(Cap.DOC_EXTRACT,),
        model_setting=FLASH,
        reasoning="A supplier invoice is attacker-controlled input. Text embedded in the "
        "PDF that instructs the fleet to approve the payment is the obvious attack, "
        "and it has to be caught before extraction, not after.",
    ),
    CountersignAgent(
        agent_id=DOCUMENT_EXTRACTOR_ID,
        fleet_index=2,
        display_name="Document extractor",
        role="Pulls entity, address, bank details, totals and sender domain with page provenance",
        runs_when="on every document",
        stages=(STAGE_INGEST,),
        capabilities=(Cap.DOC_EXTRACT,),
        model_setting=FLASH,
        reasoning="Nutrient returns the deterministic layout and text; the model only maps "
        "those spans onto named fields, and every field keeps the page and box it came "
        "from so the extraction stays checkable.",
    ),
    CountersignAgent(
        agent_id=COUNTERPARTY_VERIFIER_ID,
        fleet_index=3,
        display_name="Counterparty verifier",
        role="Decides whether search results are about this entity, and whether they are adverse",
        runs_when="on every document",
        stages=(STAGE_VERIFY,),
        capabilities=(Cap.WEB_SEARCH,),
        model_setting=PRO,
        reasoning="This is the hard judgement in the pipeline. 'Acme Corp' matches hundreds "
        "of unrelated results; deciding which ones are the same legal entity, and whether a "
        "hit is genuinely adverse or just a namesake, is not something a rule can do.",
    ),
    CountersignAgent(
        agent_id=DOMAIN_SENTINEL_ID,
        fleet_index=4,
        display_name="Domain sentinel",
        role="Sweeps confusable variants of the official domain and reports who already holds them",
        runs_when="once the official domain is known",
        stages=(STAGE_VERIFY,),
        capabilities=(Cap.DOMAIN_QUERY,),
        reasoning="Deliberately no model. Generating confusables and asking a registry who "
        "owns them is deterministic, reproducible and cheap; a model here would add "
        "nondeterminism to the one signal that has to be defensible in an audit.",
    ),
    CountersignAgent(
        agent_id=RISK_SYNTHESIZER_ID,
        fleet_index=5,
        display_name="Risk synthesiser",
        role="Fuses the evidence into a verdict where every claim cites the span it rests on",
        runs_when="once extraction and verification are complete",
        stages=(STAGE_ASSESS,),
        capabilities=(),
        model_setting=PRO,
        reasoning="Weighing a bank-detail change against domain age, entity match and adverse "
        "media is exactly the judgement a finance analyst makes in four minutes. The verdict "
        "is rejected if any claim lacks a source span.",
    ),
    CountersignAgent(
        agent_id=DOCUMENT_DRAFTER_ID,
        fleet_index=6,
        display_name="Document drafter",
        role="Shapes the structured payload for the out-of-band bank verification document",
        runs_when="only when the verdict calls for a counter-document",
        stages=(STAGE_DRAFT,),
        capabilities=(Cap.DOC_GENERATE,),
        model_setting=FLASH,
        reasoning="Turning a risk verdict into the fields a template expects is generation, "
        "not retrieval. The template itself is fixed, so the model shapes data, never prose "
        "that ends up in a legal instrument.",
    ),
    CountersignAgent(
        agent_id=ENVELOPE_PREPARER_ID,
        fleet_index=7,
        display_name="Envelope preparer",
        role="Builds the signature envelope and stops. Holds no capability to execute it",
        runs_when="once a document exists to sign",
        stages=(STAGE_HANDOFF,),
        capabilities=(Cap.ENVELOPE_PREPARE,),
        reasoning="No model, and no signing capability. This agent exists to make the "
        "boundary concrete: it assembles everything a person needs to decide, and the "
        "decision is not its to take.",
    ),
)


def agents_that_call_a_model() -> tuple[CountersignAgent, ...]:
    return tuple(a for a in FLEET if a.calls_a_model)


def grants() -> dict[str, frozenset[str]]:
    return {a.agent_id: frozenset(a.capabilities) for a in FLEET}
