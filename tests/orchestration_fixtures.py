"""A whole run with every seam faked: no credential, no credit, no network."""

from autocurricula.tools.base import ToolResult

from countersign.agents.counterparty_verifier import AssessmentStatus, CounterpartyAssessment
from countersign.agents.document_extractor import ExtractedField, ExtractedInvoice
from countersign.orchestration import AssessmentPorts, RunConfig
from countersign.orchestration.stages import STAGE_CREDENTIALS
from countersign.schemas.evidence import Claim, PageBox, Provider, SourceRef
from countersign.schemas.verdict import RiskLevel, RiskSignal, SignalKind, Verdict

AT = "2026-08-31T10:00:00Z"
OFFICIAL = "acmecorp.com"
LOOKALIKE = "acrnecorp.com"

PROVIDER_VARIABLES = tuple(
    dict.fromkeys(
        name
        for requirements in STAGE_CREDENTIALS.values()
        for alternatives in requirements
        for name in alternatives
    )
)
"""Derived from STAGE_CREDENTIALS so the list cannot drift from what the
pipeline actually reads. A hand-written copy silently stopped unsetting the
Foxit client id and secret once those were added, which made these tests pass
on a clean machine and fail on one with .env.local loaded."""


def configure_every_provider(monkeypatch, **overrides: str) -> None:
    for variable in PROVIDER_VARIABLES:
        monkeypatch.setenv(variable, overrides.get(variable, "configured"))


def unconfigure_every_provider(monkeypatch) -> None:
    for variable in PROVIDER_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def field(value: str, snippet: str) -> ExtractedField:
    return ExtractedField(
        value=value,
        span_id="s1",
        source=SourceRef(
            provider=Provider.NUTRIENT,
            locator="invoice-2291.pdf",
            box=PageBox(page=0, left=0.1, top=0.2, width=0.5, height=0.04),
            snippet=snippet,
            retrieved_at=AT,
        ),
    )


INVOICE = ExtractedInvoice(
    document_path="invoice-2291.pdf",
    extracted_at=AT,
    page_count=1,
    legal_name=field("Acme Corp", "Acme Corp, S.L."),
    address=field("Calle Mayor 1, Madrid", "Calle Mayor 1, Madrid"),
    iban=field("LT123250000000000001", "Remit to IBAN LT12 3250 0000 0000 0001"),
    sender_domain=field(LOOKALIKE, f"billing@{LOOKALIKE}"),
)

SERP_SOURCE = SourceRef(
    provider=Provider.SERPAPI,
    locator="https://serpapi.com/searches/abc.json",
    snippet=f"Acme Corp official site {OFFICIAL}",
    retrieved_at=AT,
)

ASSESSMENT = CounterpartyAssessment(
    legal_name="Acme Corp",
    address="Calle Mayor 1, Madrid",
    status=AssessmentStatus.COMPLETE,
    official_domain=OFFICIAL,
    claims=[
        Claim(
            statement=f"the official site is {OFFICIAL}", sources=[SERP_SOURCE], confidence=0.8
        )
    ],
    assessed_at=AT,
    searches_spent=3,
)


async def fake_extract(document_ref: str) -> ToolResult:
    return ToolResult.success({"invoice": INVOICE.model_dump(mode="json")})


async def fake_verify(legal_name: str, address: str) -> CounterpartyAssessment:
    return ASSESSMENT


async def fake_check_domains(domain_names: list[str]) -> ToolResult:
    return ToolResult.success(
        {
            "environment": "production",
            "requested": domain_names,
            "registered": [LOOKALIKE],
            "available": [name for name in domain_names if name != LOOKALIKE],
            "unanswered": [],
        }
    )


def verdict_for(bundle) -> Verdict:
    return Verdict(
        run_id=bundle.run_id,
        level=RiskLevel.HIGH,
        headline="Payment redirected onto a lookalike domain",
        signals=[
            RiskSignal(
                kind=SignalKind.CONFUSABLE_ALREADY_REGISTERED,
                weight=0.35,
                claim=Claim(
                    statement="a confusable of the official domain is already registered",
                    sources=[bundle.items[-1].source],
                    confidence=0.9,
                ),
            )
        ],
        recommended_action="Do not pay.",
        decided_at=AT,
    )


async def fake_synthesize(bundle) -> Verdict:
    return verdict_for(bundle)


async def fake_generate(template_path: str, data: dict, document_name: str) -> ToolResult:
    return ToolResult.success({"name": document_name, "urn": "urn:doc:1"})


async def fake_prepare(
    document_url: str, document_name: str, parties: list[dict], fields: list[dict]
) -> ToolResult:
    return ToolResult.success({"folder_id": 99, "folder_status": "DRAFT", "dispatched": False})


def fake_ports(**overrides) -> AssessmentPorts:
    seams = {
        "extract": fake_extract,
        "verify": fake_verify,
        "check_domains": fake_check_domains,
        "synthesize": fake_synthesize,
        "generate": fake_generate,
        "prepare_envelope": fake_prepare,
    }
    return AssessmentPorts(**(seams | overrides))


def demo_config() -> RunConfig:
    return RunConfig(
        template_path="/tmp/confirmation.docx",
        document_url="https://example.invalid/confirmation.pdf",
        parties=[{"email": "finance@buyer.example", "name": "Finance"}],
        fields=[{"type": "signature", "party": 1, "x": 72, "y": 600, "width": 180, "height": 40}],
    )
