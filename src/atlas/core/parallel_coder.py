"""
Atlas Core — ParallelCoder
Dispatcher paralelo que lanza subtareas de codificación en git worktrees aislados,
una por worker (provider/key activa).

Cada worker tiene su propio worktree y su propio InferenceHub con un único provider.
"""

from __future__ import annotations

import copy
import inspect
import logging
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from atlas.core.atlas_coder import AtlasCoder, CoderResult
from atlas.core.inference_hub import DEFAULT_PROVIDERS, InferenceHub, InferenceLevel, Provider

# Fábrica del motor de codificación por worker: (hub, repo_root, timeout_s) ->
# objeto con .code(task, context_files, test_cmd, max_iterations, **kwargs).
# Default = AtlasCoder (comportamiento sin cambios). Pasar ToolCoder para usar
# el motor de tool-calling (ADR-031) en cada worker del enjambre.
CoderFactory = Callable[[InferenceHub, Path, int], Any]


def _default_coder_factory(hub: InferenceHub, repo_root: Path, timeout_s: int) -> Any:
    return AtlasCoder(hub, repo_root=repo_root, timeout_s=timeout_s)

__all__ = [
    "ParallelCoder", "ParallelCoderResult", "WorkerResult", "EnsembleResult",
    "discover_workers",
]

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    subtask: str
    provider_name: str
    coder_result: CoderResult
    worktree_path: str  # path que se usó (ya limpiado)
    # Solo poblado en modo ensemble (sync_back=False): contenido de los
    # archivos cambiados, capturado ANTES de que el worktree se destruya, para
    # poder aplicar el resultado del GANADOR después de elegirlo sin depender
    # de un worktree que ya no existe.
    captured_files: dict[str, str] | None = None


@dataclass
class EnsembleResult:
    task: str
    attempts: int
    winner: WorkerResult | None
    results: list[WorkerResult] = field(default_factory=list)


