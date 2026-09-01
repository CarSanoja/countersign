"""The seams. Every stage reaches the world through one of these, and only these.

Each port is a Protocol with a live implementation bound to the agent that owns
that stage. They are injected rather than imported inside the pipeline for two
reasons that are not testing convenience: the Vertex ADC and the SerpApi quota
are both scarce, and a run that cannot be exercised without spending either is a
run nobody will exercise.
"""

import os
from dataclasses import dataclass
from typing import Any, Protocol

from autocurricula.schemas.common import StrictBaseModel
from autocurricula.tools.base import ToolResult
from pydantic import Field

from countersign.agents.counterparty_verifier import CounterpartyAssessment, verify_counterparty
from countersign.agents.document_extractor import extract_invoice
from countersign.agents.document_extractor_model import vertex_text_model
from countersign.agents.envelope_preparer import prepare_envelope_for_signature
from countersign.agents.risk_evidence import EvidenceBundle
from countersign.agents.risk_synthesizer import synthesize_verdict
from countersign.orchestration.domain_sweep import SWEEP_LIMIT
from countersign.schemas.verdict import Verdict
from countersign.tools.doctavian import doctavian_generate_document
from countersign.tools.foxit_pdf import foxit_generate_document
from countersign.tools.namecom_availability import namecom_check_availability


class ExtractPort(Protocol):
    async def __call__(self, document_ref: str) -> ToolResult: ...


class VerifyPort(Protocol):
    async def __call__(self, legal_name: str, address: str) -> CounterpartyAssessment: ...


class DomainPort(Protocol):
    async def __call__(self, domain_names: list[str]) -> ToolResult: ...


class SynthesizePort(Protocol):
    async def __call__(self, bundle: EvidenceBundle) -> Verdict: ...


class GeneratePort(Protocol):
    async def __call__(
        self, template_path: str, data: dict[str, Any], document_name: str
    ) -> ToolResult: ...


class EnvelopePort(Protocol):
    async def __call__(
        self,
        document_url: str,
        document_name: str,
        parties: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> ToolResult: ...


class RunConfig(StrictBaseModel):
    """What the run needs that the document cannot tell it."""

    legal_name: str = ""
    address: str = ""
    official_domain: str = ""
    sender_domain: str = ""
    template_path: str = ""
    document_name: str = "bank-detail-confirmation"
    document_url: str = ""
    parties: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    sweep_limit: int = Field(default=SWEEP_LIMIT, ge=1)


@dataclass(frozen=True)
class AssessmentPorts:
    """The six seams, live by default and replaceable one at a time."""

    extract: ExtractPort | None = None
    verify: VerifyPort | None = None
    check_domains: DomainPort | None = None
    synthesize: SynthesizePort | None = None
    generate: GeneratePort | None = None
    prepare_envelope: EnvelopePort | None = None

    def resolved(self) -> "ResolvedPorts":
        """Fill every empty seam with the live implementation of that stage."""
        return ResolvedPorts(
            extract=self.extract or live_extract,
            verify=self.verify or live_verify,
            check_domains=self.check_domains or live_check_domains,
            synthesize=self.synthesize or live_synthesize,
            generate=self.generate or live_generate,
            prepare_envelope=self.prepare_envelope or live_prepare_envelope,
        )


@dataclass(frozen=True)
class ResolvedPorts:
    """The same six seams, with nothing left unbound."""

    extract: ExtractPort
    verify: VerifyPort
    check_domains: DomainPort
    synthesize: SynthesizePort
    generate: GeneratePort
    prepare_envelope: EnvelopePort


async def live_extract(document_ref: str) -> ToolResult:
    """Nutrient for the layout, the flash model for the mapping onto fields."""
    model = vertex_text_model()
    if isinstance(model, ToolResult):
        return model
    return await extract_invoice(document_ref, model)


async def live_verify(legal_name: str, address: str) -> CounterpartyAssessment:
    """Three SerpApi credits and one judgement from the strong model."""
    return await verify_counterparty(legal_name, address)


async def live_check_domains(domain_names: list[str]) -> ToolResult:
    """Production, because the sandbox registry knows nothing about real ownership."""
    return await namecom_check_availability(domain_names, environment="production")


async def live_synthesize(bundle: EvidenceBundle) -> Verdict:
    """Raises UngroundedVerdictError rather than returning an uncited verdict."""
    return await synthesize_verdict(bundle)


async def live_generate(
    template_path: str, data: dict[str, Any], document_name: str
) -> ToolResult:
    """Generate the counter-document, from whichever provider is configured.

    Doctavian is the intended generator and the one its challenge asks for, but
    it needs both an api key and a bearer, and half a credential is worse than
    none: routing to it with only the key fails at the template rather than at
    the door. It also only accepts docx and xlsx, so an html template is not a
    question it can be asked — checking the extension routes on what the provider
    can actually do rather than on whether we hold its credentials.

    Foxit PDF Services covers the same reversible work and takes html, so the
    stage still produces the document a person signs.
    """
    credentialed = os.environ.get("DOCTAVIAN_API_KEY", "").strip() and (
        os.environ.get("DOCTAVIAN_ACCESS_TOKEN", "").strip()
        or os.environ.get("DOCTAVIAN_SERVICE_TOKEN", "").strip()
    )
    generatable = template_path.lower().endswith((".docx", ".xlsx"))
    if credentialed and generatable:
        return await doctavian_generate_document(
            template_path=template_path, data=data, document_name=document_name
        )
    return await foxit_generate_document(
        template_path=template_path, data=data, document_name=document_name
    )


async def live_prepare_envelope(
    document_url: str,
    document_name: str,
    parties: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> ToolResult:
    return await prepare_envelope_for_signature(
        document_url=document_url,
        document_name=document_name,
        parties=parties,
        fields=fields,
    )


__all__ = [
    "AssessmentPorts",
    "ResolvedPorts",
    "DomainPort",
    "EnvelopePort",
    "ExtractPort",
    "GeneratePort",
    "RunConfig",
    "SynthesizePort",
    "VerifyPort",
    "live_check_domains",
    "live_extract",
    "live_generate",
    "live_prepare_envelope",
    "live_synthesize",
    "live_verify",
]
