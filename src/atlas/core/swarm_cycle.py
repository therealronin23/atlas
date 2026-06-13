"""
Capa 3 — Ciclo de mantenimiento del enjambre (ADR-045/046/048).

`SwarmCycle` cablea UN worker de mantenimiento en un ciclo completo:
  scout → tareas → coordinador → reconciler → propuestas ColdUpdate

Disciplinas de seguridad implementadas:
- F7 (anti-acumulación): si hay >= cap_open propuestas swarm abiertas, el
  ciclo no propone nada nuevo (exacta lección de los 365 worktrees huérfanos).
- F6 (dedup durable): cada propuesta nueva recibe en su evidence la firma de
  la tarea; en el siguiente ciclo el scout la reconoce como abierta y la omite.
- F4 (anclar a HEAD): el file_provider de producción lee blobs commiteados, no
  el disco vivo (que puede tener cambios sin commitear que rompan el diff).

Todo inyectable: en tests se reemplazan manager, merkle, file_provider y
make_worker por fakes — sin git real, sin red, sin suite.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from atlas.core.deterministic_producer import DEFAULT_TRANSFORMS, Transform
from atlas.core.git_env import clean_git_env
from atlas.core.maintenance_scout import RepoMaintenanceScout
from atlas.core.maintenance_worker import build_maintenance_producer, maintenance_produce_diff
from atlas.core.swarm import Blackboard, Envelope, SwarmCoordinator
from atlas.core.swarm_backend import WorktreeManager, WorktreeWorker
from atlas.core.swarm_reconcile import ColdUpdateReconciler
from atlas.core.swarm_validate import worktree_validate
from atlas.core.verify import CostTier, UnifiedDiffVerifier, UniversalVerifier

# Solo strip_trailing_whitespace para el primer slice (los transforms de
# newline/EOF producen diffs que `git apply` puede rechazar por falta del
# marcador "\ No newline at end of file").
_DEFAULT_TRANSFORMS: tuple[Transform, ...] = tuple(
    t for t in DEFAULT_TRANSFORMS if t.name == "strip_trailing_whitespace"
)

# Estados de propuesta swarm que cuentan como "abiertas" (anti-acumulación).
_OPEN_STATUSES = frozenset({"proposed", "validated", "approved"})


def head_file_provider(
    root: Path,
    *,
    subdirs: tuple[str, ...] = ("src", "tests"),
    suffix: str = ".py",
    limit: int = 500,
) -> Callable[[], list[tuple[str, str]]]:
    """Devuelve un callable que lee ficheros commiteados en HEAD.

    Ancla a HEAD (F4): no lee el disco vivo para evitar que cambios sin
    commitear corrompan el diff que luego se aplica sobre el worktree.
    """

    def _provide() -> list[tuple[str, str]]:
        env = clean_git_env()
        # Usa -z para separar paths por NUL en vez de newline: los paths con
        # espacios se devuelven intactos (git ls-files normal los quotea con "").
        ls = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if ls.returncode != 0:
            return []

        paths: list[str] = []
        # split("\0") incluye un "" final si la salida termina en NUL → filter.
        for p in ls.stdout.split("\0"):
            p = p.strip()
            if not p:
                continue
            if not p.endswith(suffix):
                continue
            if not any(p.startswith(d + "/") or p.startswith(d + "\\") for d in subdirs):
                continue
            paths.append(p)
            if len(paths) >= limit:
                break

        results: list[tuple[str, str]] = []
        for rel_path in paths:
            show = subprocess.run(
                ["git", "show", f"HEAD:{rel_path}"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if show.returncode != 0:
                continue
            results.append((rel_path, show.stdout))

        return results

    return _provide


class SwarmCycle:
    """Ciclo de mantenimiento del enjambre: scout → worker → blackboard → reconciler.

    Parámetros
    ----------
    manager:
        ColdUpdateManager (o compatible) — crea y lista propuestas.
    merkle:
        MerkleLogger — escribe el log del ciclo.
    file_provider:
        Callable sin args que devuelve [(path, source)]. En producción usa
        `head_file_provider`; en tests, un fake.
    make_worker:
        Callable[[worker_id]] -> Worker. Si None, usa `_default_worker` que
        crea un WorktreeWorker real. Inyectable para tests.
    transforms:
        Transforms del scout/productor. Por defecto solo strip_trailing_whitespace.
    cap_open:
        Máximo de propuestas swarm abiertas antes de pausar (F7).
    max_tasks:
        Máximo de tareas por ciclo (evita ráfagas).
    domain:
        Dominio del enjambre (tag de logging y envelope).
    budget_units:
        Presupuesto por worker en unidades de CostTier.
    ttl_seconds:
        Duración del envelope por worker.
    """

    def __init__(
        self,
        *,
        manager: Any,
        merkle: Any,
        file_provider: Callable[[], Iterable[tuple[str, str]]],
        make_worker: Callable[[str], Any] | None = None,
        transforms: Iterable[Transform] = _DEFAULT_TRANSFORMS,
        cap_open: int = 20,
        max_tasks: int = 10,
        domain: str = "repo_maintenance",
        budget_units: int = 100,
        ttl_seconds: int = 3600,
        root: Path | None = None,
    ) -> None:
        self._manager = manager
        self._merkle = merkle
        self._file_provider = file_provider
        self._make_worker = make_worker
        self._transforms = tuple(transforms)
        self._cap_open = cap_open
        self._max_tasks = max_tasks
        self._domain = domain
        self._budget_units = budget_units
        self._ttl_seconds = ttl_seconds
        # root para _default_worker: de manager._root si existe, o inyectado.
        self._root: Path | None = root or getattr(manager, "_root", None)

    # ------------------------------------------------------------------
    # API pública

    def run_cycle(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Corre un ciclo completo. Devuelve dict resumen."""
        ref_now = now or datetime.now(timezone.utc)

        # Paso 1: propuestas swarm abiertas → open_signatures + cap check (F7).
        open_proposals = [
            p
            for p in self._manager.list_proposals()
            if p.origin == "swarm" and p.status in _OPEN_STATUSES
        ]
        open_signatures = frozenset(
            p.evidence.get("signature")
            for p in open_proposals
            if p.evidence.get("signature") is not None
        )
        n_open = len(open_proposals)

        if n_open >= self._cap_open:
            return {
                "skipped_for_cap": True,
                "open": n_open,
                "proposed_ids": [],
            }

        # Paso 2: escanear ficheros y obtener tareas nuevas.
        files = list(self._file_provider())
        tasks = RepoMaintenanceScout(self._transforms).scan(
            files, open_signatures=open_signatures
        )

        # Tope: max_tasks y lo que cabe hasta el cap.
        remaining_cap = self._cap_open - n_open
        tasks = tasks[: min(self._max_tasks, remaining_cap)]

        # Paso 3: construir coordinador + reconciler.
        reconciler = ColdUpdateReconciler(self._manager, risk="low", origin="swarm")
        coordinator = SwarmCoordinator(
            UniversalVerifier([UnifiedDiffVerifier()]),
            Blackboard(merkle=self._merkle),
            on_accepted=reconciler,
        )

        # Paso 4: un worker por tarea, asignar + ronda individual.
        make_worker = self._make_worker or self._default_worker
        proposed_ids: list[str] = []
        reconcile_errors: list[tuple[str, str]] = []

        for i, task in enumerate(tasks):
            worker_id = f"maint-{i}"
            worker = make_worker(worker_id)
            expires_at = (ref_now + timedelta(seconds=self._ttl_seconds)).isoformat()
            coordinator.assign(
                worker,
                Envelope(worker_id, self._domain, self._budget_units, expires_at),
            )
            round_result = coordinator.run_round({worker_id: task}, now=ref_now)

            # Propuestas nuevas emitidas en esta ronda.
            new_ids = reconciler.proposed_ids[len(proposed_ids):]
            for pid in new_ids:
                proposed_ids.append(pid)
            reconcile_errors.extend(round_result.reconcile_errors)

        # Paso 5: dedup durable F6 — adjuntar signature a cada propuesta nueva.
        # Usamos reconciler.proposals (lista de (entry, pid) SOLO para
        # propuestas emitidas con éxito) en vez de zip posicional sobre
        # blackboard.accepted(). Así, si propose() lanzó para una entry
        # intermedia, el emparejamiento firma→propuesta no se desalinea.
        for entry, pid in reconciler.proposals:
            try:
                idx = int(entry.worker_id.split("-", 1)[1])
                sig = tasks[idx].signature
            except (ValueError, IndexError):
                continue
            if sig:
                self._manager.attach_evidence(pid, {"signature": sig})

        # Paso 6: log Merkle del ciclo.
        self._merkle.log(
            action="swarm.cycle",
            agent="swarm_cycle",
            result="ok",
            risk_level="safe",
            payload={
                "scanned": len(files),
                "tasks": len(tasks),
                "proposed": proposed_ids,
                "reconcile_errors": [list(e) for e in reconcile_errors],
            },
        )

        return {
            "scanned": len(files),
            "tasks": len(tasks),
            "proposed_ids": proposed_ids,
            "skipped_for_cap": False,
            "reconcile_errors": [list(e) for e in reconcile_errors],
        }

    # ------------------------------------------------------------------
    # Worker de producción (inyectable en tests)

    def _default_worker(self, worker_id: str) -> Any:
        """Construye un WorktreeWorker real para producción."""
        if self._root is None:
            raise RuntimeError(
                "SwarmCycle necesita 'root' (o manager con _root) para construir "
                "el worker de producción. Inyecta 'make_worker' en tests."
            )
        mgr = WorktreeManager(root=self._root)
        produce = maintenance_produce_diff(build_maintenance_producer())
        return WorktreeWorker(
            worker_id,
            self._domain,
            manager=mgr,
            produce_diff=produce,
            validate=worktree_validate,
            base_ref="HEAD",
            cost=CostTier.SHAPE,
        )
