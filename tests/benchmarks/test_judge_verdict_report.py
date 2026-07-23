"""
tests/benchmarks/test_judge_verdict_report.py

Tests TDD para el informe del paso 3 de f2-6b (docs/backlog.yaml:
f2-6b-3-verdict-report): render(results) -> str markdown determinista (SIN
LLM) con el veredicto de la aceptación original de f2-6b: juez viable si
mejora >10% (relativo) sobre baseline en accuracy total; si no, "no
costo-eficaz".

Garantías verificadas:
  1. render() con resultados sintéticos donde el juez mejora >10% sobre
     baseline -> veredicto "viable" (y NO aparece "no costo-eficaz").
  2. render() con resultados sintéticos donde el juez mejora <=10% (incluido
     el límite exacto 10%) -> veredicto "no costo-eficaz".
  3. render() es puro: misma entrada -> misma salida exacta (sin reloj/red/
     aleatoriedad), y refleja los números reales de accuracy/n en la salida.
  4. CLI: lee el JSON de resultados (formato EvaluationResult del paso 2) y
     escribe el markdown a la ruta pedida.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.benchmarks.judge_verdict_report import render
from tests.benchmarks.judge_vs_baseline import EvaluationResult


def _result(n: int, judge_acc: float, baseline_acc: float) -> EvaluationResult:
    return {
        "n": n,
        "judge": {
            "accuracy": judge_acc,
            "by_class": {"factual": judge_acc, "personal": judge_acc},
        },
        "baseline": {
            "accuracy": baseline_acc,
            "by_class": {"factual": baseline_acc, "personal": baseline_acc},
        },
    }


class TestVerdictAboveThreshold:
    """Mejora relativa (judge_acc - baseline_acc) / baseline_acc > 0.10."""

    def test_judge_improves_far_above_threshold(self) -> None:
        # baseline 0.70, judge 0.90 -> mejora relativa = 0.20/0.70 ≈ 28.57% > 10%.
        result = _result(n=100, judge_acc=0.90, baseline_acc=0.70)
        report = render(result)
        assert "VIABLE" in report
        assert "no costo-eficaz" not in report

    def test_judge_improves_just_above_threshold(self) -> None:
        # baseline 0.50, judge 0.56 -> mejora relativa = 0.06/0.50 = 12% > 10%.
        result = _result(n=50, judge_acc=0.56, baseline_acc=0.50)
        report = render(result)
        assert "VIABLE" in report
        assert "no costo-eficaz" not in report

    def test_baseline_zero_judge_positive_is_infinite_improvement(self) -> None:
        # baseline accuracy 0.0, judge > 0.0 -> mejora "infinita", viable.
        result = _result(n=10, judge_acc=0.30, baseline_acc=0.0)
        report = render(result)
        assert "VIABLE" in report
        assert "no costo-eficaz" not in report


class TestVerdictAtOrBelowThreshold:
    def test_judge_improves_exactly_at_threshold_boundary(self) -> None:
        # baseline 0.50, judge 0.55 -> mejora relativa EXACTA = 0.05/0.50 = 10%.
        # El umbral es estrictamente ">10%", así que 10% exacto NO es viable.
        result = _result(n=50, judge_acc=0.55, baseline_acc=0.50)
        report = render(result)
        assert "no costo-eficaz" in report
        assert "VIABLE" not in report

    def test_judge_improves_below_threshold(self) -> None:
        # baseline 0.70, judge 0.75 -> mejora relativa = 0.05/0.70 ≈ 7.14% <= 10%.
        result = _result(n=100, judge_acc=0.75, baseline_acc=0.70)
        report = render(result)
        assert "no costo-eficaz" in report
        assert "VIABLE" not in report

    def test_judge_worse_than_baseline(self) -> None:
        result = _result(n=100, judge_acc=0.60, baseline_acc=0.80)
        report = render(result)
        assert "no costo-eficaz" in report
        assert "VIABLE" not in report

    def test_both_zero_no_division_by_zero(self) -> None:
        result = _result(n=10, judge_acc=0.0, baseline_acc=0.0)
        report = render(result)
        assert "no costo-eficaz" in report


class TestRenderContentAndPurity:
    def test_reflects_actual_numbers(self) -> None:
        result = _result(n=42, judge_acc=0.90, baseline_acc=0.70)
        report = render(result)
        assert "42" in report
        assert "0.90" in report or "90.0" in report or "90.00%" in report
        assert "0.70" in report or "70.0" in report or "70.00%" in report

    def test_pure_same_input_same_output(self) -> None:
        result = _result(n=20, judge_acc=0.85, baseline_acc=0.60)
        assert render(result) == render(result)

    def test_is_markdown_with_a_heading(self) -> None:
        result = _result(n=20, judge_acc=0.85, baseline_acc=0.60)
        report = render(result)
        assert report.startswith("#")


class TestCli:
    def test_cli_reads_results_writes_markdown(self, tmp_path: Path) -> None:
        results_path = tmp_path / "results.json"
        out_path = tmp_path / "verdict.md"
        results: EvaluationResult = _result(n=30, judge_acc=0.93, baseline_acc=0.70)
        results_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.benchmarks.judge_verdict_report",
                "--results",
                str(results_path),
                "--out",
                str(out_path),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "VIABLE" in content
        assert content == render(results)
