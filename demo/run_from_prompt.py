"""COUNTERSIGN from a plain instruction, the way Foxit's brief asks for it.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/run_from_prompt.py \\
        "Check demo/fixtures/invoice.pdf from Name.com. Their real site is name.com."
"""

import asyncio
import sys

from countersign.agents.planner import plan_run
from countersign.fleet.capabilities import agent_holds, capability_for_tool
from countersign.models.vertex import flash
from countersign.orchestration import RunConfig, run_assessment

DEFAULT = (
    "We got an invoice at demo/fixtures/invoice.pdf claiming to be from Name.com "
    "and it says their bank changed. Their real site is name.com. Should we pay it?"
)


async def main(instruction: str) -> None:
    print(f'instrucción: "{instruction}"\n')
    plan = await plan_run(instruction, model=flash())
    print(f"1. PLAN       documento={plan.document_ref or '(ninguno)'} "
          f"oficial={plan.official_domain or '(a buscar)'} via={plan.planned_by}")
    if not plan.is_actionable:
        print("\nNo se nombró ningún documento, así que no hay nada que evaluar.")
        return

    result = await run_assessment(
        plan.document_ref,
        config=RunConfig(official_domain=plan.official_domain, legal_name=plan.legal_name),
    )
    verdict = result.verdict
    print(f"2. VEREDICTO  {verdict.level.value.upper()}  score {verdict.score:.2f}")
    for signal in verdict.signals:
        sources = ", ".join(f"{s.provider.value}:{s.locator}" for s in signal.claim.sources)
        print(f"   · {signal.claim.statement[:88]}")
        print(f"     fuente: {sources}")

    print("\n3. FRONTERA")
    for tool in ("foxit_prepare_envelope", "foxit_execute_signature", "release_payment"):
        capability = capability_for_tool(tool)
        allowed = capability is not None and agent_holds(capability)
        print(f"   {tool:26} {'permitido' if allowed else 'DENEGADO'}")
    print(f"\n   {verdict.recommended_action}")


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or DEFAULT))
