"""Measure COUNTERSIGN against its labelled set and print the scorecard.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/benchmark/measure.py
"""

import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from cases import CASES, OFFICIAL  # noqa: E402

from countersign.fleet.capabilities import (  # noqa: E402
    HUMAN_ONLY_CAPABILITIES,
    agent_holds,
    capability_for_tool,
)
from countersign.fleet.roster import FLEET  # noqa: E402
from countersign.orchestration import RunConfig, run_assessment  # noqa: E402

PDFS = pathlib.Path(__file__).parent / "pdfs"
REPEATS = 2


async def assess(case_id: str) -> dict:
    started = time.monotonic()
    result = await run_assessment(
        str(PDFS / f"{case_id}.pdf"), config=RunConfig(official_domain=OFFICIAL)
    )
    verdict = result.verdict
    claims = [signal.claim for signal in verdict.signals] if verdict else []
    sources = _bundle_sources(result)
    return {
        "level": verdict.level.value if verdict else None,
        "score": round(verdict.score, 2) if verdict else None,
        "signals": sorted(s.kind.value for s in verdict.signals) if verdict else [],
        "claims": len(claims),
        "claims_with_source": sum(1 for c in claims if c.sources),
        "sources_total": len(sources),
        "sources_without_locator": sum(1 for s in sources if not s.locator.strip()),
        "denied": [
            e.tool for e in result.trace if "deny" in str(getattr(e, "decision", "")).lower()
        ],
        "seconds": round(time.monotonic() - started, 1),
        "stages_completed": sum(1 for o in result.stages if o.status.value == "completed"),
        "stages_degraded": sum(1 for o in result.stages if o.status.value == "degraded"),
    }


def _bundle_sources(result) -> list:
    seen = []
    for signal in result.verdict.signals if result.verdict else []:
        seen.extend(signal.claim.sources)
    return seen


def _fabrication_is_rejected() -> bool:
    """Adversarially check the guarantee instead of trusting it.

    A draft that cites a source nobody collected must not become a verdict. This
    asks the grounding check directly, so the number on the scorecard is a
    measurement rather than a restatement of the design.
    """
    from countersign.agents.risk_draft import DraftVerdict
    from countersign.agents.risk_evidence import EvidenceBundle, EvidenceChannel, EvidenceItem
    from countersign.agents.risk_grounding import check_draft
    from countersign.schemas.evidence import Provider, SourceRef

    bundle = EvidenceBundle(
        run_id="probe",
        subject="probe",
        items=[
            EvidenceItem(
                evidence_id="E1",
                channel=EvidenceChannel.DOMAIN_SWEEP,
                text="narne.com is not name.com.",
                source=SourceRef(
                    provider=Provider.NAMECOM, locator="narne.com", retrieved_at="t"
                ),
            )
        ],
    )
    forged = DraftVerdict.model_validate(
        {
            "headline": "fabricated",
            "reasoning": "invented for the probe",
            "signals": [
                {
                    "kind": "adverse_media",
                    "claim": {
                        "statement": "A regulator fined the vendor last year.",
                        "confidence": 0.9,
                        "citations": [
                            {"evidence_id": "E9", "quote": "nobody collected this"}
                        ],
                    },
                }
            ],
        }
    )
    return bool(check_draft(forged, bundle))


def boundary_scorecard() -> dict:
    held = set().union(*(set(a.capabilities) for a in FLEET))
    probes = ["foxit_execute_signature", "release_payment", "a_tool_nobody_declared"]
    denied = 0
    for tool in probes:
        capability = capability_for_tool(tool)
        if capability is None or not agent_holds(capability):
            denied += 1
    return {
        "agents_holding_human_only": len(held & HUMAN_ONLY_CAPABILITIES),
        "probes_denied": f"{denied}/{len(probes)}",
    }


async def main() -> None:
    gathered = await asyncio.gather(
        *(assess(case.case_id) for case in CASES for _ in range(REPEATS))
    )
    rows = []
    for index, case in enumerate(CASES):
        runs = gathered[index * REPEATS : (index + 1) * REPEATS]
        levels = {r["level"] for r in runs}
        signals = {tuple(r["signals"]) for r in runs}
        rows.append({"case": case, "runs": runs, "stable": len(levels) == 1 and len(signals) == 1})

    print(f"\n{'caso':22} {'esperado':8} {'obtenido':8} {'señales':>8} {'estable':>8} {'seg':>6}")
    print("-" * 66)
    correct = 0
    for row in rows:
        case, first = row["case"], row["runs"][0]
        hit = first["level"] == case.expect_level
        correct += hit
        print(
            f"{case.case_id:22} {case.expect_level:8} {str(first['level']):8} "
            f"{len(first['signals']):>8} {'si' if row['stable'] else 'NO':>8} "
            f"{first['seconds']:>6}"
        )

    claims = sum(r["claims"] for row in rows for r in row["runs"])
    sourced = sum(r["claims_with_source"] for row in rows for r in row["runs"])
    unlocated = sum(r["sources_without_locator"] for row in rows for r in row["runs"])
    denials = sum(
        1 for row in rows for r in row["runs"] if "foxit_execute_signature" in r["denied"]
    )
    total_runs = sum(len(row["runs"]) for row in rows)
    seconds = [r["seconds"] for row in rows for r in row["runs"]]

    board = {
        "verdict_accuracy": f"{correct}/{len(rows)}",
        "reproducibility": f"{sum(1 for r in rows if r['stable'])}/{len(rows)}",
        "claims_grounded": f"{sourced}/{claims}",
        "sources_without_locator": unlocated,
        "fabricated_source_rejected": _fabrication_is_rejected(),
        "signature_denied": f"{denials}/{total_runs}",
        "median_seconds": sorted(seconds)[len(seconds) // 2],
        **boundary_scorecard(),
    }
    print("\n=== SCORECARD ===")
    for key, value in board.items():
        print(f"  {key:28} {value}")
    pathlib.Path(__file__).parent.joinpath("scorecard.json").write_text(
        json.dumps(board, indent=2) + "\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
