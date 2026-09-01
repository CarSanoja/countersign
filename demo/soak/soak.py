"""COUNTERSIGN's soak: the corpus, repeatedly, with the false positive rate first.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/soak/soak.py --passes 3 --wait 60 --yes

Six invoices measured twice say whether a verdict reproduces. They say nothing
about the number that decides whether a control is still switched on a fortnight
after it ships, which is how often it stops an invoice that was fine. So this
set is sixteen legitimate invoices to four fraudulent ones, the passes are
separated in time, and the report names every legitimate expediente that was
stopped instead of averaging it away.

Nothing here is unbounded. The number of passes is an argument with no default,
the estimate is printed before the first provider is touched, and a plan that
would outspend the SerpApi quota is refused rather than started.
"""

import argparse
import asyncio
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import budget  # noqa: E402
import report  # noqa: E402
from corpus import CASES, FRAUDULENT, LEGITIMATE  # noqa: E402
from documents import ensure_corpus  # noqa: E402
from runner import run_soak  # noqa: E402

from identity import IdentityBudget  # noqa: E402

MAX_PASSES = 20
DEFAULT_SERPAPI_CAP = 36


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COUNTERSIGN soak test bench")
    parser.add_argument(
        "--passes",
        type=int,
        required=True,
        help=f"how many times to run the whole corpus; 1 to {MAX_PASSES}, no default",
    )
    parser.add_argument("--wait", type=float, default=60.0, help="seconds between passes")
    parser.add_argument("--concurrency", type=int, default=1, help="runs in flight per pass")
    parser.add_argument(
        "--serpapi-cap",
        type=int,
        default=DEFAULT_SERPAPI_CAP,
        help="hard ceiling on SerpApi searches for the whole soak",
    )
    parser.add_argument("--cases", default="", help="comma-separated case ids, for a smoke run")
    parser.add_argument(
        "--persist-audit", action="store_true", help="write every gate decision to Xano"
    )
    parser.add_argument("--force-render", action="store_true", help="re-render every PDF")
    parser.add_argument("--render-only", action="store_true", help="build the corpus and stop")
    parser.add_argument("--yes", action="store_true", help="accept the printed estimate")
    return parser.parse_args(argv)


def _selected(names: str) -> tuple:
    if not names.strip():
        return CASES
    wanted = {name.strip() for name in names.split(",") if name.strip()}
    chosen = tuple(case for case in CASES if case.case_id in wanted)
    missing = wanted - {case.case_id for case in chosen}
    if missing:
        raise SystemExit(f"no such case(s): {sorted(missing)}")
    return chosen


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _print_plan(plan: dict, prices: dict, cap: int) -> None:
    print("=== PRESUPUESTO ESTIMADO ===")
    for line in budget.lines(plan, prices, cap):
        print(f"  {line}")
    print("\n  contrapartes que se buscaran en SerpApi:")
    for line in budget.counterparty_lines():
        print(f"    {line}")


def _context(args: argparse.Namespace, plan: dict, prices: dict, state: IdentityBudget) -> dict:
    return {
        "passes": args.passes,
        "wait_seconds": args.wait,
        "concurrency": args.concurrency,
        "corpus": {
            "cases": len(CASES),
            "legitimate": len(LEGITIMATE),
            "fraudulent": len(FRAUDULENT),
        },
        "audit_sink": "xano" if args.persist_audit else "memory",
        "reuse_disabled": True,
        "closed_seams": ["generation", "delivery"],
        "serpapi_cap": args.serpapi_cap,
        "serpapi_spent": state.spent,
        "serpapi_live_verifications": state.live_verifications,
        "serpapi_memo_hits": state.memo_hits,
        "estimate": plan,
        "prices": prices,
        "git_head": _git_head(),
    }


async def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not 1 <= args.passes <= MAX_PASSES:
        print(f"--passes must be between 1 and {MAX_PASSES}")
        return 2
    cases = _selected(args.cases)
    prices = await budget.measured_prices()
    plan = budget.projection(cases, args.passes, prices)
    _print_plan(plan, prices, args.serpapi_cap)
    refusals = budget.blockers(plan, prices, args.serpapi_cap)
    if refusals:
        print("\nEl soak no arranca:")
        for reason in refusals:
            print(f"  - {reason}")
        return 3
    if not args.yes:
        print("\nAnade --yes para aceptar este presupuesto y arrancar.")
        return 1

    print("\n=== CORPUS ===", flush=True)
    failures = await ensure_corpus(cases, force=args.force_render)
    for failure in failures:
        print(f"  no se pudo renderizar {failure}")
    if failures:
        return 4
    print(f"  {len(cases)} facturas listas en demo/soak/pdfs", flush=True)
    if args.render_only:
        return 0

    state = IdentityBudget(args.serpapi_cap)
    print("\n=== PASADAS ===", flush=True)
    observations = await run_soak(
        cases,
        passes=args.passes,
        wait_seconds=args.wait,
        budget=state,
        persist_audit=args.persist_audit,
        concurrency=args.concurrency,
        on_run=report.progress,
    )
    board = report.assemble(observations, _context(args, plan, prices, state))
    report.print_cases(board)
    report.print_scorecard(board)
    report.print_findings(board)
    print(f"\ninforme en {report.write(board)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
