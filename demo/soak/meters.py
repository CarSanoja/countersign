"""Every unit a run spends, counted at the seam that spends it.

Cost per file is not an estimate here. Nutrient reports what it billed in a
response header, the registry is asked for a countable number of names, SerpApi
is metered by the budget that hands the assessment back, and each of the three
model seams is wrapped so a retry counts as the call it is. What the soak
reports as cost is therefore what the providers were actually asked to do.

Two seams are wired to a refusal rather than to a provider. The soak configures
no template and no signing party, so generation and delivery skip before either
is reached; the refusal is there so that "no envelope was created" is a property
of the harness and not a property of a configuration someone could change.
"""

from dataclasses import dataclass, field
from typing import Any

from autocurricula.tools.base import ToolResult

from countersign.agents.counterparty_model import VertexCounterpartyModel
from countersign.agents.counterparty_verifier import AssessmentStatus, CounterpartyAssessment
from countersign.agents.document_extractor import extract_from_layout
from countersign.agents.document_extractor_layout import DocumentLayout
from countersign.agents.document_extractor_model import vertex_text_model
from countersign.agents.document_extractor_nutrient import fetch_layout
from countersign.agents.risk_evidence import EvidenceBundle
from countersign.agents.risk_model import FLASH_MODEL, vertex_model
from countersign.agents.risk_synthesizer import synthesize_verdict
from countersign.orchestration import AssessmentPorts
from countersign.orchestration.ports import live_check_domains
from countersign.schemas.verdict import Verdict
from identity import IdentityBudget

ERROR_CHARS = 200


@dataclass
class RunMeter:
    """What one expediente cost, and what went wrong while it was being spent."""

    nutrient_calls: int = 0
    nutrient_credits: float = 0.0
    namecom_calls: int = 0
    namecom_lookups: int = 0
    serpapi_searches: int = 0
    vertex_calls: int = 0
    identity_from_memo: bool = False
    provider_errors: list[str] = field(default_factory=list)
    budget_violations: list[str] = field(default_factory=list)

    def fault(self, provider: str, detail: str | None) -> None:
        self.provider_errors.append(f"{provider}: {(detail or 'no detail')[:ERROR_CHARS]}")

    def as_dict(self) -> dict[str, float | int]:
        return {
            "nutrient_credits": round(self.nutrient_credits, 2),
            "nutrient_calls": self.nutrient_calls,
            "serpapi_searches": self.serpapi_searches,
            "namecom_lookups": self.namecom_lookups,
            "namecom_calls": self.namecom_calls,
            "vertex_calls": self.vertex_calls,
        }


class _CountingTextModel:
    """The extractor's model seam, counted."""

    def __init__(self, inner: Any, meter: RunMeter) -> None:
        self._inner = inner
        self._meter = meter

    async def generate_text(self, prompt: str, *, model: str) -> str:
        self._meter.vertex_calls += 1
        return await self._inner.generate_text(prompt, model=model)


class _CountingJudgementModel:
    """The verifier's model seam, counted."""

    def __init__(self, inner: Any, meter: RunMeter) -> None:
        self._inner = inner
        self._meter = meter

    async def complete(self, *, system: str, user: str) -> str:
        self._meter.vertex_calls += 1
        return await self._inner.complete(system=system, user=user)


def _counting_verdict_model(meter: RunMeter) -> Any:
    """The synthesiser's model seam, counted once per grounding attempt."""
    inner = vertex_model(FLASH_MODEL)

    async def call(prompt: str) -> str:
        meter.vertex_calls += 1
        return await inner(prompt)

    return call


def _credits(reported: Any) -> float:
    try:
        return float(reported)
    except (TypeError, ValueError):
        return 0.0


class MeteredPorts:
    """The live pipeline with all six seams observed and two of them closed."""

    def __init__(self, meter: RunMeter, budget: IdentityBudget) -> None:
        self.meter = meter
        self.budget = budget

    async def extract(self, document_ref: str) -> ToolResult:
        model = vertex_text_model()
        if isinstance(model, ToolResult):
            self.meter.fault("vertex", model.error)
            return model
        parsed = await fetch_layout(document_ref)
        self.meter.nutrient_calls += 1
        if not parsed.ok:
            self.meter.fault("nutrient", parsed.error)
            return parsed
        self.meter.nutrient_credits += _credits(parsed.payload.get("credit_cost"))
        layout = DocumentLayout.model_validate(parsed.payload["layout"])
        result = await extract_from_layout(layout, _CountingTextModel(model, self.meter))
        if not result.ok:
            self.meter.fault("vertex", result.error)
        return result

    async def verify(self, legal_name: str, address: str) -> CounterpartyAssessment:
        model = _CountingJudgementModel(VertexCounterpartyModel(), self.meter)
        assessment, spent = await self.budget.verify(legal_name, address, model)
        self.meter.serpapi_searches += spent
        self.meter.identity_from_memo = spent == 0
        if assessment.status is AssessmentStatus.FAILED:
            self.meter.fault("serpapi", "; ".join(assessment.errors))
        return assessment

    async def check_domains(self, domain_names: list[str]) -> ToolResult:
        self.meter.namecom_calls += 1
        self.meter.namecom_lookups += len(domain_names)
        result = await live_check_domains(domain_names)
        if not result.ok:
            self.meter.fault("namecom", result.error)
        return result

    async def synthesize(self, bundle: EvidenceBundle) -> Verdict:
        return await synthesize_verdict(bundle, model=_counting_verdict_model(self.meter))

    async def generate(self, template_path: str, data: dict, document_name: str) -> ToolResult:
        self.meter.budget_violations.append(
            "the generation seam was reached; the soak configures no template and must not render"
        )
        raise AssertionError("the soak must not spend a render credit")

    async def prepare_envelope(
        self, document_url: str, document_name: str, parties: list, fields: list
    ) -> ToolResult:
        self.meter.budget_violations.append(
            "the envelope seam was reached; the soak configures no signing party"
        )
        raise AssertionError("the soak must not create a Foxit eSign envelope")

    def ports(self) -> AssessmentPorts:
        return AssessmentPorts(
            extract=self.extract,
            verify=self.verify,
            check_domains=self.check_domains,
            synthesize=self.synthesize,
            generate=self.generate,
            prepare_envelope=self.prepare_envelope,
        )


__all__ = ["MeteredPorts", "RunMeter"]
