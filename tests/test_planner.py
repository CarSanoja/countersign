"""The planner reads an instruction; it never invents the thing being checked."""

import pytest

from countersign.agents.planner import RunPlan, plan_from_rules, plan_run


def test_a_named_document_and_domain_are_read_off_the_sentence():
    plan = plan_from_rules(
        "Check invoice-4471.pdf from Name.com before we pay it; their real site is name.com"
    )
    assert plan.document_ref == "invoice-4471.pdf"
    assert plan.official_domain == "name.com"
    assert plan.is_actionable


def test_an_instruction_naming_no_document_is_not_actionable():
    assert not plan_from_rules("is this legit?").is_actionable


def test_a_pdf_path_is_not_mistaken_for_a_domain():
    plan = plan_from_rules("review demo/fixtures/invoice.pdf")
    assert plan.document_ref == "demo/fixtures/invoice.pdf"
    assert plan.official_domain == ""


class _Model:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    async def generate_text(self, prompt: str, *, model: str) -> str:
        self.calls += 1
        return self.answer


async def test_the_model_is_not_consulted_when_the_rules_already_settled_it():
    model = _Model("{}")
    await plan_run("check invoice-4471.pdf against name.com", model=model)
    assert model.calls == 0


async def test_the_rules_win_over_the_model_on_the_official_domain():
    model = _Model('{"official_domain": "attacker.example", "legal_name": "X"}')
    plan = await plan_run("check invoice-4471.pdf, real site name.com", model=model)
    assert plan.official_domain == "name.com"


async def test_an_unusable_model_answer_falls_back_to_the_rules():
    plan = await plan_run("check invoice-4471.pdf", model=_Model("not json at all"))
    assert plan.document_ref == "invoice-4471.pdf"
    assert plan.planned_by == "rules"


@pytest.mark.parametrize("instruction", ["", "   ", "pay it"])
async def test_nothing_actionable_is_produced_from_nothing(instruction):
    assert not (await plan_run(instruction)).is_actionable


def test_a_plan_without_a_document_is_never_actionable():
    assert not RunPlan(official_domain="name.com").is_actionable
