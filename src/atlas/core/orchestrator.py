"""
Atlas Core — Orquestador
Coordina: Governance L0 → Permission Profile → Classifier → Tools → Merkle Logger.
Decision final: Atlas decide. Todo lo demas sirve a Atlas.
"""

from __future__ import annotations

import fcntl
import logging
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

from atlas.core.contracts import (
    DelegationPayload, Event, EventType, RoutingLevel,
    Task, TaskSource, TaskStatus, Tool, ToolLevel, PermissionLevel,
    OperationalMode, ReasoningReceipt,
)
from atlas.core.event_bus import EventBus
from atlas.governance.governance_l0 import GovernanceL0
from atlas.governance.permission_profile import PermissionProfile
from atlas.hermes.hermes import (
    DelegationBuilder,
    HermesAdapter,
    HermesMockAdapter,
    HermesRestAdapter,
    OfflineQueue,
)
from atlas.logging.merkle_logger import MerkleLogger
from atlas.memory.memory_system import (
    ErrorRegistry, ApprovedPatternStore, ProviderMetricsStore, SystemContextLoader, ToolRegistry,
)
from atlas.core.gate_h import GateHManager
from atlas.core.ghost_replay import GhostReplay
from atlas.core.inference_hub import InferenceHub
from atlas.core.decider import (
    COLD_PATCH,
    MCP_SERVER,
    SNAPSHOT,
    Allow,
    DecisionAction,
    Decider,
    Deny,
    RequiresHuman,
    RevertRegistry,
    Verdict,
    action_hash,
    make_decider,
)
from atlas.core.orchestrator_parts import agentic_helpers as _ah
from atlas.core.orchestrator_parts.agentic_executor import AgenticExecutor
from atlas.core.orchestrator_parts.approvals import ApprovalManager
from atlas.core.orchestrator_parts.classifier import HybridClassifier
from atlas.mcp import McpRegistry, McpServerConfig, load_servers
from atlas.security.sentinel_gate import SentinelGate
from atlas.core.orchestrator_parts.gate_f_executor import GateFExecutor
from atlas.core.orchestrator_parts.gate_f_parser import (
    GateFCommand,
    parse_gate_f_command,
)
from atlas.core.orchestrator_parts.git_read_tools import GitReadTools
from atlas.core.orchestrator_parts.task_persistence import TaskPersistence
from atlas.core.timetravel import TimeTravel
from atlas.memory.block_memory import (
    BlockLimitExceeded,
    BlockMemory,
    BlockMemoryError,
    BlockNotFound,
)
from atlas.memory.distiller import ChunkSource, MemoryDistiller
from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.memory.vector_store import KuzuVectorStore
from atlas.router.classifier import Classifier, ClassificationResult
from atlas.router.slm_classifier import SLMClassifier
from atlas.security.ast_guard import ASTGuard
from atlas.security.capabilities import CapabilityIssuer
from atlas.security.executor import AtlasExecutor
from atlas.security.generated_code_policy import GeneratedCodePolicy
from atlas.security.pii_surrogate import PIISurrogate
from atlas.security.sandbox import LayeredIsolationSandbox, SandboxResult
from atlas.security.ssrf_bridge import SSRFBridge
from atlas import __version__


@dataclass
class AtlasStatus:
    version: str
    workspace: str
    repo_root: str | None
    governance_ok: bool
    chain_ok: bool
    tool_count: int
    queue_depth: int
    hermes_mode: str
    record_count: int
    uptime_seconds: float
    emergency_mode: bool


