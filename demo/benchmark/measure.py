"""Measure COUNTERSIGN against its labelled set and print the scorecard.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/benchmark/measure.py

Every row here has to be capable of coming out wrong. A count of claims that
carry a source measures the schema, which forbids one that does not, and would
read 100% against a system that had never fetched anything. So the grounding
rows are checked against a ledger of what the provider seams were actually
asked for and actually answered during the same run, and the boundary rows go
through the real gate in `probes`.
"""

import asyncio
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autocurricula.tools.base import ToolResult  # noqa: E402
from cases import CASES, OFFICIAL  # noqa: E402
from probes import boundary_scorecard, fabrication_is_rejected  # noqa: E402

from countersign.agents.counterparty_verifier import CounterpartyAssessment  # noqa: E402
from countersign.orchestration import AssessmentPorts, RunConfig, run_assessment  # noqa: E402
from countersign.orchestration.ports import (  # noqa: E402
    live_check_domains,
    live_extract,
    live_verify,
)
from countersign.schemas.evidence import Provider, SourceRef  # noqa: E402

PDFS = pathlib.Path(__file__).parent / "pdfs"
REPEATS = 2


class RetrievalLedger:
    """What each provider was asked for in one run, recorded at the seam.

    The pipeline reaches the world only through the six ports, so wrapping three
    of them gives an independent record of what was retrieved. The verdict is
    then checked against that record rather than against itself: a citation that
    names a domain the sweep never asked about, a document that was never
    parsed, or a URL the verifier never returned, does not resolve.
    """

    def __init__(self) -> None:
        self.retrieved: set[tuple[str, str]] = set()

    async def extract(self, document_ref: str) -> ToolResult:
        result = await live_extract(document_ref)
        if result.ok:
            self._record(Provider.NUTRIENT, document_ref)
        return result

    async def verify(self, legal_name: str, address: str) -> CounterpartyAssessment:
        assessment = await live_verify(legal_name, address)
        claims = [*assessment.claims, *(signal.claim for signal in assessment.signals)]
        for claim in claims:
            for source in claim.sources:
                self._record(source.provider, source.locator)
        return assessment

    async def check_domains(self, domain_names: list[str]) -> ToolResult:
        result = await live_check_domains(domain_names)
        answered = result.payload.get("requested") or []
        for name in [*domain_names, *answered]:
            self._record(Provider.NAMECOM, str(name))
        return result

    def ports(self) -> AssessmentPorts:
        """The live pipeline with three seams observed and none of them replaced."""
        return AssessmentPorts(
            extract=self.extract, verify=self.verify, check_domains=self.check_domains
        )

    def holds(self, source: SourceRef) -> bool:
        return (str(source.provider), source.locator.strip().lower()) in self.retrieved

    @property
    def providers(self) -> set[str]:
        return {provider for provider, _ in self.retrieved}

    def _record(self, provider: Provider, locator: str) -> None:
        if locator.strip():
            self.retrieved.add((str(provider), locator.strip().lower()))


async def assess(case_id: str) -> dict:
    started = time.monotonic()
    ledger = RetrievalLedger()
    result = await run_assessment(
        str(PDFS / f"{case_id}.pdf"),
        config=RunConfig(official_domain=OFFICIAL),
        ports=ledger.ports(),
    )
    verdict = result.verdict
    signals = verdict.signals if verdict else []
    sources = [source for signal in signals for source in signal.claim.sources]
    return {
        "level": verdict.level.value if verdict else None,
        "score": round(verdict.score, 2) if verdict else None,
        "signals": sorted(signal.kind.value for signal in signals),
        "sources": len(sources),
        "sources_retrieved": sum(1 for source in sources if ledger.holds(source)),
        "unretrieved": sorted(
            f"{source.provider.value}:{source.locator}"
            for source in sources
            if not ledger.holds(source)
        ),
        "providers_cited": sorted({source.provider.value for source in sources}),
        "providers_retrieved": sorted(ledger.providers),
        "denied": [entry.tool for entry in result.trace if not entry.allowed],
        "seconds": round(time.monotonic() - started, 1),
        "stages_completed": sum(1 for o in result.stages if o.status.value == "completed"),
        "stages_degraded": sum(1 for o in result.stages if o.status.value == "degraded"),
    }


def print_table(rows: list[dict]) -> int:
    print(f"\n{'caso':22} {'esperado':8} {'obtenido':8} {'señales':>8} {'estable':>8} {'seg':>6}")
    print("-" * 66)
    correct = 0
    for row in rows:
        case, first = row["case"], row["runs"][0]
        correct += first["level"] == case.expect_level
        print(
            f"{case.case_id:22} {case.expect_level:8} {str(first['level']):8} "
            f"{len(first['signals']):>8} {'si' if row['stable'] else 'NO':>8} "
            f"{first['seconds']:>6}"
        )
    return correct


def grounding_rows(rows: list[dict]) -> dict[str, object]:
    """The two rows that compare the verdict against what was actually fetched."""
    runs = [run for row in rows for run in row["runs"]]
    sources = sum(run["sources"] for run in runs)
    retrieved = sum(run["sources_retrieved"] for run in runs)
    cited = sorted({name for run in runs for name in run["providers_cited"]})
    collected = sorted({name for run in runs for name in run["providers_retrieved"]})
    unmatched = sorted({item for run in runs for item in run["unretrieved"]})
    board: dict[str, object] = {
        "sources_retrieved": f"{retrieved}/{sources}",
        "providers_cited": f"{len(cited)}/{len(collected)} ({', '.join(cited)})",
    }
    if unmatched:
        board["sources_not_retrieved"] = unmatched
    return board


def _isolate_from_vendor_state() -> None:
    """Measure the verdict logic, not the accumulated vendor files.

    Once a vendor acquires a file the bank signal correctly falls silent, so a
    benchmark that shares state with earlier runs stops being reproducible and
    starts measuring history. Vendor state is a real behaviour and it belongs in
    the soak test, which runs over time on purpose; here it is held out so the
    same six invoices always score the same.
    """
    os.environ.pop("COUNTERSIGN_BASELINE_SALT", None)


async def main() -> None:
    _isolate_from_vendor_state()
    gathered = await asyncio.gather(
        *(assess(case.case_id) for case in CASES for _ in range(REPEATS))
    )
    rows = []
    for index, case in enumerate(CASES):
        runs = gathered[index * REPEATS : (index + 1) * REPEATS]
        levels = {run["level"] for run in runs}
        signals = {tuple(run["signals"]) for run in runs}
        rows.append({"case": case, "runs": runs, "stable": len(levels) == 1 and len(signals) == 1})

    correct = print_table(rows)
    denials = sum(
        1 for row in rows for run in row["runs"] if "foxit_execute_signature" in run["denied"]
    )
    total_runs = sum(len(row["runs"]) for row in rows)
    seconds = sorted(run["seconds"] for row in rows for run in row["runs"])

    board = {
        "verdict_accuracy": f"{correct}/{len(rows)}",
        "reproducibility": f"{sum(1 for row in rows if row['stable'])}/{len(rows)}",
        **grounding_rows(rows),
        "fabricated_source_rejected": fabrication_is_rejected(),
        "signature_denied": f"{denials}/{total_runs}",
        **await boundary_scorecard(),
        "median_seconds": seconds[len(seconds) // 2],
    }
    print("\n=== SCORECARD ===")
    for key, value in board.items():
        print(f"  {key:28} {value}")
    pathlib.Path(__file__).parent.joinpath("scorecard.json").write_text(
        json.dumps(board, indent=2) + "\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
