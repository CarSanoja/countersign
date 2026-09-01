"""The soak report: the table a person reads and the file a script reads.

The case table comes first and the rates come second, deliberately. A false
positive rate is a summary of specific invoices that were wrongly stopped, and
the only useful version of that number is the one you can read the names off.
"""

import json
import pathlib
from typing import Any

from metrics import case_table, detection_rows, false_positive_rows, stability_rows
from resources import boundary_rows, cost_rows, latency_rows, provider_rows
from runner import Observation

REPORT_PATH = pathlib.Path(__file__).resolve().parent / "report.json"
LEVEL_WIDTH = 6


def assemble(observations: list[Observation], context: dict[str, Any]) -> dict[str, Any]:
    """Everything the soak measured, in the order it should be read."""
    return {
        "context": context,
        "false_positives": false_positive_rows(observations),
        "detection": detection_rows(observations),
        "stability": stability_rows(observations),
        "latency": latency_rows(observations),
        "providers": provider_rows(observations),
        "cost": cost_rows(observations),
        "boundary": boundary_rows(observations),
        "cases": case_table(observations),
        "runs": [vars(observation) for observation in observations],
    }


def _levels(row: dict[str, Any]) -> str:
    return " ".join(
        str(level or "none")[:LEVEL_WIDTH].ljust(LEVEL_WIDTH) for level in row["levels"]
    )


def print_cases(board: dict[str, Any]) -> None:
    """Every invoice, its truth, and the verdict each pass gave it."""
    print(f"\n{'caso':32} {'verdad':11} {'veredicto por pasada':26} {'estable':>7} {'seg p50':>8}")
    print("-" * 92)
    for row in board["cases"]:
        seconds = row["seconds"] or [0.0]
        marker = "si" if row["stable"] else "NO"
        flag = " <-- FALSO POSITIVO" if _is_false_positive(row) else ""
        print(
            f"{row['case_id']:32} {row['truth']:11} {_levels(row):26} "
            f"{marker:>7} {sorted(seconds)[len(seconds) // 2]:>8.1f}{flag}"
        )


def _is_false_positive(row: dict[str, Any]) -> bool:
    return row["truth"] == "legitimate" and any(
        level in ("review", "high") for level in row["levels"]
    )


def _print_block(title: str, body: dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    for key, value in body.items():
        rendered = json.dumps(value) if isinstance(value, (dict, list)) else value
        print(f"  {key:38} {rendered}")


def print_scorecard(board: dict[str, Any]) -> None:
    """The rates, then what they cost to produce."""
    _print_block("FALSOS POSITIVOS (la cifra que importa)", board["false_positives"])
    _print_block("DETECCION", board["detection"])
    _print_block("ESTABILIDAD ENTRE PASADAS", board["stability"])
    _print_block("LATENCIA", board["latency"])
    _print_block("PROVEEDORES Y DEGRADACION", board["providers"])
    _print_block("COSTE", board["cost"])
    _print_block("FRONTERA", board["boundary"])


def print_findings(board: dict[str, Any]) -> None:
    """The legitimate invoices this build stops, named rather than averaged away."""
    flagged = board["false_positives"]["flagged_legitimate_cases"]
    blocked = board["false_positives"]["blocked_legitimate_cases"]
    if not flagged:
        print("\nNingun expediente legitimo fue marcado.")
        return
    print("\n=== HALLAZGOS ===")
    index = {row["case_id"]: row for row in board["cases"]}
    for case_id in flagged:
        row = index[case_id]
        severity = "PAGO DETENIDO" if case_id in blocked else "revision humana"
        print(f"  {case_id} [{severity}] {row['levels']}")
        print(f"    remitente {row['sender_domain']} contra oficial {row['official_domain']}")
        print(f"    senales   {row['signals']}")
        print(f"    etapas    {row['stages']}")
        if row["errors"]:
            print(f"    errores   {row['errors']}")
        print(f"    por que   {row['why']}")


def write(board: dict[str, Any], path: pathlib.Path = REPORT_PATH) -> pathlib.Path:
    path.write_text(json.dumps(board, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def progress(observation: Observation) -> None:
    """One line per run, so a soak that takes half an hour is watchable."""
    print(
        f"  p{observation.pass_index} {observation.case_id:32} "
        f"{str(observation.level):6} {observation.seconds:6.1f}s "
        f"{'memo' if observation.identity_from_memo else 'live'}",
        flush=True,
    )


__all__ = [
    "REPORT_PATH",
    "assemble",
    "print_cases",
    "print_findings",
    "print_scorecard",
    "progress",
    "write",
]
