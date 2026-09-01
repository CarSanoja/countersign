"""One full COUNTERSIGN run through the real pipeline, against live APIs.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/run_demo.py

Every stage below is the orchestration the tests cover, not a script that
imitates it. See demo/run_from_prompt.py for the same run started from a plain
instruction, and demo/benchmark/measure.py for the labelled set.
"""

import asyncio

from countersign.orchestration import RunConfig, run_assessment

INVOICE = "demo/fixtures/invoice.pdf"
OFFICIAL_DOMAIN = "name.com"

# Foxit fetches the document to be signed over HTTPS, and its fetcher cannot
# reach every public host; this one is verified reachable.
DOCUMENT_URL = (
    "https://raw.githubusercontent.com/py-pdf/sample-files/main/"
    "001-trivial/minimal-document.pdf"
)


async def main() -> None:
    result = await run_assessment(
        INVOICE,
        config=RunConfig(
            official_domain=OFFICIAL_DOMAIN,
            document_url=DOCUMENT_URL,
            document_name="Bank verification - Name.com Inc",
            parties=[
                {
                    "first_name": "Finance",
                    "last_name": "Team",
                    "email_id": "csanoja@somosquanta.com",
                }
            ],
            fields=[
                {
                    "type": "signature",
                    "party": 1,
                    "x": 72,
                    "y": 600,
                    "width": 180,
                    "height": 40,
                    "page_number": 1,
                    "required": True,
                }
            ],
        ),
    )

    print(f"run {result.run_id}\n")
    for outcome in result.stages:
        print(f"  {outcome.stage.value:12} {outcome.status.value:10} {(outcome.detail or '')[:56]}")

    verdict = result.verdict
    print(f"\nVEREDICTO {verdict.level.value.upper()}  score {verdict.score:.2f}")
    print(f"  {verdict.headline}")
    for signal in verdict.signals:
        sources = ", ".join(f"{s.provider.value}:{s.locator}" for s in signal.claim.sources)
        print(f"  · [{signal.kind.value}] {signal.claim.statement[:78]}")
        print(f"    fuente: {sources}")

    print("\nDECISIONES DEL GATE")
    for entry in result.trace:
        decision = str(getattr(entry, "decision", "")).lower()
        mark = "DENEGADO " if "deny" in decision else "permitido"
        print(f"  {mark} {getattr(entry, 'agent_id', '?'):22} {getattr(entry, 'tool', '?')}")

    if result.envelope:
        envelope = result.envelope
        print(
            f"\nSOBRE {envelope.get('folder_id')} estado="
            f"{envelope.get('folder_status')} enviado={envelope.get('dispatched')}"
        )
    print(f"\ntraza persistida en Xano: {result.trace_persisted}")
    print(f"{verdict.recommended_action}")


if __name__ == "__main__":
    asyncio.run(main())
