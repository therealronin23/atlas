"""
Atlas Core — BenchmarkGate: puerta de "razonamiento no roto" (no de velocidad).

Compara el recall de memoria (LongMemEval_S, medido por scripts/eval_longmemeval.py,
que no se modifica aquí, solo se invoca como subprocess) entre un estado "before"
y un estado "after" del repo — típicamente dos worktrees o commits distintos — para
detectar si un cambio propuesto degrada la calidad de recuperación de memoria.

No mide velocidad ni tiempo de ejecución: la métrica es recall@k por modo de
retrieval, agregada como el promedio de la clave "overall" del JSON que escribe
eval_longmemeval.py con --json-out (ver estructura en run_evaluation() de ese
script: {"overall": {modo: recall_at_k, ...}, "per_type": ..., ...}).
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

__all__ = ["BenchmarkGate", "BenchmarkResult"]

# Firma del runner inyectable: mismo shape que subprocess.run con los kwargs
# que BenchmarkGate necesita (cwd, capture_output, text, check).
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

_STDERR_TAIL_CHARS = 2000  # recorte razonable para no inflar `reason` con logs largos.


@dataclasses.dataclass
class BenchmarkResult:
    ran: bool
    before_score: float | None
    after_score: float | None
    metric_name: str
    no_regression: bool
    reason: str
    # Tri-estado explícito para el caso "dataset ausente": distinto de un
    # fallo real (subprocess roto, JSON inesperado). ran/no_regression se
    # mantienen fail-closed (False) igual — `skipped` es señal adicional
    # para que el llamador (cold_update_batcher) sepa que no hubo intento
    # real de correr el benchmark, no que corrió y falló.
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class BenchmarkGate:
    """Corre scripts/eval_longmemeval.py antes/después y decide no_regression.

    FAIL-CLOSED: cualquier fallo (dataset ausente, subprocess con
    returncode != 0, JSON inesperado) produce ran=False, no_regression=False —
    nunca se asume que un benchmark que no pudo correr "pasa". El caso
    "dataset ausente" además marca BenchmarkResult.skipped=True (con la razón
    apuntando a `python scripts/fetch_longmemeval.py`) para distinguirlo de
    un fallo real de ejecución — sigue sin bloquear el lote (ver
    cold_update_batcher.py), solo cambia qué dice la señal persistida.
    """

    # Nombre de la métrica principal: promedio de "overall" (uno por modo de
    # retrieval evaluado). eval_longmemeval.py con --mode all corre varios
    # modos (cosine/hybrid/temporal/...); promediarlos da un único escalar
    # comparable aunque el set de modos cambie entre runs.
    _METRIC_NAME = "overall_recall_mean"

    def __init__(
        self,
        *,
        repo_root: Path,
        data_path: Path | None = None,
        sample_n: int = 50,
        # tolerance=0.02 (2%): con sample_n=50 el ruido de muestreo entre dos
        # runs del MISMO código puede mover el recall unos puntos porcentuales
        # por azar (qué preguntas caen en la muestra aleatoria). Exigir
        # after_score >= before_score estrictamente descartaría lotes buenos
        # solo por mala suerte de muestreo, no por regresión real.
        tolerance: float = 0.02,
        python_executable: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._data_path = data_path or (repo_root / "data/longmemeval/longmemeval_s_cleaned.json")
        self._sample_n = sample_n
        self._tolerance = tolerance
        self._python = python_executable or sys.executable
        self._runner: Runner = runner or subprocess.run

    def compare(self, *, before_root: Path, after_root: Path) -> BenchmarkResult:
        if not self._data_path.exists():
            return BenchmarkResult(
                ran=False,
                before_score=None,
                after_score=None,
                metric_name="",
                no_regression=False,
                skipped=True,
                reason=(
                    f"dataset ausente: {self._data_path} — benchmark saltado (no bloquea "
                    "el lote), pero tampoco se asume que pasa. Descárgalo con: "
                    "python scripts/fetch_longmemeval.py"
                ),
            )

        with tempfile.TemporaryDirectory() as tmp:
            before_json = Path(tmp) / "before.json"
            after_json = Path(tmp) / "after.json"

            before_score, before_err = self._run_eval(cwd=before_root, json_out=before_json)
            if before_score is None:
                return BenchmarkResult(
                    ran=False,
                    before_score=None,
                    after_score=None,
                    metric_name="",
                    no_regression=False,
                    reason=f"eval_longmemeval.py falló en before_root ({before_root}): {before_err}",
                )

            after_score, after_err = self._run_eval(cwd=after_root, json_out=after_json)
            if after_score is None:
                return BenchmarkResult(
                    ran=False,
                    before_score=None,
                    after_score=None,
                    metric_name="",
                    no_regression=False,
                    reason=f"eval_longmemeval.py falló en after_root ({after_root}): {after_err}",
                )

        no_regression = after_score >= before_score - self._tolerance
        verdict = "sin regresión" if no_regression else "REGRESIÓN"
        reason = (
            f"{verdict}: {self._METRIC_NAME} before={before_score:.4f} "
            f"after={after_score:.4f} (tolerancia={self._tolerance})"
        )
        return BenchmarkResult(
            ran=True,
            before_score=before_score,
            after_score=after_score,
            metric_name=self._METRIC_NAME,
            no_regression=no_regression,
            reason=reason,
        )

    def _run_eval(self, *, cwd: Path, json_out: Path) -> tuple[float, None] | tuple[None, str]:
        """Invoca scripts/eval_longmemeval.py como subprocess y extrae la
        métrica principal del JSON escrito. Devuelve (score, None) en éxito
        o (None, motivo) en fallo."""
        cmd = [
            self._python,
            "scripts/eval_longmemeval.py",
            "--data", str(self._data_path),
            "--n", str(self._sample_n),
            "--mode", "all",
            "--seed", "42",
            "--json-out", str(json_out),
        ]
        try:
            result = self._runner(
                cmd, cwd=str(cwd), capture_output=True, text=True, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"excepción al lanzar subprocess: {exc}"

        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-_STDERR_TAIL_CHARS:]
            return None, f"returncode={result.returncode} stderr={stderr_tail!r}"

        try:
            data = json.loads(json_out.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"no se pudo leer/parsear {json_out}: {exc}"

        overall = data.get("overall")
        if not overall:
            return None, f"JSON de eval_longmemeval.py sin clave 'overall' válida: {data!r}"

        score = sum(overall.values()) / len(overall)
        return score, None