class Orchestrator:
    """
    Cerebro ejecutivo de Atlas Core.
    Recibe intenciones → clasifica → enruta → ejecuta → registra.
    """

    VERSION = __version__

    # Atributos opcionales declarados a nivel clase para que mypy use el tipo
    # Optional desde el principio (evita redef cuando se reasignan a None tras stop_*).
    _telegram_bot: Any
    _telegram_thread: Any
    _offline_monitor: Any
    _thermal_watchdog: Any
    _gate_f_exec: GateFExecutor
    _pending_approval_dir: Path
    _agentic_auto_approve: frozenset[str]   # ADR-033
    _agentic_suspension_ttl: float | None   # ADR-033
    _mcp: McpRegistry                       # ADR-035
    _mcp_started: bool                      # ADR-035
    _decider: Decider                       # ADR-040 — seam de decisión central
    _revert_registry: RevertRegistry        # ADR-040 slice 6 — handles de undo

    # Gate D pipeline integrado (opt-in via enable_gate_d_pipeline()).
    # Inicializados a None y poblados al activar.
    _gate_d_enabled: bool
    _distiller: Any
    _ghost_replay: Any
    _slm_classifier: Any
    _timetravel: Any
    _pii_surrogate: Any
    _inference_hub: Any  # se guarda en enable_gate_d_pipeline para que
                         # _execute_task LOCAL_SAFE pueda invocarlo.
    _gate_h: Any
    _vector_store: KuzuVectorStore | None
    _observability: Any
    _cold_update_manager: Any
    _self_audit_runner: Any
    _swarm_cycle: Any
    _knowledge_cve_proposer: Any

    # Politica del hybrid classifier:
    # - Si el rule-based devuelve confidence >= SLM_BYPASS_THRESHOLD (1.0),
    #   significa que una regla matched explicitamente: se confia y NO se
    #   invoca al SLM.
    # - Si el rule-based cae a su default LOCAL_SAFE (confidence 0.6), se
    #   consulta al SLM. El SLM gana el empate cuando identifica una ruta
    #   mas especifica que LOCAL_SAFE.
    # Governance bloqueado del rule-based SIEMPRE prevalece — la constitucion
    # no admite revision por LLM.
    SLM_BYPASS_THRESHOLD: float = 1.0

    def __init__(self, workspace: Path | None = None) -> None:
        self._workspace = workspace or self._resolve_workspace()
        self._start_time = datetime.now(timezone.utc)
        self._init_dirs()
        self._init_components()

    # ------------------------------------------------------------------
    # API publica principal
    # ------------------------------------------------------------------

    def set_decider(self, decider: Decider) -> None:
        """Sustituye el decisor central (ADR-040).

        El humano (``HumanDecider``) es la implementación por defecto. El pivote
        a autonomía es inyectar otra implementación aquí (``AutonomousDecider``,
        ``hybrid``) — no refactorizar los call-sites.
        """
        self._decider = decider

    def _consult_decider(
        self, action: DecisionAction, task: Task
    ) -> tuple[Verdict, str]:
        """Punto único de decisión (ADR-040).

        Slice 3: calcula el ``action_hash`` (ata el veredicto a la acción
        exacta, ADR-036 P2), lo pasa al decisor en el contexto y emite
        telemetría no bloqueante (D7) en cada veredicto.

        Devuelve ``(verdict, action_hash)``. El hash se hila hasta el punto de
        ejecución (slice 6): una mutación reversible que se ejecuta registra su
        handle de undo atado a este mismo hash, y ``revert(action_hash)`` lo
        consume. Los call-sites sin undo real ignoran el hash (``verdict, _``).
        """
        act_hash = action_hash(action, task.intent)
        verdict = self._decider.decide(
            action,
            sanctioned_intent=task.intent,
            context={
                "source": task.source.value,
                "task_id": task.id,
                "action_hash": act_hash,
            },
        )
        self._emit_decider_telemetry(action, task, verdict, act_hash)
        return verdict, act_hash

    def _emit_decider_telemetry(
        self, action: DecisionAction, task: Task, verdict: Verdict, act_hash: str
    ) -> None:
        """Canal on-the-loop (ADR-040 D7): nunca bloquea la decisión."""
        verdict_name = type(verdict).__name__
        try:
            self._merkle.log(
                action="decider.verdict",
                agent="orchestrator",
                result=verdict_name.lower(),
                risk_level="high" if action.sensitivity == "high" else "medium",
                payload={
                    "action_kind": action.kind,
                    "descriptor": action.descriptor,
                    "mutating": action.mutating,
                    "verdict": verdict_name,
                    "reason": verdict.reason,
                    "action_hash": act_hash,
                },
                task_id=task.id,
            )
            self._bus.publish_type(
                EventType.DECIDER_VERDICT,
                {
                    "verdict": verdict_name,
                    "action_kind": action.kind,
                    "action_hash": act_hash,
                    "reason": verdict.reason,
                },
                task.id,
            )
        except Exception:
            pass  # la telemetría no bloquea la decisión (D7)

    def register_undo(self, action_hash_value: str, kind: str, ref: str) -> None:
        """Ata una primitiva de undo real a una acción autorizada (slice 6).

        Solo se llama cuando una acción reversible se ejecuta y deja un handle
        consumible: snapshot OMEGA (``SNAPSHOT``) o server MCP (``MCP_SERVER``).
        """
        self._revert_registry.register(action_hash_value, kind, ref)

    def revert(self, action_hash_value: str) -> bool:
        """Deshace una acción previa por su ``action_hash`` (ADR-040 slice 6).

        Resuelve el handle persistido y dispara la primitiva: restaura el
        snapshot o retira el server MCP. Devuelve False si no hay handle o si la
        primitiva no pudo deshacer. Un revert consumado olvida el handle.
        """
        handle = self._revert_registry.get(action_hash_value)
        if handle is None:
            return False
        if handle.kind == SNAPSHOT:
            ok = self._sandbox.restore_snapshot(handle.ref)
        elif handle.kind == MCP_SERVER:
            ok = self._mcp.remove_server(handle.ref)
        elif handle.kind == COLD_PATCH:
            ok = self.cold_update().rollback_applied(handle.ref)
        else:
            ok = False
        if ok:
            self._revert_registry.forget(action_hash_value)
            try:
                self._merkle.log(
                    action="decider.revert",
                    agent="orchestrator",
                    result="success",
                    risk_level="medium",
                    payload={"action_hash": action_hash_value, "kind": handle.kind, "ref": handle.ref},
                )
            except Exception:
                pass
        return ok

    # ------------------------------------------------------------------
    # ADR-040 slice 6 — mutaciones reversibles gobernadas por el seam
    #
    # Únicos call-sites que declaran ``reversible=True``: tienen una primitiva
    # de undo real y registrable. Hilan el ``action_hash`` de la decisión hasta
    # la ejecución y, tras dejar el handle, atan el undo a ese hash. El resto de
    # los call-sites sigue ``reversible=False`` → el AutonomousDecider los deniega
    # (invariante 4, fail-safe). ``revert(action_hash)`` consume el handle.
    # ------------------------------------------------------------------

    def adopt_mcp_server(self, cfg: McpServerConfig, task: Task) -> str:
        """Adopta un server MCP en caliente bajo veredicto del decisor (ADR-040).

        Mutación reversible: ``remove_server`` deshace la adopción. Si el decisor
        autoriza y ``add_server`` reporta ``ok:``, registra el undo
        ``MCP_SERVER`` atado al ``action_hash`` exacto que autorizó. Devuelve el
        estado textual (``ok:`` / ``skipped:`` / ``vetoed:`` / ``error:`` /
        ``denegado:`` / ``requiere aprobación humana``) para que el llamante lo
        reporte (Telegram, auto-mantenimiento)."""
        verdict, act_hash = self._consult_decider(
            DecisionAction(
                kind="mcp_adopt",
                requires_approval=True,
                mutating=True,
                reversible=True,
                sensitivity=task.sensitivity,
                descriptor=cfg.name,
                reason="adopción de server MCP",
            ),
            task,
        )
        if isinstance(verdict, RequiresHuman):
            return "requiere aprobación humana para adoptar el server"
        if isinstance(verdict, Deny):
            return f"denegado: {verdict.reason}"
        status = self._mcp.add_server(cfg)
        if status.startswith("ok:"):
            self.register_undo(act_hash, MCP_SERVER, cfg.name)
        return status

    def execute_reversible_code(
        self, code: str, task: Task, *, descriptor: str = ""
    ) -> SandboxResult | None:
        """Ejecuta código en OMEGA con snapshot previo, bajo veredicto del seam.

        Mutación reversible: el snapshot del workspace permite undo físico
        (``restore_snapshot``). Si el decisor autoriza y la ejecución dejó un
        ``snapshot_id``, registra el undo ``SNAPSHOT`` atado al ``action_hash``.
        Devuelve ``None`` si el decisor no autorizó (Deny / RequiresHuman); en
        ese caso no se ejecuta nada."""
        verdict, act_hash = self._consult_decider(
            DecisionAction(
                kind="omega_exec",
                requires_approval=True,
                mutating=True,
                reversible=True,
                sensitivity=task.sensitivity,
                descriptor=descriptor,
                reason="ejecución OMEGA con snapshot reversible",
            ),
            task,
        )
        if not isinstance(verdict, Allow):
            return None
        result = self._sandbox.execute(
            code=code,
            operational_mode=OperationalMode.OMEGA,
            take_snapshot=True,
        )
        if result.snapshot_id is not None:
            self.register_undo(act_hash, SNAPSHOT, result.snapshot_id)
        return result

    def authorize_offensive_action(
        self,
        grant: "Any",
        *,
        candidate_target: str,
        capability: "Any",
        intent: str,
        contained: bool,
    ) -> "tuple[Any, str | None]":
        """ADR-043 Fase 0 — gate de autorización + seam del decisor para acciones
        ofensivas. Autorización NECESARIA pero NO suficiente: un grant válido pasa
        el gate, pero el decisor sigue gobernando (lo irreversible/activo escala o se
        deniega; lo contenido-en-sandbox=reversible puede fluir). Fail-closed."""
        import os
        from atlas.security.authorization import AuthorizationVerifier

        key = os.environ.get("ATLAS_AUTHZ_HMAC_KEY", "").encode()
        hmac_key: bytes | None = key if key else None
        authz = AuthorizationVerifier(hmac_key=hmac_key).check(
            grant,
            candidate_target=candidate_target,
            capability=capability,
        )
        if not authz.allowed:
            self._merkle.log(
                action="authz.denied",
                agent="authorization",
                result="blocked",
                risk_level="high",
                payload={
                    "target": candidate_target,
                    "capability": str(capability),
                    "reason": authz.reason,
                    "grant": grant.to_dict(),
                },
            )
            return Deny(reason=f"sin autorización: {authz.reason}"), None

        self._merkle.log(
            action="authz.granted",
            agent="authorization",
            result="success",
            risk_level="moderate",
            payload={
                "target": candidate_target,
                "capability": str(capability),
                "issuer": grant.issuer,
                "grant": grant.to_dict(),
            },
        )
        task = Task(intent=intent, source=TaskSource.INTERNAL)
        return self._consult_decider(
            DecisionAction(
                kind="offensive_action",
                requires_approval=True,
                mutating=True,
                reversible=contained,
                sensitivity="moderate" if contained else "high",
                descriptor=f"{capability}@{candidate_target}",
                reason=(
                    f"acción ofensiva (grant issuer={grant.issuer},"
                    f" exp={grant.expires_at}, contained={contained})"
                ),
            ),
            task,
        )

    def handle_intent(self, intent: str, source: TaskSource = TaskSource.CLI) -> Task:
        """
        Convierte una intencion en una Task ejecutada con todo el pipeline:
        Governance → Permission → Classify → Route → Execute → Log.
        """
        task = Task(intent=intent, source=source)
        self._merkle.log(
            action="task.created",
            agent="orchestrator",
            result="pending",
            risk_level="safe",
            payload={"intent": intent, "source": source.value},
            task_id=task.id,
        )
        self._bus.publish_type(EventType.TASK_RECEIVED, {"intent": intent}, task.id)

        try:
            self._run_pipeline(task)
        except Exception as e:
            task.transition(TaskStatus.FAILED)
            task.error = str(e)
            self._merkle.log(
                action="task.failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"error": str(e)},
                task_id=task.id,
            )

        return task

    def status(self) -> AtlasStatus:
        """Retorna el estado completo del core."""
        gov = GovernanceL0.get_instance()
        chain_ok, _ = self._merkle.verify_chain()
        hermes_status = self._hermes.health_check()
        uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        repo_root = self._repo_root()
        return AtlasStatus(
            version=self.VERSION,
            workspace=str(self._workspace),
            repo_root=str(repo_root) if repo_root else None,
            governance_ok=not gov.in_emergency_mode,
            chain_ok=chain_ok,
            tool_count=len(self._tool_registry.enabled()),
            queue_depth=self._offline_queue.depth,
            hermes_mode=hermes_status.mode,
            record_count=self._merkle.record_count,
            uptime_seconds=round(uptime, 1),
            emergency_mode=gov.in_emergency_mode,
        )

    def health_report(self) -> dict[str, Any]:
        """JSON de salud operativa (Gate I)."""
        st = self.status()
        hermes = self._hermes.health_check()
        thermal_mode = OperationalMode.NORMAL.value
        if self._thermal_watchdog is not None:
            thermal_mode = self._thermal_watchdog.current_operational_mode().value
        return {
            "version": st.version,
            "uptime_s": st.uptime_seconds,
            "governance_ok": st.governance_ok,
            "merkle_chain_ok": st.chain_ok,
            "emergency_mode": st.emergency_mode,
            "hermes_mode": hermes.mode,
            "hermes_reachable": hermes.reachable,
            "thermal_mode": thermal_mode,
            "gate_d_enabled": self._gate_d_enabled,
            "gate_h": self._gate_h.status_summary(),
            "pending_approvals_count": len(self.pending_approvals()),
            "queue_depth": st.queue_depth,
            "telegram_running": self._telegram_thread is not None and self._telegram_thread.is_alive(),
            "offline_monitor_running": self._offline_monitor is not None,
            "observability": self._observability.snapshot(),
        }

    def cold_update(self) -> Any:
        """ADR-025 ColdUpdateManager (project root via ATLAS_CORE_ROOT)."""
        if self._cold_update_manager is None:
            from atlas.core.cold_update_manager import ColdUpdateManager

            root = Path(
                os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
            ).expanduser().resolve()
            self._cold_update_manager = ColdUpdateManager(root, self._merkle)
        return self._cold_update_manager

    def advance_cold_update(self, proposal_id: str) -> str:
        """Avanza una propuesta de ColdUpdate bajo veredicto del decisor (ADR-040).

        Punto único que cierra el lazo de los proposers (deps/codegen): valida
        en worktree si hace falta y consulta el seam para aprobar+aplicar. Bajo
        ``HumanDecider`` (default) devuelve "requiere aprobación humana" y la
        propuesta queda ``validated`` esperando el CLI (`atlas update approve`)
        — paridad exacta con hoy. Bajo autónomo/híbrido, lo de bajo riesgo
        anclado en su intención se aplica con undo real (``rollback_applied``,
        kind ``COLD_PATCH``); ``risk=high/critical`` viaja como sensitivity=high
        → el AutonomousDecider lo deniega (regla constitucional #4) y el Hybrid
        lo escala a humano. Mutación reversible: el patch aplicado se deshace
        con ``revert(action_hash)``."""
        mgr = self.cold_update()
        proposal = mgr.get(proposal_id)
        if proposal is None:
            return f"error: propuesta {proposal_id} no existe"
        if proposal.status == "proposed":
            report = mgr.validate(proposal_id)
            if not report.passed:
                return "validation_failed: el patch no pasa pytest/mypy en worktree"
            proposal = mgr.get(proposal_id)
        if proposal.status != "validated":
            return f"skipped: estado {proposal.status} (se requiere validated)"

        # El descriptor ancla la acción al ARTEFACTO (evidencia del proposer:
        # dependencia, path objetivo…), no repite el intent — así el invariante
        # de coherencia del AutonomousDecider compara cosas distintas.
        evidence_surface = " ".join(
            str(v) for v in (proposal.evidence or {}).values()
        ).strip()
        task = Task(intent=proposal.intent, source=TaskSource.INTERNAL)
        verdict, act_hash = self._consult_decider(
            DecisionAction(
                kind="cold_update_apply",
                requires_approval=True,
                mutating=True,
                reversible=True,
                sensitivity="high" if proposal.risk in ("high", "critical") else "normal",
                descriptor=evidence_surface or proposal.intent,
                reason=f"aplicar patch ColdUpdate (origin={proposal.origin}, risk={proposal.risk})",
            ),
            task,
        )
        if isinstance(verdict, RequiresHuman):
            return "requiere aprobación humana (atlas update approve)"
        if isinstance(verdict, Deny):
            mgr.reject(proposal_id, reason=verdict.reason)
            return f"denegado: {verdict.reason}"
        mgr.approve(proposal_id)
        result = mgr.apply(proposal_id)
        self.register_undo(act_hash, COLD_PATCH, proposal_id)
        return f"applied: {result['proposal_id']}"

    def swarm_cycle(self) -> Any:
        """Capa 3 (ADR-045/046/048) — ciclo de mantenimiento del enjambre.

        Un worker produce diffs mecánicos verificados (capa 1) en worktree
        aislado; cada artefacto ACEPTADO baja por ``ColdUpdateReconciler`` →
        propuesta ColdUpdate → seam del decisor. **Auto-apply OFF** (propuesta
        -solo): nada se aplica aquí. Escritor único = este ``_merkle`` (mismo
        patrón que el self-audit: el worker es productor puro, no escribe Merkle
        ni toca el ATLAS_HOME vivo; el coordinador registra en la cadena única).
        El walker lee blobs de HEAD (no el disco vivo) y el ciclo deduplica
        contra propuestas swarm abiertas con tope (anti-acumulación)."""
        if self._swarm_cycle is None:
            from atlas.core.swarm_cycle import SwarmCycle, head_file_provider

            root = Path(
                os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
            ).expanduser().resolve()
            self._swarm_cycle = SwarmCycle(
                manager=self.cold_update(),
                merkle=self._merkle,
                file_provider=head_file_provider(root),
                root=root,
            )
        return self._swarm_cycle

    def swarm_audit_sample(self, fraction: float = 0.2) -> dict[str, Any]:
        """Off-path del propose; re-ejecuta la suite sobre una muestra de propuestas
        swarm con ATLAS_HOME aislado; divergencias = punto ciego del verificador
        barato."""
        from atlas.core.swarm_audit import reverify_swarm_proposals

        return reverify_swarm_proposals(
            self.cold_update(),
            fraction=fraction,
            merkle=self._merkle,
        )

    def self_audit(self) -> Any:
        """Atlas 24h self-audit loop (cold, auditable, no hot self-patch)."""
        if self._self_audit_runner is None:
            from atlas.core.patch_generator import PatchGenerator
            from atlas.core.self_audit import SelfAuditRunner

            root = Path(
                os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
            ).expanduser().resolve()
            self._self_audit_runner = SelfAuditRunner(
                root,
                self._merkle,
                health_provider=self.health_report,
                patch_generator=PatchGenerator(root),
            )
        return self._self_audit_runner

    def maintenance_scout(self) -> Any:
        """ADR-039 slice 1 — Scout read-only de salud/deuda. Delegado al facade."""
        return self._maintenance_facade.maintenance_scout()

    def maintenance_adopter(self) -> Any:
        """ADR-039 slice 3 — wire propuesta → ``adopt_mcp_server``. Delegado al facade."""
        return self._maintenance_facade.maintenance_adopter()

    def maintenance_registry_scout(self) -> Any:
        """ADR-039 slice 1 (literal) — Scout externo autoritativo. Delegado al facade."""
        return self._maintenance_facade.maintenance_registry_scout()

    def maintenance_scheduler(self) -> Any:
        """ADR-039 slice 4 — Scheduler cron del front-half. Delegado al facade."""
        return self._maintenance_facade.maintenance_scheduler()

    def maintenance_dep_scout(self) -> Any:
        """ADR-039 slice 6 — Scout de bumps de dependencias PyPI. Delegado al facade."""
        return self._maintenance_facade.maintenance_dep_scout()

    def maintenance_dep_proposer(self) -> Any:
        """ADR-039 slice 6 — Materializa bump como patch de ColdUpdate. Delegado al facade."""
        return self._maintenance_facade.maintenance_dep_proposer()

    def _knowledge_cve_proposer_instance(self) -> Any:
        """CveDepProposer instanciado lazily para bumps CVE-driven."""
        if self._knowledge_cve_proposer is None:
            from atlas.knowledge.self_improvement import CveDepProposer

            self._knowledge_cve_proposer = CveDepProposer(
                pyproject_path=self._project_root() / "pyproject.toml",
                propose=self.cold_update().propose,
                merkle=self._merkle,
            )
        return self._knowledge_cve_proposer

    def maintenance_community_scout(self) -> Any:
        """ADR-039 slice 5 — Scout community (foros). Delegado al facade."""
        return self._maintenance_facade.maintenance_community_scout()

    def maintenance_codegen_proposer(self) -> Any:
        """ADR-039 slice 7 — Codegen como patch dirigido. Delegado al facade."""
        return self._maintenance_facade.maintenance_codegen_proposer()

    @property
    def _maintenance_scheduler(self) -> Any:
        """Acceso directo al scheduler lazy (service_runner lo lee para hacer stop)."""
        return self._maintenance_facade._maintenance_scheduler

    @_maintenance_scheduler.setter
    def _maintenance_scheduler(self, value: Any) -> None:
        self._maintenance_facade._maintenance_scheduler = value

    @property
    def _maintenance_scout(self) -> Any:
        return self._maintenance_facade._maintenance_scout

    @_maintenance_scout.setter
    def _maintenance_scout(self, value: Any) -> None:
        self._maintenance_facade._maintenance_scout = value

    @property
    def _maintenance_adopter(self) -> Any:
        return self._maintenance_facade._maintenance_adopter

    @_maintenance_adopter.setter
    def _maintenance_adopter(self, value: Any) -> None:
        self._maintenance_facade._maintenance_adopter = value

    @property
    def _maintenance_registry_scout(self) -> Any:
        return self._maintenance_facade._maintenance_registry_scout

    @_maintenance_registry_scout.setter
    def _maintenance_registry_scout(self, value: Any) -> None:
        self._maintenance_facade._maintenance_registry_scout = value

    @property
    def _maintenance_dep_scout(self) -> Any:
        return self._maintenance_facade._maintenance_dep_scout

    @_maintenance_dep_scout.setter
    def _maintenance_dep_scout(self, value: Any) -> None:
        self._maintenance_facade._maintenance_dep_scout = value

    @property
    def _maintenance_dep_proposer(self) -> Any:
        return self._maintenance_facade._maintenance_dep_proposer

    @_maintenance_dep_proposer.setter
    def _maintenance_dep_proposer(self, value: Any) -> None:
        self._maintenance_facade._maintenance_dep_proposer = value

    @property
    def _maintenance_codegen_proposer(self) -> Any:
        return self._maintenance_facade._maintenance_codegen_proposer

    @_maintenance_codegen_proposer.setter
    def _maintenance_codegen_proposer(self, value: Any) -> None:
        self._maintenance_facade._maintenance_codegen_proposer = value

    @property
    def _maintenance_community_scout(self) -> Any:
        return self._maintenance_facade._maintenance_community_scout

    @_maintenance_community_scout.setter
    def _maintenance_community_scout(self, value: Any) -> None:
        self._maintenance_facade._maintenance_community_scout = value

    @staticmethod
    def _project_root() -> Path:
        return Path(
            os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
        ).expanduser().resolve()

    def _pyproject_dep_floors(self) -> list[tuple[str, str]]:
        """Pares (nombre, piso ``>=``) de las deps de ``pyproject``. Vacío si falla."""
        import tomllib

        from packaging.requirements import Requirement

        path = self._project_root() / "pyproject.toml"
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return []
        floors: list[tuple[str, str]] = []
        for raw in data.get("project", {}).get("dependencies", []):
            try:
                req = Requirement(raw)
            except Exception:  # noqa: BLE001 — un requirement raro no tumba el resto
                continue
            for spec in req.specifier:
                if spec.operator == ">=":
                    floors.append((req.name, spec.version))
                    break
        return floors

    def knowledge_scan_step(self) -> dict[str, Any]:
        """Escanea CVEs para las deps de Atlas y propone bumps vía ColdUpdate.

        Para cada dep en pyproject: consulta OSV.dev, cruza con la versión
        instalada (SelfImprovementBridge) y propone dep-bump si hay fixed_version.
        Sin red cuando SSRF bloquea el egress. Retorna conteos de la pasada.
        """
        from datetime import datetime, timezone

        from atlas.knowledge.artifact import KnowledgeArtifact
        from atlas.knowledge.self_improvement import SelfImprovementBridge
        from atlas.knowledge.sources import OsvDepSource

        deps = self._pyproject_dep_floors()
        bridge = SelfImprovementBridge()
        proposer = self._knowledge_cve_proposer_instance()
        osv = OsvDepSource(bridge=self._ssrf_bridge)

        scanned = 0
        total_findings = 0
        proposed = 0

        for dep_name, _floor in deps:
            try:
                records = osv.fetch(dep_name)
                if not records:
                    scanned += 1
                    continue
                record = records[0]
                # status -1 = SSRF bloqueado; cualquier non-200 fuera de eso se salta
                if record.status == -1 or record.status != 200:
                    scanned += 1
                    continue
                try:
                    content = json.loads(record.payload)
                except (ValueError, TypeError):
                    scanned += 1
                    continue

                artifact = KnowledgeArtifact(
                    id=f"osv/{dep_name}",
                    domain="security/cve",
                    source_id="osv.dev/pypi",
                    content=content,
                    provenance={
                        "url": record.url,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                findings = bridge.scan(artifact)
                total_findings += len(findings)
                for f in findings:
                    if f.fixed_version is not None:
                        result = proposer.propose_bump(f)
                        if result is not None:
                            proposed += 1
                scanned += 1
            except Exception:  # noqa: BLE001 — un fallo aislado no aborta el barrido
                scanned += 1

        # Paso MCP: exponer tools disponibles como artefacto de conocimiento
        try:
            from atlas.knowledge.sources import McpKnowledgeSource
            mcp_src = McpKnowledgeSource(self._mcp)
            mcp_records = mcp_src.fetch(None)
            if mcp_records and mcp_records[0].status == 200:
                try:
                    mcp_content = json.loads(mcp_records[0].payload)
                except (ValueError, TypeError):
                    mcp_content = None
                if mcp_content is not None:
                    mcp_artifact = KnowledgeArtifact(
                        id="mcp/local",
                        domain="tools/mcp",
                        source_id="mcp/local",
                        content=mcp_content,
                        provenance={
                            "url": mcp_records[0].url,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    bridge.scan(mcp_artifact)  # retorna [] para domain != security/cve
                    scanned += 1
        except Exception:  # noqa: BLE001
            pass

        return {"scanned": scanned, "findings": total_findings, "proposed": proposed}

    def audit_tail(self, n: int = 20) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._merkle.tail(n)]

    def tools(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tool_registry.all()]

    def pending_approvals(self) -> list[dict[str, Any]]:
        return self._approvals.pending()

    def approve_pending(
        self,
        task_id: str,
        approved: bool,
        *,
        abort: bool = False,
        approve_only: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._approvals.approve(
            task_id, approved, abort=abort, approve_only=approve_only,
        )

    def attach_gate_f_tools(
        self,
        *,
        browser: Any | None = None,
        editor: Any | None = None,
        vision_loop: Any | None = None,
    ) -> None:
        """
        Inyecta herramientas Gate F ya construidas.

        Es principalmente util para tests y para integraciones que quieran
        controlar el ciclo de vida del browser/editor. Si no se inyectan, el
        Orchestrator construye instancias conservadoras bajo demanda.
        """
        self._gate_f_exec.attach(
            browser=browser, editor=editor, vision_loop=vision_loop,
        )

    def start_mcp_servers(self) -> None:
        """ADR-035: arranca los servers MCP del registry (opt-in, idempotente).

        Pensado para ``atlas serve`` y CLI interactivos. Tests y flows
        unitarios pueden no llamarlo: el registry vacío hace que las tools
        MCP no aparezcan en specs ni en dispatch.
        """
        if self._mcp_started:
            return
        self._mcp.start_all()
        self._mcp_started = True

    def stop_mcp_servers(self) -> None:
        if not self._mcp_started:
            return
        self._mcp.close_all()
        self._mcp_started = False

    def memory_read(self, layer: str) -> Any:
        layer_map = {
            "system_context": lambda: self._system_context.as_system_context(),
            "error_registry": lambda: [e.to_dict() for e in self._error_registry.all()],
            "approved_patterns": lambda: [e.to_dict() for e in self._approved_patterns.all()],
        }
        fn = layer_map.get(layer)
        if fn is None:
            return {"error": f"Capa desconocida: {layer}"}
        return fn()

    def gate_h_status(self) -> dict[str, Any]:
        return self._gate_h.status_summary()  # type: ignore[no-any-return]

    def rebuild_memory(self) -> dict[str, int]:
        return self._gate_h.rebuild_memory(self._vector_store)  # type: ignore[no-any-return]

    def gate_h_receipts(self, n: int = 20) -> list[dict[str, Any]]:
        return [
            r.to_dict()
            for r in self._merkle.tail(n * 3)
            if r.action == "generated_tool.receipt"
        ][-n:]

    def _record_tool_receipt(
        self,
        task: Task,
        *,
        purpose: str,
        data_touched: list[str] | None = None,
        permissions_required: list[str] | None = None,
        safety_checks: list[str] | None = None,
        approval_path: str = "automatic",
    ) -> None:
        receipt = ReasoningReceipt(
            purpose=purpose,
            data_touched=data_touched or [task.tool_name or "unknown"],
            permissions_required=permissions_required or [
                task.route.value if task.route else "unknown"
            ],
            safety_checks=safety_checks or [
                "PermissionProfile",
                "AtlasExecutor",
                "MerkleLogger",
            ],
            approval_path=approval_path,
        )
        self._gate_h.record_reasoning_receipt(
            task.id,
            task.tool_name or "unknown",
            receipt,
        )

    def _check_gate_h_tool_allowed(self, tool_name: str, task_id: str | None = None) -> str | None:
        if self._gate_h.is_tool_paused(tool_name):
            return f"Herramienta pausada por Gate H: {tool_name}"
        if not self._gate_h.is_allowed_in_diagnostic(tool_name):
            return f"Modo diagnostico Gate H: solo tools conocidas ({tool_name} bloqueada)"
        return None

    @staticmethod
    def _is_generated_tool_run(working_dir: str, command: str) -> bool:
        wd = working_dir.replace("\\", "/").lower()
        if ".atlas/generated" in wd:
            return True
        cmd_lower = command.lower()
        if ".atlas/generated" in cmd_lower:
            return True
        if "python" in cmd_lower and ".py" in cmd_lower:
            return True
        return False

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def executor(self) -> AtlasExecutor:
        """AtlasExecutor (ADR-020). Toda IO con efecto externo deberia ir aqui."""
        return self._executor

    @property
    def capability_issuer(self) -> CapabilityIssuer:
        """Issuer de capability tokens — equivalente a orchestrator.executor.issuer."""
        return self._capability_issuer

    @property
    def gate_d_pipeline_enabled(self) -> bool:
        return self._gate_d_enabled

    @property
    def distiller(self) -> Any:
        return self._distiller

    @property
    def ghost_replay(self) -> Any:
        return self._ghost_replay

    @property
    def slm_classifier(self) -> Any:
        return self._slm_classifier

    @property
    def timetravel(self) -> Any:
        return self._timetravel

    @property
    def pii_surrogate(self) -> PIISurrogate:
        return self._pii_surrogate  # type: ignore[no-any-return]

    @property
    def inference_hub(self) -> Any:
        """InferenceHub asociado al pipeline Gate D (None si no fue inyectado)."""
        return self._inference_hub

    @property
    def vector_store(self) -> KuzuVectorStore | None:
        """KuzuVectorStore activo cuando Gate D + ATLAS_MEMORY_VECTOR (default on)."""
        return self._vector_store

    @property
    def block_memory(self) -> BlockMemory:
        """ADR-030 block memory — bloques siempre-en-contexto (Letta/MemGPT)."""
        return self._block_memory

    @staticmethod
    def _memory_vector_enabled() -> bool:
        return os.environ.get("ATLAS_MEMORY_VECTOR", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

    # ------------------------------------------------------------------
    # Gate D pipeline integrado (opt-in)
    # ------------------------------------------------------------------

    def enable_gate_d_pipeline(
        self,
        *,
        embedder: Embedder | None = None,
        inference_hub: InferenceHub | None = None,
        ghost_ttl_s: int = 24 * 3600,
        slm_mode: str = "auto",
    ) -> None:
        """
        Activa el pipeline integrado con todas las piezas Gate D:
        GhostReplay -> hybrid classifier -> MemoryDistiller ->
        AtlasExecutor -> InferenceHub -> TimeTravel.

        Idempotente: si ya esta activo, no reconstruye las piezas.
        """
        if self._gate_d_enabled:
            return

        emb = embedder or StubEmbedder()
        vector_store: KuzuVectorStore | None = None
        if self._memory_vector_enabled():
            kuzu_dir = self._workspace / "memory" / "kuzu"
            kuzu_dir.mkdir(parents=True, exist_ok=True)
            vector_store = KuzuVectorStore(
                db_path=kuzu_dir / "atlas.kuzu",
                embedder=emb,
            )
        self._vector_store = vector_store
        self._distiller = MemoryDistiller(embedder=emb, vector_store=vector_store)
        self._error_registry = ErrorRegistry(
            self._workspace / "memory" / "error_registry",
            merkle=self._merkle,
            vector_store=vector_store,
        )
        self._approved_patterns = ApprovedPatternStore(
            self._workspace / "memory" / "approved_patterns",
            merkle=self._merkle,
            vector_store=vector_store,
        )
        self._ghost_replay = GhostReplay(
            cache_path=self._workspace / "memory" / "ghost_cache",
            default_ttl_seconds=ghost_ttl_s,
        )
        hub = inference_hub
        if hub is None:
            from atlas.core.inference_hub import InferenceHub as _InferenceHub
            from atlas.transparency.gateway import TransparencyGateway
            from atlas.transparency.key_store import load_or_create_subject, load_or_create_operator
            from atlas.transparency.client_cosign import ClientCosigner
            from atlas.transparency.log import TransparencyLog

            subj_signer, _, _ = load_or_create_subject()
            op_signer, _, _   = load_or_create_operator()
            _tlog = TransparencyLog(signer=op_signer)
            _cosigner = ClientCosigner(subj_signer)
            _gw = TransparencyGateway(_cosigner, op_signer, _tlog)
            hub = _InferenceHub(mode="auto", transparency=_gw)
        self._inference_hub = hub
        self._slm_classifier = SLMClassifier(
            hub=hub,
            mode=slm_mode,
            ghost_replay=self._ghost_replay,
        )
        self._timetravel = TimeTravel(
            store_path=self._workspace / "memory" / "checkpoints",
            merkle=self._merkle,
        )
        pii_mode = os.environ.get("ATLAS_PII_SURROGATE_MODE", "auto")
        self._pii_surrogate = PIISurrogate(hub=hub, mode=pii_mode)
        self._gate_d_enabled = True
        self._merkle.log(
            action="pipeline.gate_d_enabled",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={
                "embedder_dim": emb.dim,
                "ghost_ttl_s":  ghost_ttl_s,
                "slm_mode":     slm_mode,
                "memory_vector": vector_store is not None,
                "pii_mode":     self._pii_surrogate.mode,
            },
        )
        self._gate_h._vector_store = vector_store
        if vector_store is not None:
            self._merkle.log(
                action="pipeline.memory_vector_enabled",
                agent="orchestrator",
                result="success",
                risk_level="safe",
                payload={
                    "db_path": str(self._workspace / "memory" / "kuzu" / "atlas.kuzu"),
                    "embedder_dim": emb.dim,
                },
            )

    # ------------------------------------------------------------------
    # Lifecycle Gate C / C4-s2 (bot Telegram + OfflineMonitor)
    # ------------------------------------------------------------------

    def start_telegram_bot(self, token: str | None = None) -> bool:
        """
        Arranca el bot si hay TELEGRAM_BOT_TOKEN disponible.
        Es opcional: si no hay token, registra un log y devuelve False.
        Retorna True si el bot quedo corriendo.

        ADR-026: si ATLAS_DISABLE_TELEGRAM=1, Atlas NO arranca el bot porque
        Hermes-Agent en el VPS ya lo gestiona (twin architecture). Sin esto,
        dos procesos harían long-polling sobre el mismo bot → respuestas
        intermitentes y conflicto en getUpdates.
        """
        if os.environ.get("ATLAS_DISABLE_TELEGRAM", "").strip().lower() in (
            "1", "true", "yes",
        ):
            self._merkle.log(
                action="telegram.skip", agent="orchestrator", result="disabled_by_env",
                risk_level="safe",
                payload={"reason": "ATLAS_DISABLE_TELEGRAM=1 (Hermes-Agent handles it)"},
            )
            return False
        token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            self._merkle.log(
                action="telegram.skip", agent="orchestrator", result="no_token",
                risk_level="safe", payload={"reason": "TELEGRAM_BOT_TOKEN no definido"},
            )
            return False

        from atlas.interfaces.orchestrator_ops import OrchestratorOps
        from atlas.interfaces.telegram_bot import (
            TelegramAuthorizer, TelegramBot, TelegramClient,
        )

        client = TelegramClient(token=token)
        authorizer = TelegramAuthorizer.from_permission_profile(self._permissions)
        ops = OrchestratorOps(self)
        bot = TelegramBot(
            client=client,
            authorizer=authorizer,
            ops=ops,
            merkle=self._merkle,
            telegram_config=self._permissions.telegram_config,
        )
        self._wire_bus_to_bot(bot)
        self._telegram_bot = bot
        self._telegram_thread = threading.Thread(
            target=bot.run_polling, daemon=True, name="atlas-telegram-bot",
        )
        self._telegram_thread.start()
        # Notificacion de arranque
        self._bus.publish_type(EventType.SESSION_STARTED, {
            "version": self.VERSION,
            "queued_tasks": self._offline_queue.depth,
        })
        return True

    def stop_telegram_bot(self) -> None:
        if self._telegram_bot is not None:
            self._telegram_bot.stop()
        if self._telegram_thread is not None:
            self._telegram_thread.join(timeout=2)
        self._telegram_bot = None
        self._telegram_thread = None

    def start_offline_monitor(self, poll_interval_seconds: int = 60) -> None:
        from atlas.core.offline_monitor import OfflineMonitor
        self._offline_monitor = OfflineMonitor(
            hermes=self._hermes, bus=self._bus,
            poll_interval_seconds=poll_interval_seconds,
        )
        self._offline_monitor.start()

    def stop_offline_monitor(self) -> None:
        if self._offline_monitor is not None:
            self._offline_monitor.stop()
            self._offline_monitor = None

    def sync_offline_queue(self) -> dict[str, Any]:
        """
        ADR-012 pull-on-reconnect — se llama cuando el OfflineMonitor detecta
        que Hermes volvio a estar reachable (evento HERMES_RECONNECTED).

        Drena la OfflineQueue: intenta re-enviar cada entrada pendiente a Hermes
        via enqueue_task(). Marca la entrada como 'sent' o 'failed' segun resultado.
        Devuelve un resumen {sent, failed, skipped}.

        Tambien se puede invocar manualmente (CLI/Telegram) para forzar un sync.
        """
        pending = self._offline_queue.all_pending()
        sent = failed = 0
        for entry in pending:
            try:
                self._hermes.enqueue_task(entry.delegation)
                self._offline_queue.mark_sent(entry.delegation.id)
                sent += 1
            except Exception as e:  # noqa: BLE001
                self._offline_queue.mark_failed(entry.delegation.id)
                failed += 1
                _log.warning("sync_offline_queue: fallo envio %s — %s",
                             entry.delegation.id[:8], e)

        skipped = len(pending) - sent - failed
        self._merkle.log(
            action="hermes.sync_offline_queue",
            agent="orchestrator",
            result="success" if failed == 0 else "partial",
            risk_level="safe",
            payload={"pending": len(pending), "sent": sent,
                     "failed": failed, "skipped": skipped},
        )
        _log.info("sync_offline_queue: %d enviadas, %d fallidas (de %d pendientes)",
                  sent, failed, len(pending))
        return {"sent": sent, "failed": failed, "skipped": skipped}

    def attach_thermal_watchdog(self, watchdog: Any) -> None:
        """Conecta un ThermalWatchdog ya construido para que emita THERMAL_ALERT."""
        self._thermal_watchdog = watchdog

    def thermal_alert_callback(self) -> Any:
        """Devuelve un callback para pasar a ThermalWatchdog(alert_callback=...)."""
        def _cb(state: Any) -> None:
            self._bus.publish_type(EventType.THERMAL_ALERT, {
                "mode": state.operational_mode.value,
                "temperature_c": state.temperature_celsius,
                "ram_free_mb": state.ram_free_mb,
                "policy": state.policy,
                "emergency": state.emergency,
            })
        return _cb

    def _wire_bus_to_bot(self, bot: Any) -> None:
        self._bus.subscribe(EventType.APPROVAL_REQUIRED, bot.on_approval_required)
        self._bus.subscribe(EventType.THERMAL_ALERT, bot.on_thermal_alert)
        self._bus.subscribe(EventType.SHADOW_ALERT, bot.on_shadow_alert)
        self._bus.subscribe(EventType.SESSION_STARTED, bot.on_session_started)
        # ADR-033 #4: progreso del loop agéntico (el handler decide opt-in).
        if hasattr(bot, "on_agentic_progress"):
            self._bus.subscribe(EventType.AGENTIC_PROGRESS, bot.on_agentic_progress)

    # ------------------------------------------------------------------
    # Pipeline interno
    # ------------------------------------------------------------------

    def _run_pipeline(self, task: Task) -> None:
        self._pipeline_runner._run_pipeline(task)

    # ------------------------------------------------------------------
    # Gate D — pipeline integrado opt-in
    # ------------------------------------------------------------------

    def _run_pipeline_gate_d(self, task: Task) -> None:
        self._pipeline_runner._run_pipeline_gate_d(task)

    def _hybrid_classify(
        self, intent: str, sensitivity: str | None, *, task_id: str | None = None,
    ) -> ClassificationResult:
        return self._pipeline_runner._hybrid_classify(intent, sensitivity, task_id=task_id)

    def _execute_task(self, task: Task) -> None:
        self._pipeline_runner._execute_task(task)

    # ------------------------------------------------------------------
    # Gate F — Browser / Editor / VisionLoop routing
    # ------------------------------------------------------------------

    def _parse_gate_f_command(self, intent: str) -> GateFCommand | None:
        return parse_gate_f_command(
            intent, is_generated_tool_run=self._is_generated_tool_run,
        )

    def _route_gate_f_command(self, task: Task, command: GateFCommand) -> None:
        task.transition(TaskStatus.ROUTING)
        task.route = (
            RoutingLevel.REQUIRES_APPROVAL
            if command.requires_approval or task.sensitivity == "high"
            else RoutingLevel.DETERMINISTIC_TOOL
        )
        task.tool_name = f"{command.tool}.{command.action}"
        task.metadata["gate_f_command"] = {
            "tool": command.tool,
            "action": command.action,
            "args": command.args,
            "requires_approval": command.requires_approval,
        }
        self._merkle.log(
            action="task.classified",
            agent="classifier_gate_f",
            result="success",
            risk_level="safe",
            payload={
                "route": task.route.value,
                "tool": task.tool_name,
                "reason": command.reason,
            },
            task_id=task.id,
        )

        if task.route == RoutingLevel.REQUIRES_APPROVAL:
            verdict, _ = self._consult_decider(
                DecisionAction(
                    kind="gate_f",
                    requires_approval=command.requires_approval,
                    sensitivity=task.sensitivity,
                    mutating=True,
                    reason=command.reason,
                    descriptor=task.tool_name or "",
                ),
                task,
            )
            if isinstance(verdict, RequiresHuman):
                task.transition(TaskStatus.AWAITING_APPROVAL)
                task.result = {
                    "message": f"Accion Gate F requiere aprobacion explicita. Razon: {command.reason}",
                    "approved": False,
                    "reason": command.reason,
                    "tool": task.tool_name,
                }
                self._approvals.register(task)
                self._persist_pending_approval(task)
                self._merkle.log(
                    action="task.routed",
                    agent="router_gate_f",
                    result="pending",
                    risk_level="high",
                    payload={"requires_approval": True, "tool": task.tool_name},
                    task_id=task.id,
                )
                self._bus.publish_type(EventType.APPROVAL_REQUIRED, {
                    "task_id": task.id,
                    "intent": task.intent,
                    "reason": command.reason,
                    "tool": task.tool_name,
                }, task.id)
                return
            if isinstance(verdict, Deny):
                self._block_task(task, verdict.reason or command.reason, "high")
                return
            # Allow → el decisor autoriza sin humano; cae a ejecución.

        task.transition(TaskStatus.EXECUTING)
        self._execute_gate_f_task(task)

    def _execute_gate_f_task(self, task: Task) -> None:
        self._gate_f_exec.execute_task(task)

    def _execute_browser_command(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        return self._gate_f_exec.execute_browser_command(action, args)

    def _execute_editor_command(
        self,
        action: str,
        args: dict[str, Any],
        *,
        task: Task | None = None,
    ) -> dict[str, Any]:
        return self._gate_f_exec.execute_editor_command(action, args, task=task)

    def _execute_vision_command(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        return self._gate_f_exec.execute_vision_command(action, args)

    def _get_browser_tool(self) -> Any:
        return self._gate_f_exec.get_browser_tool()

    def _get_editor_tool(self) -> Any:
        return self._gate_f_exec.get_editor_tool()

    def _get_vision_loop(self) -> Any:
        return self._gate_f_exec.get_vision_loop()

    # ------------------------------------------------------------------
    # Pending approval persistence (Gate G)
    # ------------------------------------------------------------------

    def _pending_summary(self, task: Task) -> dict[str, Any]:
        return TaskPersistence.summary(task)

    def _persist_pending_approval(self, task: Task) -> None:
        self._tasks.persist(task)

    def _load_pending_approval(self, task_id: str) -> Task | None:
        return self._tasks.load(task_id)

    def _load_persisted_pending_approvals(self) -> list[Task]:
        return self._tasks.load_all()

    def _delete_pending_approval(self, task_id: str) -> None:
        self._tasks.delete(task_id)

    def _serialize_task(self, task: Task) -> dict[str, Any]:
        return TaskPersistence.serialize(task)

    def _deserialize_task(self, data: dict[str, Any]) -> Task:
        return TaskPersistence.deserialize(data)

    # ------------------------------------------------------------------
    # ADR-031 — herramientas del loop agéntico
    # ------------------------------------------------------------------

    _UNTRUSTED_MARKER = _ah.UNTRUSTED_MARKER
    _AGENTIC_MUTATING_TOOLS = _ah.AGENTIC_MUTATING_TOOLS
    _AGENTIC_UNTRUSTED_READERS = _ah.UNTRUSTED_READERS

    def _agentic_tool_specs(self) -> list[dict[str, Any]]:
        return _ah.tool_specs() + self._mcp.tool_specs()

    def _agentic_tool_kind(self, name: str) -> str:
        # ADR-035 dec.5: tools MCP son mutate por defecto. La allowlist por
        # server (read_only_tools en mcp_servers.json) marca cuáles corren
        # inline. Esto convive con ADR-037: la procedencia 'untrusted' (que
        # también es mcp__*) sigue activando taint y envoltura.
        if name.startswith("mcp__"):
            return "read" if self._mcp.is_read_only(name) else "mutate"
        return _ah.tool_kind(name)

    def _agentic_tool_provenance(self, name: str) -> str:
        return _ah.tool_provenance(name)

    def _wrap_untrusted(self, content: str) -> str:
        return _ah.wrap_untrusted(content)

    def _loop_is_tainted(self, messages: list[dict[str, Any]]) -> bool:
        return _ah.loop_is_tainted(messages)

    # ------------------------------------------------------------------
    # ADR-033 — refinamientos del loop suspendible
    # ------------------------------------------------------------------

    def set_agentic_auto_approve(self, tools: list[str] | set[str]) -> None:
        """ADR-033 #2: configura la allowlist de mutaciones auto-aprobadas (sin
        HITL). Pensado para tools de bajo riesgo en las que ya confías. NO se
        persiste en governance.json; vive solo en este proceso/sesión."""
        self._agentic_auto_approve = frozenset(t.strip() for t in tools if t.strip())

    def _is_agentic_auto_approved(self, name: str, task: Task) -> bool:
        """Una mutación corre inline (sin suspender) solo si está en la allowlist
        Y la tarea no es de sensibilidad alta. Seguro por defecto: allowlist
        vacía → siempre False → todo mutante exige HITL."""
        if name not in self._agentic_auto_approve:
            return False
        return task.sensitivity != "high"

    def sweep_expired_suspensions(
        self, ttl_seconds: float | None = None,
    ) -> list[str]:
        """ADR-033 #1: cancela loops suspendidos cuyo `agentic_state.created_at`
        supera el TTL. Opt-in: si `ttl_seconds` (o el TTL configurado) es None/<=0
        no hace nada. Devuelve los task_id cancelados. Pensado para invocarse
        desde el tick de `atlas serve` o `atlas pending --sweep`."""
        ttl = ttl_seconds if ttl_seconds is not None else self._agentic_suspension_ttl
        if not ttl or ttl <= 0:
            return []
        now = datetime.now(timezone.utc)
        cancelled: list[str] = []
        in_memory = self._approvals.snapshot()
        candidates = {t.id: t for t in in_memory}
        for t in self._load_persisted_pending_approvals():
            candidates.setdefault(t.id, t)

        for task in candidates.values():
            state = task.metadata.get("agentic_state")
            if not isinstance(state, dict):
                continue
            created_raw = state.get("created_at")
            if not created_raw:
                continue
            try:
                created = datetime.fromisoformat(str(created_raw))
            except ValueError:
                continue
            if (now - created).total_seconds() < ttl:
                continue
            # Expirado → cancelar y limpiar.
            lock_fd, lock_path = self._acquire_pending_lock(task.id)
            if lock_fd is None:
                continue  # otro proceso lo está tocando; sáltalo
            try:
                self._approvals.discard(task.id)
                if task.status == TaskStatus.AWAITING_APPROVAL:
                    task.transition(TaskStatus.CANCELLED)
                task.result = {
                    "approved": False,
                    "message": "Loop suspendido expirado (TTL) — cancelado.",
                    "expired": True,
                }
                self._delete_pending_approval(task.id)
                self._merkle.log(
                    action="task.suspension_expired",
                    agent="orchestrator.agentic",
                    result="cancelled",
                    risk_level="moderate",
                    payload={"ttl_seconds": ttl, "created_at": created_raw},
                    task_id=task.id,
                )
                cancelled.append(task.id)
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
                if lock_path is not None:
                    lock_path.unlink(missing_ok=True)
        return cancelled

    def _stringify_tool_result(self, result: Any) -> str:
        return _ah.stringify_tool_result(result)

    def _hermes_local_takeover(self) -> bool:
        """Hermes pausado → el portátil absorbe la carga (ATLAS_HERMES_LOCAL=1).

        Con el VPS dado de baja, las tareas DELEGATE_HERMES se pudrían en la
        OfflineQueue (nadie la consume). Con el flag activo y el adapter en
        mock, la delegación se convierte en ejecución local. Solo aplica al
        mock: si hay un Hermes REST real configurado, se delega normal."""
        if os.environ.get("ATLAS_HERMES_LOCAL", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return False
        return isinstance(self._hermes, HermesMockAdapter)

    def _delegate_to_hermes(self, task: Task) -> None:
        if self._hermes_local_takeover():
            self._merkle.log(
                action="hermes.local_takeover",
                agent="orchestrator",
                result="rerouted",
                risk_level="safe",
                payload={"intent": task.intent[:200]},
                task_id=task.id,
            )
            task.transition(TaskStatus.EXECUTING)
            self._execute_task(task)
            return
        payload = DelegationBuilder.build(
            task_id=task.id,
            intent=task.intent,
            priority=task.priority,
        )
        receipt = self._hermes.enqueue_task(payload)

        if isinstance(self._hermes, HermesMockAdapter):
            signed_payload = self._hermes._queue.get(payload.id, payload)
            mode_note = "Hermes mock (desarrollo)"
            merkle_action = "hermes.mock_queued"
        elif isinstance(self._hermes, HermesRestAdapter):
            signed_payload = self._hermes._sign_payload(payload)
            mode_note = f"Hermes REST ({os.environ.get('HERMES_BASE_URL', '').rstrip('/')})"
            merkle_action = "hermes.delegated"
        else:
            signed_payload = payload
            mode_note = "Hermes adapter desconocido"
            merkle_action = "hermes.delegated"

        entry_cls = __import__(
            "atlas.hermes.hermes", fromlist=["QueueEntry"]
        ).QueueEntry
        self._offline_queue.enqueue(entry_cls(delegation=signed_payload))

        task.transition(TaskStatus.DELEGATED)
        task.result = {
            "delegation_id": receipt.delegation_id,
            "accepted": receipt.accepted,
            "queue_position": receipt.queue_position,
            "note": f"Payload firmado y encolado. {mode_note}.",
        }
        self._merkle.log(
            action=merkle_action,
            agent="hermes_adapter",
            result="success",
            risk_level="safe",
            payload={"delegation_id": receipt.delegation_id, "priority": task.priority},
            task_id=task.id,
        )
        self._bus.publish_type(EventType.HERMES_MESSAGE, {
            "delegation_id": receipt.delegation_id
        }, task.id)

    def _block_task(self, task: Task, reason: str, risk_level: str) -> None:
        self._pipeline_runner._block_task(task, reason, risk_level)

    # ------------------------------------------------------------------
    # Herramientas simples
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Herramientas via AtlasExecutor (FU-1 — ADR-020 wiring completo)
    # ------------------------------------------------------------------
    # Toda accion con efecto externo pasa por: CapabilityIssuer.issue_exec()
    # -> ExecCapability -> AtlasExecutor.execute_exec() -> sandbox + Merkle.
    # Si el issuer rechaza la capability (CapabilityDenied) o el executor
    # falla (ExecutorError) caemos a {"error": ...} para mantener el contrato
    # de retorno hacia _execute_task.

    def _run_via_executor(
        self,
        command: str,
        args: tuple[str, ...],
        *,
        task: Task | None = None,
    ) -> dict[str, Any]:
        return self._pipeline_runner._run_via_executor(command, args, task=task)

    def _run_git_status(self, task: Task | None = None) -> dict[str, Any]:
        return self._git.status(task)

    def _run_git_log(self, task: Task | None = None) -> dict[str, Any]:
        return self._git.log(task)

    def _run_git_diff(self, task: Task | None = None) -> dict[str, Any]:
        return self._git.diff(task)

    def _list_workspace(self) -> dict[str, Any]:
        return self._git.list_workspace()

    # ------------------------------------------------------------------
    # Inicializacion
    # ------------------------------------------------------------------

    def _resolve_workspace(self) -> Path:
        env = os.environ.get("ATLAS_HOME")
        return Path(env).expanduser().resolve() if env else Path.home() / "atlas"

    def _repo_root(self) -> Path | None:
        """Raíz del repo de código de Atlas, para grounding git real.

        El workspace (`~/atlas`) NO es un repo git: es estado de runtime. Las
        preguntas factuales sobre commits/historial deben aterrizarse contra el
        repo de código (`~/proyectos/atlas-core`). Se resuelve por `ATLAS_REPO_ROOT`
        si está, o derivando de la ubicación del paquete. Devuelve None si no es
        un repo git (instalación pip no-editable): entonces las tools git caen al
        comportamiento previo (cwd=workspace).
        """
        env = os.environ.get("ATLAS_REPO_ROOT")
        if env:
            cand = Path(env).expanduser().resolve()
        else:
            try:
                cand = Path(__file__).resolve().parents[3]
            except IndexError:
                return None
        return cand if (cand / ".git").exists() else None

    def _init_dirs(self) -> None:
        for sub in ["projects", "tmp", "skills", "memory/system_context",
                    "memory/error_registry", "memory/approved_patterns",
                    "memory/performance", "memory/audit",
                    "memory/pending_approvals", "memory/gate_h",
                    "memory/truth_snapshots", "config"]:
            (self._workspace / sub).mkdir(parents=True, exist_ok=True)

    def _init_components(self) -> None:
        config_dir = self._workspace / "config"

        # Copiar config defaults si no existen
        self._copy_defaults(config_dir)

        # Governance L0
        GovernanceL0.initialize(config_dir / "governance.json")

        # Permission Profile
        self._permissions = PermissionProfile(
            config_dir / "permissions.yaml",
            self._workspace,
            git_inspect_root=self._repo_root(),
        )

        # Merkle Logger + ADR-024 observability stack
        from atlas.logging.observability import ObservabilityStack

        self._observability = ObservabilityStack(self._workspace)
        self._merkle = self._observability.wrap_merkle(
            MerkleLogger(self._workspace / "memory" / "audit")
        )
        self._cold_update_manager = None
        self._swarm_cycle = None
        self._self_audit_runner = None
        self._knowledge_cve_proposer = None

        from atlas.core.orchestrator_parts.maintenance_facade import MaintenanceFacade
        self._maintenance_facade = MaintenanceFacade(self)

        from atlas.core.orchestrator_parts.pipeline_runner import PipelineRunner
        self._pipeline_runner = PipelineRunner(self)

        # Verificar integridad al arrancar
        ok, msg = self._merkle.verify_chain()
        if not ok:
            raise RuntimeError(f"Merkle chain corrupta al arrancar: {msg}")

        # Verificar governance en disco
        GovernanceL0.get_instance().check_file_integrity()

        # Router
        self._classifier = Classifier()

        # AST Guard
        self._ast_guard = ASTGuard()

        # Sandbox + SSRF Bridge (consumidos por AtlasExecutor)
        self._sandbox = LayeredIsolationSandbox(self._workspace)
        self._ssrf_bridge = SSRFBridge()

        # Capability Issuer + AtlasExecutor (ADR-020, Gate D/D3).
        # Toda accion con efecto externo deberia pasar por aqui — la migracion
        # del pipeline existente queda como follow-up de D3.
        self._capability_issuer = CapabilityIssuer(self._permissions, self._ssrf_bridge)
        self._executor = AtlasExecutor(
            self._capability_issuer,
            self._merkle,
            self._sandbox,
            self._ast_guard,
        )

        # Memoria
        self._system_context = SystemContextLoader.load(
            self._workspace / "memory" / "system_context"
        )
        # ADR-030 block memory: bloques siempre-en-contexto (persona/human/...).
        # render() se inyecta en el prompt de inferencia local.
        self._block_memory = BlockMemory(
            self._workspace / "memory" / "blocks",
            merkle=self._merkle,
        )
        self._error_registry = ErrorRegistry(
            self._workspace / "memory" / "error_registry",
            merkle=self._merkle,
        )
        self._approved_patterns = ApprovedPatternStore(
            self._workspace / "memory" / "approved_patterns",
            merkle=self._merkle,
        )
        self._provider_metrics = ProviderMetricsStore(self._workspace / "memory" / "performance")
        self._tool_registry = ToolRegistry()
        self._gate_h = GateHManager(
            self._workspace,
            self._merkle,
            self._error_registry,
            self._approved_patterns,
        )

        # Hermes (REST si HERMES_BASE_URL + HERMES_API_KEY en .env)
        self._offline_queue = OfflineQueue(self._workspace / "memory")
        self._hermes = self._build_hermes_adapter()

        # Event Bus
        self._bus = EventBus()
        # ADR-012: suscribir sync offline al evento de reconexion con Hermes
        def _on_hermes_reconnected(_evt: Event) -> None:
            self.sync_offline_queue()
        self._bus.subscribe(
            EventType.HERMES_RECONNECTED,
            _on_hermes_reconnected,
        )

        # Approval flow (Gate C / C4-s2)
        self._pending_approval_dir = self._workspace / "memory" / "pending_approvals"
        self._tasks = TaskPersistence(self._pending_approval_dir, self._merkle)
        self._agentic_executor = AgenticExecutor(self)
        self._approvals = ApprovalManager(
            pending_dir=self._pending_approval_dir,
            tasks=self._tasks,
            merkle=self._merkle,
            permissions=self._permissions,
            on_execute=self._execute_task,
            on_resume=self._agentic_executor.resume,
        )

        # ADR-040: todos los puntos de decisión se enrutan por este seam. El
        # decisor se elige por config (ATLAS_DECIDER = human | autonomous |
        # hybrid); default human → paridad con el HITL de hoy. El pivote a
        # autonomía es el flip de env, no tocar los call-sites de nuevo.
        self._decider = make_decider(os.environ.get("ATLAS_DECIDER"))
        # Slice 6: handles de undo (snapshot OMEGA / server MCP) atados al
        # action_hash que el decisor autorizó; revert(action_hash) los consume.
        self._revert_registry = RevertRegistry(
            self._workspace / "memory" / "revert_registry.json"
        )

        self._git = GitReadTools(
            workspace=self._workspace,
            merkle=self._merkle,
            repo_root=self._repo_root,
            run_via_executor=self._run_via_executor,
        )

        # ADR-033: allowlist de auto-aprobación de mutaciones del loop agéntico.
        # VACÍA por defecto → todo mutante sigue exigiendo HITL (seguro). Se
        # puebla vía env ATLAS_AGENTIC_AUTO_APPROVE (csv de nombres de tool) o
        # set_agentic_auto_approve(). NO vive en governance.json (regla 3).
        raw_allow = os.environ.get("ATLAS_AGENTIC_AUTO_APPROVE", "")
        self._agentic_auto_approve: frozenset[str] = frozenset(
            t.strip() for t in raw_allow.split(",") if t.strip()
        )
        # ADR-033: TTL (segundos) para barrer loops suspendidos abandonados.
        # Ausente/<=0 → barrido desactivado (no-op).
        ttl_raw = os.environ.get("ATLAS_AGENTIC_SUSPENSION_TTL", "").strip()
        try:
            self._agentic_suspension_ttl: float | None = (
                float(ttl_raw) if ttl_raw else None
            )
        except ValueError:
            self._agentic_suspension_ttl = None

        # ADR-035: cliente MCP. Config en $ATLAS_MCP_SERVERS o
        # ~/atlas/mcp_servers.json. Si no existe, registry vacío → 0 tools MCP
        # expuestas (Atlas funciona sin MCP). start_all() es perezoso para no
        # arrancar subprocesos en CLI/tests por defecto.
        mcp_config_path = (
            os.environ.get("ATLAS_MCP_SERVERS")
            or str(self._workspace / "mcp_servers.json")
        )
        self._sentinel = SentinelGate(
            self._workspace / "memory" / "sentinel",
            merkle_log=self._merkle.log,
        )
        self._mcp = McpRegistry(
            load_servers(mcp_config_path),
            merkle_log=self._merkle.log,
            sentinel=self._sentinel,
        )
        self._mcp_started = False

        # Telegram bot + monitors (opcionales, se inician con start_*).
        # Tipo declarado a nivel clase (ver bloque al inicio de Orchestrator).
        self._telegram_bot = None
        self._telegram_thread = None
        self._offline_monitor = None
        self._thermal_watchdog = None
        self._gate_f_exec = GateFExecutor(
            workspace=self._workspace,
            executor=self._executor,
            ssrf_bridge=self._ssrf_bridge,
            merkle=self._merkle,
            gate_h=self._gate_h,
            timetravel=lambda: self._timetravel,
            bus=self._bus,
            check_gate_h_allowed=self._check_gate_h_tool_allowed,
            record_receipt=self._record_tool_receipt,
            thermal_blocks=self._thermal_blocks_execution,
        )

        # Gate D pipeline integrado — desactivado por defecto. Se activa con
        # enable_gate_d_pipeline() o con ATLAS_PIPELINE_GATE_D=1 en el env.
        # PIISurrogate es siempre construible (sin dependencias externas).
        self._distiller = None
        self._ghost_replay = None
        self._slm_classifier = None
        self._hybrid = HybridClassifier(
            rule_classifier=self._classifier,
            slm_getter=lambda: self._slm_classifier,
            merkle=self._merkle,
            bypass_threshold=self.SLM_BYPASS_THRESHOLD,
        )
        self._timetravel = None
        self._inference_hub = None
        self._pii_surrogate = PIISurrogate()
        self._vector_store = None
        self._gate_d_enabled = False
        if os.environ.get("ATLAS_PIPELINE_GATE_D", "") == "1":
            self.enable_gate_d_pipeline()

    @property
    def _hermes_mock(self) -> HermesMockAdapter:
        """Compatibilidad tests: cola in-memory solo con mock."""
        if isinstance(self._hermes, HermesMockAdapter):
            return self._hermes
        raise TypeError("HermesMockAdapter no activo — usa HermesRestAdapter (HERMES_BASE_URL)")

    def _build_hermes_adapter(self) -> HermesAdapter:
        base_url = os.environ.get("HERMES_BASE_URL", "").strip()
        api_key = os.environ.get("HERMES_API_KEY", "").strip()
        if base_url and api_key:
            _log.info("Hermes: REST -> %s", base_url)
            return HermesRestAdapter(
                base_url=base_url,
                shared_secret=api_key,
                offline_queue=self._offline_queue,
            )
        _log.warning(
            "Hermes: mock (faltan HERMES_BASE_URL/HERMES_API_KEY). "
            "Carga .env para VPS real."
        )
        return HermesMockAdapter()

    @staticmethod
    def _ghost_cache_eligible(
        sensitivity: str | None,
        *,
        route: RoutingLevel | None = None,
    ) -> bool:
        if (sensitivity or "low") == "high":
            return False
        if route == RoutingLevel.REQUIRES_APPROVAL:
            return False
        return True

    def _acquire_pending_lock(self, task_id: str) -> tuple[int, Path] | tuple[None, None]:
        return self._tasks.acquire_lock(task_id)

    def _thermal_blocks_local_llm(self) -> str | None:
        if self._thermal_watchdog is None:
            return None
        state = self._thermal_watchdog.current_state()
        if state.should_pause_local_llm:
            return str(state.policy)
        return None

    def _thermal_blocks_execution(self) -> str | None:
        if self._thermal_watchdog is None:
            return None
        state = self._thermal_watchdog.current_state()
        if state.emergency:
            return str(state.policy)
        return None

    def _copy_defaults(self, config_dir: Path) -> None:
        """Copia governance.json y permissions.yaml si no existen en el workspace."""
        src_dir = Path(__file__).parent.parent.parent.parent.parent / "config"
        if not src_dir.exists():
            # En instalacion pip el config esta en un sitio diferente;
            # crear defaults minimos inline
            self._write_default_governance(config_dir / "governance.json")
            self._write_default_permissions(config_dir / "permissions.yaml")
            return

        for fname in ("governance.json", "permissions.yaml"):
            dst = config_dir / fname
            src = src_dir / fname
            if not dst.exists() and src.exists():
                import shutil
                shutil.copy2(src, dst)

    def _write_default_governance(self, path: Path) -> None:
        import json as _json
        if path.exists():
            return
        default = {
            "version": "1.0.0",
            "immutable": True,
            "axioms": {
                "transparency": "Atlas siempre puede explicar sus decisiones.",
                "immutability": "El Governance L0 y el Merkle Logger no pueden ser alterados.",
                "empirical_priority": "Los datos observados superan las inferencias.",
                "causal_traceability": "Toda accion tiene una causa registrada.",
                "resource_containment": "Atlas no escala recursos sin autorizacion.",
                "non_maleficence": "Atlas no ejecuta acciones daninas sin aprobacion.",
                "data_sovereignty": "Los datos no salen del PC sin cifrado y consentimiento.",
            },
            "hard_blocks": [
                "Modificar o eliminar entradas del Merkle Logger.",
                "Modificar este archivo governance.json.",
                "Desactivar AST Guard, Sandbox, SSRF Bridge o Thermal Watchdog.",
                "Ejecutar con privilegios elevados.",
            ],
            "hard_block_patterns": [
                r"rm\s+-rf\s*/",
                r"\bsudo\b",
                r"governance\.json",
                r"merkle.{0,20}(disable|deshabilit)",
            ],
        }
        path.write_text(_json.dumps(default, indent=2, ensure_ascii=False))

    def _write_default_permissions(self, path: Path) -> None:
        if path.exists():
            return
        path.write_text(
            "workspace:\n"
            "  auto_write:\n    - tmp/\n"
            "  confirm_write:\n    - projects/\n    - skills/\n    - memory/\n"
            "  read_only:\n    - config/governance.json\n"
            "  read_extended: []\n"
            "absolute_blocks:\n  - ~/.ssh/\n  - ~/.gnupg/\n  - /etc/\n  - /root/\n"
            "system_read_allowed:\n  - /sys/class/hwmon/\n"
            "telegram:\n  authorized_chat_ids: []\n  require_passphrase_for_approve: false\n  passphrase_hash: ''\n"
            "shell_allowlist:\n  - echo\n  - cat\n  - ls\n  - git status\n  - git log\n  - git diff\n"
        )

    def log_session_start(self) -> None:
        """Registra el inicio de una sesion de larga duracion (serve).

        NO se llama en ``__init__``: las invocaciones one-shot del CLI (incluso
        de solo-lectura como ``search``/``audit``) construyen un Orchestrator y
        antes ensuciaban el ledger con un ``session.started`` por comando. Ahora
        solo ``atlas serve`` lo registra explicitamente.
        """
        self._merkle.log(
            action="session.started",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={"version": self.VERSION, "workspace": str(self._workspace)},
        )
        self._bus.publish_type(EventType.SESSION_STARTED, {"version": self.VERSION})
