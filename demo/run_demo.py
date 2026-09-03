"""One full COUNTERSIGN run through the real pipeline, against live APIs.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/run_demo.py --fresh

The run also writes demo/out/dossier.html, the same page the API serves, for the
run that just happened rather than for the bundled sample.

Without --fresh the run is answered from the assessment already on file for
these exact bytes, which is the correct production behaviour and the wrong one
for a demo: pass it to re-check the world on the same invoice.

Every stage below is the orchestration the tests cover, not a script that
imitates it. See demo/run_from_prompt.py for the same run started from a plain
instruction, and demo/benchmark/measure.py for the labelled set.
"""

import asyncio
import logging
import sys
from pathlib import Path

from countersign.api.dossier_page import render_dossier
from countersign.orchestration import RunConfig, run_assessment

logging.getLogger("google_genai.models").setLevel(logging.ERROR)

INVOICE = "demo/fixtures/invoice.pdf"
DOSSIER_OUT = Path("demo/out/dossier.html")
OFFICIAL_DOMAIN = "name.com"

# Foxit fetches the document to be signed over HTTPS, and its fetcher cannot
# reach every public host; this one is verified reachable.
DOCUMENT_URL = (
    "https://raw.githubusercontent.com/py-pdf/sample-files/main/001-trivial/minimal-document.pdf"
)


def show(outcome) -> None:
    print(f"  {outcome.stage.value:12} {outcome.status.value:10} {(outcome.detail or '')[:56]}")


async def main(*, fresh: bool) -> None:
    print(f"assessing {INVOICE}\n")
    result = await run_assessment(
        INVOICE,
        reuse=not fresh,
        on_stage=show,
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

    if result.reused_from:
        print("\nanswered from a prior assessment; pass --fresh to re-run")

    verdict = result.verdict
    print(f"\nVERDICT {verdict.level.value.upper()}  score {verdict.score:.2f}")
    print(f"  {verdict.headline}")
    for signal in verdict.signals:
        sources = ", ".join(f"{s.provider.value}:{s.locator}" for s in signal.claim.sources)
        print(f"  · [{signal.kind.value}] {signal.claim.statement[:78]}")
        print(f"    source: {sources}")

    print("\nGATE DECISIONS")
    for entry in result.trace:
        decision = str(getattr(entry, "decision", "")).lower()
        mark = "DENIED " if "deny" in decision else "granted"
        print(f"  {mark} {getattr(entry, 'agent_id', '?'):22} {getattr(entry, 'tool', '?')}")

    if result.envelope:
        envelope = result.envelope
        print(
            f"\nENVELOPE {envelope.get('folder_id')} status="
            f"{envelope.get('folder_status')} dispatched={envelope.get('dispatched')}"
        )
    if result.reused_from:
        print(f"\n{DOSSIER_OUT} left untouched; a reused run would overwrite the real one")
    else:
        DOSSIER_OUT.parent.mkdir(parents=True, exist_ok=True)
        DOSSIER_OUT.write_text(render_dossier(result), encoding="utf-8")
        print(f"\ndossier written to {DOSSIER_OUT}")

    print(f"trace persisted to Xano: {result.trace_persisted}")
    print(f"{verdict.recommended_action}")


if __name__ == "__main__":
    asyncio.run(main(fresh="--fresh" in sys.argv))