@dataclass
class ParallelCoderResult:
    subtasks_total: int
    subtasks_passed: int
    subtasks_failed: int
    results: list[WorkerResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.subtasks_failed == 0


def discover_workers(
    providers: list[Provider] | None = None,
    level: InferenceLevel = InferenceLevel.L1,
) -> list[tuple[Provider, str]]:
    """Devuelve lista de (provider, api_key) para todos los providers del nivel
    que tienen al menos una key configurada en el entorno.

    Con account_pool: una entrada por key disponible (un worker por cuenta).
    Sin account_pool: una entrada si api_key_env está en el entorno.
    Providers con api_key_env=None (Ollama): siempre incluidos con key vacía.
    """
    pool = providers if providers is not None else DEFAULT_PROVIDERS
    workers: list[tuple[Provider, str]] = []

    for provider in pool:
        if provider.level != level:
            continue

        if provider.api_key_env is None:
            # Ollama o similar — siempre disponible
            workers.append((provider, ""))
            continue

        if provider.account_pool:
            for env_var in provider.account_pool:
                val = os.environ.get(env_var)
                if val:
                    workers.append((provider, val))
        else:
            val = os.environ.get(provider.api_key_env)
            if val:
                workers.append((provider, val))

    return workers


def _hub_for_worker(provider: Provider, api_key: str) -> InferenceHub:
    """InferenceHub dedicado a un único provider/key para uso en worker paralelo.

    discover_workers ya verificó que la variable de entorno tiene valor,
    así que InferenceHub encontrará la key al construirse.
    """
    p = copy.copy(provider)
    return InferenceHub(providers=[p], mode="auto")


def _sync_worker_result_back(
    wt_path: Path, repo_root: Path, files_changed: list[str]
) -> None:
    """Sincroniza los archivos de un worker EXITOSO desde su worktree al repo
    real. Un archivo ausente en el worktree significa que se borró ahí — se
    borra también en el repo real (mismo contrato que
    AtlasCoder._sync_sandbox_back, técnica #6)."""
    for rel_path in files_changed:
        src = wt_path / rel_path
        dst = repo_root / rel_path
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            dst.unlink(missing_ok=True)


def _run_worker(
    subtask: str,
    provider: Provider,
    api_key: str,
    repo_root: Path,
    context_files: list[str],
    test_cmd: list[str],
    timeout_s: int,
    max_iterations: int,
    worker_index: int,
    coder_kwargs: dict[str, object],
    coder_factory: CoderFactory,
    level: InferenceLevel,
    sync_back: bool = True,
) -> WorkerResult:
    """Ejecuta una subtarea en un worktree aislado. Siempre limpia el worktree.

    Si el resultado es success=True, sincroniza files_changed de vuelta al
    repo real ANTES de borrar el worktree (bug corregido 2026-06-28: antes se
    descartaba TODO el trabajo, incluidos los éxitos).

    sync_back=False (modo ensemble): NO escribe al repo real — en su lugar
    captura el contenido de los archivos cambiados en memoria
    (WorkerResult.captured_files), porque varios workers pueden estar
    resolviendo la MISMA tarea en paralelo y solo el ganador debe aplicarse
    (aplicar todos causaría ediciones en conflicto no deterministas)."""
    wt_path = ""
    try:
        # Crear worktree temporal en detached HEAD (evita conflicto con rama en uso)
        with tempfile.TemporaryDirectory(prefix=f"atlas_wt_{worker_index}_") as tmpdir:
            wt_path = str(Path(tmpdir) / f"wt_{worker_index}")
            try:
                subprocess.run(
                    ["git", "worktree", "add", "--detach", wt_path, "HEAD"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                error_msg = exc.stderr.strip() if exc.stderr else str(exc)
                return WorkerResult(
                    subtask=subtask,
                    provider_name=provider.name,
                    coder_result=CoderResult(
                        success=False,
                        iterations=0,
                        files_changed=[],
                        test_output="",
                        error=f"git worktree add falló: {error_msg}",
                    ),
                    worktree_path=wt_path,
                )

            # Sincronizar src/ y tests/ desde repo_root al worktree.
            # Necesario para archivos untracked que no están en git HEAD.
            for subdir in ("src", "tests"):
                src_dir = repo_root / subdir
                dst_dir = Path(wt_path) / subdir
                if src_dir.exists():
                    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)

            try:
                hub = _hub_for_worker(provider, api_key)
                coder = coder_factory(hub, Path(wt_path), timeout_s)
                # Gap latente (2026-07-02): `level` solo alimentaba discover_
                # workers, nunca llegaba a coder.code(). Se reenvía SOLO si el
                # motor declara un parámetro `level` explícito (ToolCoder) —
                # AtlasCoder no lo tiene y no acepta **kwargs, forzarlo rompería
                # la llamada.
                call_kwargs = dict(coder_kwargs)
                code_params = inspect.signature(coder.code).parameters
                if "level" in code_params and "level" not in call_kwargs:
                    call_kwargs["level"] = level
                result = coder.code(
                    subtask, context_files, test_cmd, max_iterations, **call_kwargs,
                )
                captured_files: dict[str, str] | None = None
                if result.success:
                    if sync_back:
                        _sync_worker_result_back(
                            Path(wt_path), repo_root, result.files_changed
                        )
                    else:
                        captured_files = {}
                        for rel_path in result.files_changed:
                            src = Path(wt_path) / rel_path
                            if src.exists():
                                captured_files[rel_path] = src.read_text(encoding="utf-8")
            finally:
                # Cleanup: remover worktree aunque el worker falle
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=repo_root,
                    capture_output=True,
                )

            return WorkerResult(
                subtask=subtask,
                provider_name=provider.name,
                coder_result=result,
                worktree_path=wt_path,
                captured_files=captured_files,
            )

    except Exception as exc:  # noqa: BLE001
        logger.warning("Worker %d falló inesperadamente: %s", worker_index, exc)
        return WorkerResult(
            subtask=subtask,
            provider_name=provider.name,
            coder_result=CoderResult(
                success=False,
                iterations=0,
                files_changed=[],
                test_output="",
                error=str(exc),
            ),
            worktree_path=wt_path,
        )


class ParallelCoder:
    """
    Dispatcher paralelo: asigna subtareas a workers, cada uno en su propio
    git worktree, usando ThreadPoolExecutor.
    """

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        timeout_s: int = 120,
        providers: list[Provider] | None = None,
        coder_factory: CoderFactory | None = None,
    ) -> None:
        self._repo_root = repo_root or Path.cwd()
        self._timeout_s = timeout_s
        self._providers = providers  # None = usar DEFAULT_PROVIDERS en run()
        self._coder_factory = coder_factory or _default_coder_factory

    def run(
        self,
        subtasks: list[str],
        context_files: list[str],
        test_cmd: list[str],
        *,
        level: InferenceLevel = InferenceLevel.L1,
        max_iterations: int = 3,
        max_workers: int | None = None,
        **coder_kwargs: object,
    ) -> ParallelCoderResult:
        """
        Ejecuta subtasks en paralelo, una por worker disponible (modo enjambre).

        Parámetros
        ----------
        subtasks:
            Lista de descripciones de subtareas a codificar en paralelo.
        context_files:
            Archivos de contexto (rutas relativas al repo_root) que cada worker verá.
        test_cmd:
            Comando de tests para validar cada subtarea.
        level:
            Nivel de inferencia para descubrir workers.
        max_iterations:
            Iteraciones máximas por worker.
        max_workers:
            Límite superior de workers paralelos. None = sin límite extra.
        coder_kwargs:
            Se propaga a cada AtlasCoder.code() (edit_format, use_apply_model,
            strategy, lesson_store, lesson_recaller, repo_map_files, etc.) —
            mismo mecanismo que IncrementalCoder.run(). sandbox NO se acepta
            aquí: cada worker ya está aislado en su propio git worktree, un
            sandbox interno adicional sería redundante.
        """
        if "sandbox" in coder_kwargs:
            raise ValueError(
                "sandbox no aplica a ParallelCoder — cada worker ya está "
                "aislado en su propio git worktree."
            )
        workers = discover_workers(providers=self._providers, level=level)

        if not workers:
            # Sin workers disponibles: devolver fallo para cada subtask
            no_key_error = CoderResult(
                success=False,
                iterations=0,
                files_changed=[],
                test_output="",
                error="No hay workers disponibles (ninguna API key encontrada en el entorno).",
            )
            results = [
                WorkerResult(
                    subtask=st,
                    provider_name="(none)",
                    coder_result=no_key_error,
                    worktree_path="",
                )
                for st in subtasks
            ]
            return ParallelCoderResult(
                subtasks_total=len(subtasks),
                subtasks_passed=0,
                subtasks_failed=len(subtasks),
                results=results,
            )

        effective_workers = min(len(subtasks), len(workers), max_workers or 999)

        futures_map = {}
        all_results: list[WorkerResult] = []

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            for idx, subtask in enumerate(subtasks):
                # Asignar worker round-robin
                provider, api_key = workers[idx % len(workers)]
                future = executor.submit(
                    _run_worker,
                    subtask,
                    provider,
                    api_key,
                    self._repo_root,
                    context_files,
                    test_cmd,
                    self._timeout_s,
                    max_iterations,
                    idx,
                    coder_kwargs,
                    self._coder_factory,
                    level,
                )
                futures_map[future] = subtask

            for future in as_completed(futures_map):
                all_results.append(future.result())

        passed = sum(1 for r in all_results if r.coder_result.success)
        failed = len(all_results) - passed

        return ParallelCoderResult(
            subtasks_total=len(subtasks),
            subtasks_passed=passed,
            subtasks_failed=failed,
            results=all_results,
        )

    def run_ensemble(
        self,
        task: str,
        context_files: list[str],
        test_cmd: list[str],
        *,
        n: int = 3,
        level: InferenceLevel = InferenceLevel.L1,
        max_iterations: int = 3,
        **coder_kwargs: object,
    ) -> EnsembleResult:
        """Modo ensemble (patrón Cursor, cross-audit 2026-07-02): la MISMA
        tarea se manda a *n* workers/proveedores distintos en paralelo — el
        inverso de `run()` (que reparte subtareas DISTINTAS entre workers).
        Gana el intento exitoso con menos iteraciones (desempate: el primero
        en la lista de resultados). Solo el ganador se sincroniza al repo
        real — los demás, aunque hayan tenido éxito, se descartan sin tocar
        el repo (evita ediciones en conflicto de intentos redundantes)."""
        if "sandbox" in coder_kwargs:
            raise ValueError(
                "sandbox no aplica a ParallelCoder — cada worker ya está "
                "aislado en su propio git worktree."
            )
        workers = discover_workers(providers=self._providers, level=level)
        if not workers:
            return EnsembleResult(task=task, attempts=0, winner=None, results=[])

        futures_map = {}
        all_results: list[WorkerResult] = []

        with ThreadPoolExecutor(max_workers=n) as executor:
            for idx in range(n):
                provider, api_key = workers[idx % len(workers)]
                future = executor.submit(
                    _run_worker,
                    task,
                    provider,
                    api_key,
                    self._repo_root,
                    context_files,
                    test_cmd,
                    self._timeout_s,
                    max_iterations,
                    idx,
                    coder_kwargs,
                    self._coder_factory,
                    level,
                    False,  # sync_back — decidido tras elegir ganador
                )
                futures_map[future] = idx

            for future in as_completed(futures_map):
                all_results.append(future.result())

        winners = [r for r in all_results if r.coder_result.success]
        winner = min(winners, key=lambda r: r.coder_result.iterations, default=None)

        if winner is not None and winner.captured_files:
            for rel_path, content in winner.captured_files.items():
                dst = self._repo_root / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(content, encoding="utf-8")

        return EnsembleResult(
            task=task, attempts=len(all_results), winner=winner, results=all_results,
        )
