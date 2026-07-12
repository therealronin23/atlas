"""
Tests para BenchmarkGate (src/atlas/core/self_maintenance/benchmark_gate.py).

BenchmarkGate corre scripts/eval_longmemeval.py (SIN modificarlo) antes/después
de un cambio, y decide si hay regresión de "razonamiento" (recall de memoria),
no de velocidad. El subprocess real se reemplaza por un `runner` inyectado en
la mayoría de los tests para no depender de que el dataset LongMemEval esté
presente en cada entorno de CI.

Métrica principal: eval_longmemeval.py con --mode all escribe un JSON con
clave "overall": {modo: recall_at_k, ...} (uno por modo de retrieval). Como
BenchmarkGate no sabe de antemano cuántos modos corrieron, usa el promedio de
"overall" como métrica escalar única — así compara manzanas con manzanas
aunque cambie el set de modos evaluados.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance.benchmark_gate import BenchmarkGate, BenchmarkResult


def _fake_runner_factory(scores_by_cwd: dict[str, float], returncode: int = 0):
    """Fabrica un `runner` inyectable que escribe el JSON esperado en el
    --json-out indicado en los args, simulando lo que hace eval_longmemeval.py
    de verdad, sin ejecutarlo. Identifica before/after por el cwd pasado."""

    def _runner(cmd: list[str], *, cwd: str, capture_output: bool, text: bool, check: bool):
        if returncode != 0:
            return subprocess.CompletedProcess(
                cmd, returncode=returncode, stdout="", stderr="boom: fake failure"
            )
        # Extrae --json-out del cmd para escribir el resultado ahí.
        json_out = cmd[cmd.index("--json-out") + 1]
        score = scores_by_cwd[cwd]
        Path(json_out).write_text(
            json.dumps({"n": 5, "k": 5, "elapsed_s": 0.1, "overall": {"cosine": score}})
        )
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    return _runner


def test_dataset_ausente_falla_cerrado(tmp_path: Path) -> None:
    gate = BenchmarkGate(
        repo_root=tmp_path,
        data_path=tmp_path / "no_existe" / "dataset.json",
    )
    result = gate.compare(before_root=tmp_path, after_root=tmp_path)

    assert isinstance(result, BenchmarkResult)
    assert result.ran is False
    assert result.before_score is None
    assert result.after_score is None
    assert result.no_regression is False
    assert "dataset ausente" in result.reason


def test_dataset_ausente_es_skipped_explicito_con_razon_accionable(tmp_path: Path) -> None:
    """Tri-estado: dataset ausente != fallo real de ejecución. Sigue
    fail-closed (ran=False, no_regression=False) pero con skipped=True y una
    razón que apunta al comando concreto que lo arregla."""
    gate = BenchmarkGate(
        repo_root=tmp_path,
        data_path=tmp_path / "no_existe" / "dataset.json",
    )
    result = gate.compare(before_root=tmp_path, after_root=tmp_path)

    assert result.ran is False
    assert result.no_regression is False
    assert result.skipped is True
    assert "scripts/fetch_longmemeval.py" in result.reason


def test_fallo_subprocess_no_es_skipped(tmp_path: Path) -> None:
    """Un fallo real de ejecución (dataset SÍ presente, pero el subprocess
    revienta) no debe confundirse con el caso "dataset ausente": skipped
    debe seguir en False."""
    data_path = tmp_path / "dataset.json"
    data_path.write_text("[]")
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()

    runner = _fake_runner_factory({}, returncode=1)
    gate = BenchmarkGate(repo_root=tmp_path, data_path=data_path, runner=runner)
    result = gate.compare(before_root=before_root, after_root=after_root)

    assert result.ran is False
    assert result.skipped is False


def test_to_dict_roundtrip(tmp_path: Path) -> None:
    """Bug real: cold_update_batcher.py llama result.to_dict() y hoy no
    existe -> AttributeError tragado silenciosamente por un except Exception,
    dejando benchmark_findings en None siempre. to_dict() debe existir y
    reflejar exactamente los campos del dataclass (dataclasses.asdict)."""
    data_path = tmp_path / "dataset.json"
    data_path.write_text("[]")
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()

    runner = _fake_runner_factory({str(before_root): 0.60, str(after_root): 0.65})
    gate = BenchmarkGate(repo_root=tmp_path, data_path=data_path, runner=runner)
    result = gate.compare(before_root=before_root, after_root=after_root)

    d = result.to_dict()

    assert d == dataclasses.asdict(result)
    assert d["ran"] is True
    assert d["no_regression"] is True
    assert d["skipped"] is False
    assert d["before_score"] == pytest.approx(0.60)
    assert d["after_score"] == pytest.approx(0.65)


def test_to_dict_roundtrip_skipped(tmp_path: Path) -> None:
    gate = BenchmarkGate(
        repo_root=tmp_path,
        data_path=tmp_path / "no_existe" / "dataset.json",
    )
    result = gate.compare(before_root=tmp_path, after_root=tmp_path)

    d = result.to_dict()

    assert d == dataclasses.asdict(result)
    assert d["skipped"] is True
    assert d["ran"] is False
    assert d["no_regression"] is False
    assert "scripts/fetch_longmemeval.py" in d["reason"]


def test_after_igual_o_mejor_no_regresion(tmp_path: Path) -> None:
    data_path = tmp_path / "dataset.json"
    data_path.write_text("[]")
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()

    runner = _fake_runner_factory({str(before_root): 0.60, str(after_root): 0.70})
    gate = BenchmarkGate(repo_root=tmp_path, data_path=data_path, runner=runner)

    result = gate.compare(before_root=before_root, after_root=after_root)

    assert result.ran is True
    assert result.before_score == pytest.approx(0.60)
    assert result.after_score == pytest.approx(0.70)
    assert result.no_regression is True


def test_after_peor_fuera_de_tolerancia_regresion(tmp_path: Path) -> None:
    data_path = tmp_path / "dataset.json"
    data_path.write_text("[]")
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()

    runner = _fake_runner_factory({str(before_root): 0.80, str(after_root): 0.50})
    gate = BenchmarkGate(repo_root=tmp_path, data_path=data_path, tolerance=0.02, runner=runner)

    result = gate.compare(before_root=before_root, after_root=after_root)

    assert result.ran is True
    assert result.no_regression is False
    assert "0.5" in result.reason or "regres" in result.reason.lower()


def test_after_ligeramente_peor_dentro_tolerancia_no_regresion(tmp_path: Path) -> None:
    data_path = tmp_path / "dataset.json"
    data_path.write_text("[]")
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()

    # 0.70 -> 0.69: diferencia de 0.01, dentro de tolerance=0.02.
    runner = _fake_runner_factory({str(before_root): 0.70, str(after_root): 0.69})
    gate = BenchmarkGate(repo_root=tmp_path, data_path=data_path, tolerance=0.02, runner=runner)

    result = gate.compare(before_root=before_root, after_root=after_root)

    assert result.ran is True
    assert result.no_regression is True


def test_subprocess_falla_no_asume_pasa(tmp_path: Path) -> None:
    data_path = tmp_path / "dataset.json"
    data_path.write_text("[]")
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()

    runner = _fake_runner_factory({}, returncode=1)
    gate = BenchmarkGate(repo_root=tmp_path, data_path=data_path, runner=runner)

    result = gate.compare(before_root=before_root, after_root=after_root)

    assert result.ran is False
    assert result.no_regression is False
    assert result.before_score is None
    assert result.after_score is None
    assert "boom" in result.reason or "fake failure" in result.reason


# ---------------------------------------------------------------------------
# Integración real (opcional): solo corre si el dataset real existe en el
# repo. Usa sample_n muy pequeño para que sea rápido. No debe romper CI si el
# dataset no está — se salta explícitamente.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_DATA = _REPO_ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"


@pytest.mark.skipif(not _REAL_DATA.exists(), reason="dataset LongMemEval real no disponible")
def test_integracion_real_mismo_repo_no_regresion() -> None:
    # before == after == mismo repo real: debe correr de verdad el script y
    # no reportar regresión contra sí mismo (mismo código, mismo score).
    gate = BenchmarkGate(repo_root=_REPO_ROOT, sample_n=5)
    result = gate.compare(before_root=_REPO_ROOT, after_root=_REPO_ROOT)

    assert result.ran is True
    assert result.no_regression is True
    assert result.before_score is not None
    assert result.after_score is not None
