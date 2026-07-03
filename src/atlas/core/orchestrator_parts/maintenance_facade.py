"""Cluster de auto-mantenimiento — extraído del god-object ``Orchestrator`` (ADR-039).

Agrupa los métodos de factory/acceso perezoso de las piezas de auto-mantenimiento:
scout, adopter, registry scout, dep scout/proposer, community scout, codegen proposer
y el scheduler que los compone. Todos son **read-only de creación**: instancian una
vez y devuelven el mismo objeto; la lógica vive en los módulos self_maintenance/*.

Inyección: ``MaintenanceFacade(orch)`` guarda ``self._orch`` y lee los colaboradores
del Orchestrator en tiempo de llamada (mismo patrón que ``AgenticExecutor``). El
import de ``Orchestrator`` se hace bajo ``TYPE_CHECKING`` para evitar ciclos.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.core.contracts import EventType

if TYPE_CHECKING:
    from atlas.core.orchestrator import Orchestrator

# Cota del cuerpo descargado (mismo criterio que SecureExecutor: no leer
# respuestas ilimitadas aunque la URL esté en la allowlist).
_EGRESS_MAX_BYTES = 5 * 1024 * 1024


def _build_avoid_section(recaller: Any, store: Any, query: str) -> str:
    """Construye la sección '## Patrones a evitar' para el prompt de codegen.

    Recupera hasta 3 lecciones relevantes del store via el recaller y concatena
    sus avoid_patterns. Devuelve cadena vacía si no hay lecciones que superen
    el threshold del recaller o si el recaller/store son None."""
    if recaller is None or store is None:
        return ""
    recaller.index()
    results = recaller.recall_all(query, k=3)
    if not results:
        return ""
    patterns = "\n".join(
        f"- {lesson.avoid_pattern}"
        for r in results
        if r.matched and (lesson := store.get(r.lesson_id)) is not None
    )
    if not patterns:
        return ""
    return f"\n\n## Patrones a evitar (lecciones del sistema)\n{patterns}"


def _egress_fetch_text(url: str, *, timeout: float = 15.0) -> str:
    """Descarga el cuerpo de una URL ya autorizada por el bridge (stdlib).

    El gateo de egress lo hace el llamador vía ``SSRFBridge.check`` antes de
    invocar esto; aquí solo se hace el GET HTTP, acotando el tamaño leído."""
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — gateado por SSRFBridge
        raw: bytes = resp.read(_EGRESS_MAX_BYTES)
    return raw.decode("utf-8", errors="replace")


class MaintenanceFacade:
    """Factory perezosa de todas las piezas de auto-mantenimiento (ADR-039).

    El Orchestrator instancia este facade en ``_init_components`` y delega cada
    método público ``maintenance_*`` a él. El facade lee los colaboradores del
    Orchestrator (``_merkle``, ``_ssrf_bridge``, …) en tiempo de llamada, no en
    el constructor — igual que ``AgenticExecutor`` — para preservar paridad con
    los tests que sustituyen esos atributos después de construir el Orchestrator.
    """

    def __init__(self, orch: "Orchestrator") -> None:
        self._orch = orch

        # Estado perezoso — se inicializa aquí, no en orchestrator._init_components
        self._maintenance_scout: Any = None
        self._maintenance_adopter: Any = None
        self._maintenance_registry_scout: Any = None
        self._maintenance_scheduler: Any = None
        self._maintenance_dep_scout: Any = None
        self._maintenance_dep_proposer: Any = None
        self._maintenance_codegen_proposer: Any = None
        self._maintenance_community_scout: Any = None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _project_root() -> Path:
        return Path(
            os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
        ).expanduser().resolve()

    # ------------------------------------------------------------------
    # Métodos públicos — mirrors exactos de los métodos del Orchestrator
    # ------------------------------------------------------------------

    def maintenance_scout(self) -> Any:
        """ADR-039 slice 1 — Scout read-only de salud/deuda (no muta, no propone).

        Cableado a las primitivas read-only existentes (``health_report``,
        ``GitReadTools``, ``ErrorRegistry``). ``survey()`` devuelve un informe
        estructurado auditado en Merkle. El front-half del agente de
        auto-mantenimiento; Analyst/Proposer entran en slices posteriores."""
        if self._maintenance_scout is None:
            from atlas.core.self_maintenance import MaintenanceScout

            orch = self._orch
            self._maintenance_scout = MaintenanceScout(
                merkle=orch._merkle,
                health_provider=orch.health_report,
                git_status_provider=orch._run_git_status,
                failure_provider=orch._error_registry.all,
            )
        return self._maintenance_scout

    def maintenance_adopter(self) -> Any:
        """ADR-039 slice 3 — wire propuesta → ``add_server`` (reuso puro del seam).

        Traduce una ``McpProposal`` corroborada (slice 2) en una adopción real
        vía ``adopt_mcp_server``, que consulta el decisor (ADR-040). El adopter
        no decide: bajo ``HumanDecider`` el seam exige aprobación humana y nada
        se adopta; bajo autónomo/híbrido con la intención anclada, adopta y
        registra el undo reversible (``remove_server``)."""
        if self._maintenance_adopter is None:
            from atlas.core.self_maintenance import MaintenanceAdopter

            self._maintenance_adopter = MaintenanceAdopter(
                adopt=self._orch.adopt_mcp_server,
                merkle=self._orch._merkle,
            )
        return self._maintenance_adopter

    def maintenance_registry_scout(self) -> Any:
        """ADR-039 slice 1 (literal) — Scout externo autoritativo (read-only).

        Descubre candidatos de server MCP en el registro MCP oficial. Gatea el
        egress por ``SSRFBridge`` y transporta la prosa de cada entrada como
        ``Source`` no confiable (la digiere el Analyst, no el Scout). No muta ni
        propone: emite ``McpCandidate`` etiquetados como autoritativos para el
        gate de corroboración (slice 2)."""
        if self._maintenance_registry_scout is None:
            from atlas.core.self_maintenance import RegistryScout

            self._maintenance_registry_scout = RegistryScout(
                merkle=self._orch._merkle,
                bridge=self._orch._ssrf_bridge,
                fetch=_egress_fetch_text,
            )
        return self._maintenance_registry_scout

    def maintenance_scheduler(self) -> Any:
        """ADR-039 slice 4 — Scheduler cron del front-half. Cierra el lazo vía el decisor.

        Ata las piezas ya existentes: descubre con el ``RegistryScout``
        autoritativo, analiza con el ``MaintenanceAnalyst`` (dual-LLM + gate de
        corroboración) y, por cada propuesta corroborada, (1) la surfa publicando
        ``MAINTENANCE_PROPOSED`` en el bus y (2) la enruta al ``MaintenanceAdopter``.

        El cron no decide ni aplica por sí mismo: la adopción pasa SIEMPRE por
        ``adopt_mcp_server`` → seam del decisor (ADR-040). Bajo ``HumanDecider``
        (default) el seam devuelve "requiere aprobación humana" y nada se adopta
        — paridad exacta con el HITL de hoy, surfado por el evento. Bajo
        autónomo/híbrido con la intención anclada, adopta en caliente y registra
        el undo reversible. Esto es human-ON-the-loop: el punto de decisión es el
        decisor intercambiable, no un botón hardcodeado."""
        if self._maintenance_scheduler is None:
            from atlas.core.inference_hub import InferenceHub
            from atlas.core.self_maintenance import (
                MaintenanceAnalyst,
                MaintenanceScheduler,
                McpProposal,
            )

            orch = self._orch
            hub = orch._inference_hub or InferenceHub(mode="auto")
            analyst = MaintenanceAnalyst(merkle=orch._merkle, hub=hub)

            def _notify(proposals: list[McpProposal]) -> None:
                orch._bus.publish_type(
                    EventType.MAINTENANCE_PROPOSED,
                    {
                        "proposal_ids": [p.id for p in proposals],
                        "capabilities": [p.capability for p in proposals],
                        "count": len(proposals),
                    },
                )
                # Cierre del lazo: cada propuesta pasa por el seam del decisor.
                adopter = self._orch.maintenance_adopter()
                for proposal in proposals:
                    adopter.adopt(proposal)

            def _dep_cycle() -> None:
                # Rama de auto-actualización de deps.
                # Se enruta por self._orch para que los monkeypatches sobre
                # Orchestrator (e.g. _no_real_dep_scout en conftest) sean
                # respetados en tests (ADR-039 fix regresión).
                scout = self._orch.maintenance_dep_scout()
                proposer = self._orch.maintenance_dep_proposer()
                for cand in scout.discover() or []:
                    proposal = proposer.propose_bump(cand)
                    if proposal is not None:
                        orch.advance_cold_update(proposal.id)

            self._maintenance_scheduler = MaintenanceScheduler(
                merkle=orch._merkle,
                discover=self._orch.maintenance_registry_scout().discover,
                analyze=analyst.analyze,
                notify=_notify,
                extra_cycles=(_dep_cycle,),
            )
        return self._maintenance_scheduler

    def maintenance_dep_scout(self) -> Any:
        """ADR-039 slice 6 — Scout de bumps de dependencias PyPI (read-only).

        Lee los pisos de ``[project.dependencies]`` del ``pyproject`` y consulta
        PyPI (autoritativo, egress gateado) por la última estable. No muta:
        emite ``DepCandidate``; la materialización del patch es del proposer."""
        if self._maintenance_dep_scout is None:
            from atlas.core.self_maintenance import DepScout

            self._maintenance_dep_scout = DepScout(
                merkle=self._orch._merkle,
                bridge=self._orch._ssrf_bridge,
                fetch=_egress_fetch_text,
                deps_provider=self._orch._pyproject_dep_floors,
            )
        return self._maintenance_dep_scout

    def maintenance_dep_proposer(self) -> Any:
        """ADR-039 slice 6 — Materializa un bump como patch revisable de ColdUpdate.

        Construye el diff del bump y lo entrega a ``ColdUpdateManager.propose``
        con ``origin="self_audit"``. Nunca aplica: ColdUpdate valida en worktree
        y la adopción exige el seam del decisor (ADR-040)."""
        if self._maintenance_dep_proposer is None:
            from atlas.core.self_maintenance import DepProposer

            self._maintenance_dep_proposer = DepProposer(
                merkle=self._orch._merkle,
                propose=self._orch.cold_update().propose,
                pyproject_path=self._project_root() / "pyproject.toml",
            )
        return self._maintenance_dep_proposer

    def maintenance_community_scout(self) -> Any:
        """ADR-039 slice 5 — Scout community (foros) con corroboración obligatoria.

        El foro solo *surge* nombres candidatos; cada uno se contrasta contra el
        registro MCP oficial (autoritativo). Sin respaldo autoritativo se descarta
        (fail-closed): un candidato solo-foro nunca se propone. Los campos salen
        del candidato autoritativo; la prosa del foro viaja como ``Source``
        community no confiable."""
        if self._maintenance_community_scout is None:
            from atlas.core.self_maintenance import CommunityScout, McpCandidate

            index: dict[str, McpCandidate] = {}
            built = [False]

            def _lookup(name: str) -> "McpCandidate | None":
                if not built[0]:
                    for c in self._orch.maintenance_registry_scout().discover():
                        index[c.name] = c
                    built[0] = True
                if name in index:
                    return index[name]
                # Coincidencia laxa: el foro suele citar el nombre corto del paquete.
                for cname, cand in index.items():
                    if cname.endswith("/" + name) or name in cname.split("/"):
                        return cand
                return None

            self._maintenance_community_scout = CommunityScout(
                merkle=self._orch._merkle,
                bridge=self._orch._ssrf_bridge,
                fetch=_egress_fetch_text,
                forum_urls=[
                    "https://hn.algolia.com/api/v1/search?query=mcp%20server&tags=story",
                ],
                authoritative_lookup=_lookup,
            )
        return self._maintenance_community_scout

    def maintenance_codegen_proposer(self) -> Any:
        """ADR-039 slice 7 — Codegen como patch dirigido (revisable, nunca apply solo).

        El humano apunta el objetivo (``CodegenTarget``); el LLM de control genera
        un diff; el proposer impone que solo toque el fichero apuntado y lo entrega
        a ColdUpdate con ``origin="self_audit"``. Coherente con ADR-025: la
        generación es libre, la aplicación nunca es autónoma."""
        if self._maintenance_codegen_proposer is None:
            from atlas.core.inference_hub import InferenceHub, InferenceLevel
            from atlas.core.self_maintenance import CodegenProposer, CodegenTarget
            from atlas.core.verify import ArtifactKind, UnifiedDiffVerifier, UniversalVerifier
            from atlas.router.cascade import CascadeRouter, Difficulty, InferenceProducer, TaskSpec

            orch = self._orch
            hub = orch._inference_hub or InferenceHub(mode="auto")
            # Capa 2 (ADR-042): L0 local primero, escalada a L1 si el diff no
            # verifica. FRONTIER queda preparado: cuando exista un provider L2
            # es añadir un rung aquí. El path conversacional (CLAIM) NO se
            # cablea: sin verificador más barato que el modelo, la cascada
            # solo diría UNKNOWN — sería teatro de verificación.
            cascade = CascadeRouter(
                UniversalVerifier([UnifiedDiffVerifier()]),
                [
                    InferenceProducer(
                        hub, level=InferenceLevel.L0,
                        capability=Difficulty.HARD, temperature=0.0,
                    ),
                    InferenceProducer(
                        hub, level=InferenceLevel.L1,
                        capability=Difficulty.HARD, temperature=0.0,
                    ),
                ],
            )

            # Cargar LessonStore para inyección blanda de avoid_patterns.
            #
            # 2026-07-03: unificado a <repo_root>/workspace/lessons — la MISMA
            # convención que AtlasCoder/ToolCoder (src/atlas/core/atlas_coder.py,
            # tool_coder.py), donde YA viven las lecciones reales generadas por
            # el propio motor de codificación. Antes apuntaba a
            # `orch._workspace / "memory" / "lessons"` (~/atlas/memory/lessons,
            # runtime workspace) — una ruta que ni siquiera existía, así que el
            # self-audit del Orchestrator nunca veía las lecciones reales que el
            # propio Atlas ya había generado (hallazgo real, verificado en vivo).
            try:
                from atlas.core.lesson_store import LessonStore
                from atlas.immunity.lesson_recaller import LessonRecaller
                from atlas.memory.embeddings import default_embedder

                _repo_root = orch._repo_root() or orch._workspace
                _lesson_store = LessonStore(_repo_root / "workspace" / "lessons")
                # threshold: sin override — el default de LessonRecaller (0.8) ya
                # está calibrado para embeddings SEMÁNTICOS (ver su docstring);
                # el 0.65 anterior compensaba el hash NO-semántico de
                # StubEmbedder(dim=64) que se acaba de dejar de usar aquí.
                _lesson_recaller: Any = LessonRecaller(
                    _lesson_store,
                    embedder=default_embedder(),
                )
            except Exception:  # noqa: BLE001 — directorio no existe u otro error; degradado
                _lesson_store = None
                _lesson_recaller = None

            def _generate(target: CodegenTarget) -> str:
                avoid_section = _build_avoid_section(
                    _lesson_recaller,
                    _lesson_store,
                    f"{target.goal} {target.path}",
                )
                prompt = (
                    "Genera SOLO un diff unificado (git apply) que logre el objetivo, "
                    f"tocando únicamente el fichero {target.path}. No expliques.\n\n"
                    f"Objetivo: {target.goal}\n"
                    f"{avoid_section}"
                )
                result = cascade.route(TaskSpec(
                    intent=prompt,
                    kind=ArtifactKind.PATCH,
                    metadata={
                        "context": target.context,
                        "task_id": "codegen.patch",
                        "allowed_paths": [target.path],
                    },
                ))
                orch._merkle.log(
                    action="cascade.route",
                    agent="codegen_cascade",
                    result="success" if result.verified else "failure",
                    risk_level="safe",
                    payload=result.to_dict(),
                    task_id="codegen.patch",
                )
                if not (result.verified and result.artifact is not None):
                    return ""
                return str(result.artifact.payload.get("diff", ""))

            self._maintenance_codegen_proposer = CodegenProposer(
                merkle=orch._merkle,
                generate=_generate,
                propose=orch.cold_update().propose,
            )
        return self._maintenance_codegen_proposer
