"""Tests para scripts/benchmark_workload.py (t6-workload-benchmark-harness).

Cubre SOLO parsing/agregacion pura (stats, conversion de unidades de Ollama,
analisis de cuello de botella) — nunca los workloads reales (Ollama/Playwright/
FastAPI), que son lentos y requieren el hardware/servicios presentes en la
maquina. Esos se verifican corriendo el script de verdad (ver informe de la
tarea), no en la suite de pytest.

El modulo se carga por ruta (importlib) en vez de import normal porque
scripts/ no esta pensado como paquete instalable — es el mismo patron que
otros scripts sueltos del repo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "benchmark_workload.py"
_spec = importlib.util.spec_from_file_location("benchmark_workload", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
bw = importlib.util.module_from_spec(_spec)
sys.modules["benchmark_workload"] = bw
_spec.loader.exec_module(bw)


# ---------------------------------------------------------------------------
# _stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_empty_list_reports_n_zero(self) -> None:
        assert bw._stats([]) == {"n": 0}

    def test_single_value(self) -> None:
        result = bw._stats([2.0])
        assert result["n"] == 1
        assert result["mean"] == 2.0
        assert result["median"] == 2.0
        assert result["min"] == 2.0
        assert result["max"] == 2.0
        assert result["stdev"] == 0.0

    def test_known_values(self) -> None:
        result = bw._stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result["n"] == 5
        assert result["mean"] == 3.0
        assert result["median"] == 3.0
        assert result["min"] == 1.0
        assert result["max"] == 5.0

    def test_p95_index_never_out_of_range(self) -> None:
        # Regresion: con listas pequenas, round(0.95 * (n-1)) no debe pasarse
        # del ultimo indice.
        for n in range(1, 10):
            values = list(float(i) for i in range(n))
            result = bw._stats(values)
            assert result["p95"] in values


# ---------------------------------------------------------------------------
# Conversion de unidades Ollama (ns -> s, tokens/sec)
# ---------------------------------------------------------------------------


class TestOllamaUnitConversion:
    def test_ns_to_s_none_passthrough(self) -> None:
        assert bw._ns_to_s(None) is None

    def test_ns_to_s_converts(self) -> None:
        assert bw._ns_to_s(1_000_000_000) == 1.0
        assert bw._ns_to_s(500_000_000) == 0.5

    def test_tokens_per_sec_none_when_missing_inputs(self) -> None:
        assert bw._tokens_per_sec(None, 1_000_000_000) is None
        assert bw._tokens_per_sec(10, None) is None
        assert bw._tokens_per_sec(0, 1_000_000_000) is None

    def test_tokens_per_sec_known_value(self) -> None:
        # 62 tokens en 12.343470642s (numeros reales observados en la corrida
        # de code_generation contra qwen2.5-coder:7b en esta maquina).
        result = bw._tokens_per_sec(62, 12_343_470_642)
        assert result == pytest.approx(5.02, abs=0.01)

    def test_tokens_per_sec_zero_duration_is_none(self) -> None:
        assert bw._tokens_per_sec(10, 0) is None


# ---------------------------------------------------------------------------
# analyze_bottleneck — logica pura sobre un reporte sintetico
# ---------------------------------------------------------------------------


def _base_report(**overrides) -> dict:
    report = {
        "system": {
            "gpu_name": "NVIDIA GeForce GTX 960M",
            "before": {
                "temperature_celsius": 50.0,
                "ram_free_mb": 5000,
                "operational_mode": "normal",
                "gpu_vram_used_mb": 40.0,
            },
            "after": {
                "temperature_celsius": 55.0,
                "ram_free_mb": 4800,
                "operational_mode": "normal",
                "gpu_vram_used_mb": 40.0,
            },
        },
        "workloads": {
            "classification": {
                "tokens_per_sec": {"mean": 80.0},
                "ollama_ps_after": "NAME  ID  SIZE  PROCESSOR  CONTEXT  UNTIL\nqwen2.5:0.5b  x  442 MB  100% CPU  4096  1m",
            },
            "code_generation": {
                "tokens_per_sec": {"mean": 5.5},
                "ollama_ps_after": "NAME  ID  SIZE  PROCESSOR  CONTEXT  UNTIL\nqwen2.5-coder:7b  x  4.6 GB  100% CPU  4096  1m",
            },
        },
    }
    report.update(overrides)
    return report


class TestAnalyzeBottleneck:
    def test_normal_thermal_and_ram_yields_cpu_bottleneck(self) -> None:
        report = _base_report()
        analysis = bw.analyze_bottleneck(report)
        assert analysis["gpu_offloads_llm_to_gpu"] is False
        assert "CPU" in analysis["primary_bottleneck"] or "throughput" in analysis["primary_bottleneck"]
        assert any("100% en CPU" in f for f in analysis["findings"])

    def test_normal_operational_mode_is_not_flagged_as_thermal_bottleneck(self) -> None:
        # Regresion del bug real encontrado en desarrollo: OperationalMode.value
        # es "normal" en minuscula, no "NORMAL". Comparar contra el string en
        # mayusculas hacia que CUALQUIER corrida se marcara como termica.
        report = _base_report()
        analysis = bw.analyze_bottleneck(report)
        assert analysis["primary_bottleneck"] != "termico"
        thermal_findings = [f for f in analysis["findings"] if "NO fue el cuello de botella" in f]
        assert thermal_findings, "se esperaba el finding de termico-OK cuando operational_mode == 'normal'"

    def test_degraded_mode_after_is_flagged_as_thermal_bottleneck(self) -> None:
        report = _base_report()
        report["system"]["after"]["operational_mode"] = "degraded"
        analysis = bw.analyze_bottleneck(report)
        assert analysis["primary_bottleneck"] == "termico"

    def test_low_ram_after_is_flagged_as_ram_bottleneck(self) -> None:
        report = _base_report()
        report["system"]["after"]["ram_free_mb"] = 512
        analysis = bw.analyze_bottleneck(report)
        assert analysis["primary_bottleneck"] == "RAM"

    def test_gpu_offload_detected_when_ollama_ps_shows_gpu(self) -> None:
        report = _base_report()
        report["workloads"]["classification"]["ollama_ps_after"] = (
            "NAME  ID  SIZE  PROCESSOR  CONTEXT  UNTIL\nqwen2.5:0.5b  x  442 MB  100% GPU  4096  1m"
        )
        analysis = bw.analyze_bottleneck(report)
        assert analysis["gpu_offloads_llm_to_gpu"] is True

    def test_findings_include_setup_complexity_note(self) -> None:
        report = _base_report()
        analysis = bw.analyze_bottleneck(report)
        assert any("CUDA_VISIBLE_DEVICES" in f for f in analysis["findings"])


# ---------------------------------------------------------------------------
# collect_meta — sanity basica, sin red
# ---------------------------------------------------------------------------


class TestCollectMeta:
    def test_returns_expected_keys(self) -> None:
        meta = bw.collect_meta()
        for key in ("generated_at", "script_version", "hostname", "platform", "cpu_count", "ram_total_mb"):
            assert key in meta

    def test_script_version_matches_constant(self) -> None:
        meta = bw.collect_meta()
        assert meta["script_version"] == bw.SCRIPT_VERSION
