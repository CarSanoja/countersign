"""A plain instruction in, a run plan out.

Foxit's brief asks for an agent that starts from a plain prompt. Taking a PDF
and a filled-in config is not that: somebody has already done the thinking. The
planner reads what a person would actually type and decides what the run needs.

It plans; it does not act. Nothing here touches an external system, so a bad
plan costs a re-plan and never a payment.
"""

import json
import re
from typing import Any, Protocol

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

_DOCUMENT = re.compile(r"[\w./-]+\.pdf\b", re.IGNORECASE)
_DOMAIN = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.IGNORECASE)

INSTRUCTIONS = """You turn a plain instruction from a finance or procurement team into a
plan for a vendor-assessment run.

Return JSON only, this exact shape:
{"document_ref": "...", "legal_name": "...", "official_domain": "...", "intent": "..."}

- document_ref: the file the instruction refers to, verbatim. "" if none is named.
- legal_name: the vendor as the instruction names it. "" if not stated.
- official_domain: the vendor's real domain ONLY if the instruction states it.
  Never guess it from the company name; leaving it empty makes the run look it
  up, and a guess here would silently become the thing every other check is
  measured against.
- intent: one short sentence, what the person actually wants.

Instruction:
"""


class PlannerModel(Protocol):
    async def generate_text(self, prompt: str, *, model: str) -> str: ...


class RunPlan(StrictBaseModel):
    document_ref: str = ""
    legal_name: str = ""
    official_domain: str = ""
    intent: str = ""
    planned_by: str = Field(default="rules")

    @property
    def is_actionable(self) -> bool:
        return bool(self.document_ref)


def plan_from_rules(instruction: str) -> RunPlan:
    """What can be read off the sentence without asking anyone."""
    document = _DOCUMENT.search(instruction)
    domains = [
        found.group(1).lower()
        for found in _DOMAIN.finditer(instruction)
        if not found.group(1).lower().endswith(".pdf")
    ]
    return RunPlan(
        document_ref=document.group(0) if document else "",
        official_domain=domains[0] if domains else "",
        intent=instruction.strip()[:200],
    )


async def plan_run(
    instruction: str,
    *,
    model: PlannerModel | None = None,
    model_name: str = "gemini-3.5-flash-lite",
) -> RunPlan:
    """Read the instruction, deterministically first and with a model only if needed."""
    settled = plan_from_rules(instruction)
    if model is None or (settled.document_ref and settled.official_domain):
        return settled
    try:
        raw = await model.generate_text(INSTRUCTIONS + instruction, model=model_name)
    except Exception:
        return settled
    parsed = _parse(raw)
    if parsed is None:
        return settled
    return RunPlan(
        document_ref=settled.document_ref or str(parsed.get("document_ref", "")),
        legal_name=str(parsed.get("legal_name", "")),
        official_domain=settled.official_domain or str(parsed.get("official_domain", "")),
        intent=str(parsed.get("intent", "")) or settled.intent,
        planned_by="model",
    )


def _parse(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
