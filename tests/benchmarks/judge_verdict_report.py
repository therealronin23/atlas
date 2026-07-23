"""
tests/benchmarks/judge_verdict_report.py

Paso 3 de f2-6b (docs/backlog.yaml: f2-6b-3-verdict-report): informe
determinista (sin LLM) del veredicto de aceptación original de f2-6b —
el juez InferenceHub es viable si mejora >10% relativo sobre el baseline
léxico en accuracy total; si no, "no costo-eficaz".

render() es puro (misma entrada -> misma salida exacta). El CLI solo
adapta lectura de JSON / escritura de fichero alrededor de render().
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tests.benchmarks.judge_vs_baseline import EvaluationResult

VIABILITY_THRESHOLD = 0.10


def _relative_improvement(judge_acc: float, baseline_acc: float) -> float | None:
    """None significa "mejora infinita" (baseline=0, judge>0)."""
    if baseline_acc == 0.0:
        return None if judge_acc > 0.0 else 0.0
    return (judge_acc - baseline_acc) / baseline_acc


def render(results: EvaluationResult) -> str:
    n = results["n"]
    judge = results["judge"]
    baseline = results["baseline"]
    judge_acc = judge["accuracy"]
    baseline_acc = baseline["accuracy"]

    improvement = _relative_improvement(judge_acc, baseline_acc)
    # Redondeo a 9 decimales antes de comparar: el umbral 10% exacto debe
    # caer del lado "no viable" incluso cuando el binario de punto flotante
    # representa 0.05/0.50 como 0.10000000000000009 en vez de 0.1 exacto.
    is_viable = improvement is None or round(improvement, 9) > VIABILITY_THRESHOLD

    if improvement is None:
        improvement_str = "infinita (baseline=0.00%)"
    else:
        improvement_str = f"{improvement * 100:.2f}%"

    # "VIABLE" y "no costo-eficaz" deben ser mutuamente excluyentes como
    # substrings literales (lo exige el contrato de test) — "NO VIABLE"
    # seguiría conteniendo "VIABLE", por eso el rótulo negativo usa una
    # palabra distinta (DESCARTADO), no una negación de la palabra positiva.
    verdict = "**VIABLE**" if is_viable else "**DESCARTADO (no costo-eficaz)**"

    lines = [
        "# Veredicto f2-6b: juez InferenceHub vs baseline determinista",
        "",
        f"- n = {n}",
        f"- Accuracy juez: {judge_acc * 100:.2f}%",
        f"- Accuracy baseline: {baseline_acc * 100:.2f}%",
        f"- Mejora relativa: {improvement_str}",
        f"- Umbral de aceptación: >{VIABILITY_THRESHOLD * 100:.0f}% relativo",
        "",
        f"## Veredicto: {verdict}",
        "",
        "### Por clase",
        "",
        "| clase | judge | baseline |",
        "|---|---|---|",
    ]
    for label in sorted(judge["by_class"]):
        j = judge["by_class"][label]
        b = baseline["by_class"].get(label, 0.0)
        lines.append(f"| {label} | {j * 100:.2f}% | {b * 100:.2f}% |")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    results: EvaluationResult = json.loads(args.results.read_text(encoding="utf-8"))
    report = render(results)
    args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
