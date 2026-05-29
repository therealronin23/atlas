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
from atlas.security.pending_store import (
    is_legacy_pending_file,
    unwrap_task_payload,
    wrap_task_payload,
)
from atlas.security.pii_surrogate import PIISurrogate
from atlas.security.sandbox import LayeredIsolationSandbox
from atlas.security.ssrf_bridge import SSRFBridge


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


@dataclass(frozen=True)
class GateFCommand:
    tool: str
    action: str
    args: dict[str, Any]
    requires_approval: bool
    reason: str


class Orchestrator:
    """
    Cerebro ejecutivo de Atlas Core.
    Recibe intenciones → clasifica → enruta → ejecuta → registra.
    """

    VERSION = "0.9.0"

    # Atributos opcionales declarados a nivel clase para que mypy use el tipo
    # Optional desde el principio (evita redef cuando se reasignan a None tras stop_*).
    _telegram_bot: Any
    _telegram_thread: Any
    _offline_monitor: Any
    _thermal_watchdog: Any
    _browser_tool: Any
    _editor_tool: Any
    _vision_loop: Any
    _pending_approval_dir: Path

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

    def self_audit(self) -> Any:
        """Atlas 24h self-audit loop (cold, auditable, no hot self-patch)."""
        if self._self_audit_runner is None:
            from atlas.core.self_audit import SelfAuditRunner

            root = Path(
                os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
            ).expanduser().resolve()
            self._self_audit_runner = SelfAuditRunner(
                root,
                self._merkle,
                health_provider=self.health_report,
            )
        return self._self_audit_runner

    def audit_tail(self, n: int = 20) -> list[dict]:
        return [r.to_dict() for r in self._merkle.tail(n)]

    def tools(self) -> list[dict]:
        return [t.to_dict() for t in self._tool_registry.all()]

    def pending_approvals(self) -> list[dict]:
        with self._approvals_lock:
            tasks = dict(self._pending_approvals)
            for task in self._load_persisted_pending_approvals():
                tasks.setdefault(task.id, task)
            return [self._pending_summary(t) for t in tasks.values()]

    def approve_pending(
        self, task_id: str, approved: bool, *, abort: bool = False
    ) -> dict:
        lock_fd, lock_path = self._acquire_pending_lock(task_id)
        if lock_fd is None:
            return {
                "task_id": task_id,
                "status": "in_progress",
                "error": "otro proceso esta aprobando o ejecutando esta tarea",
            }
        try:
            return self._approve_pending_locked(task_id, approved, abort=abort)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            if lock_path is not None:
                lock_path.unlink(missing_ok=True)

    def _approve_pending_locked(
        self, task_id: str, approved: bool, *, abort: bool = False
    ) -> dict:
        with self._approvals_lock:
            task = self._pending_approvals.pop(task_id, None)

        pending_path = self._pending_approval_dir / f"{task_id}.json"
        executing_path = self._pending_approval_dir / f"{task_id}.executing.json"

        if executing_path.exists():
            return {
                "task_id": task_id,
                "status": "in_progress",
                "error": "la tarea ya esta en ejecucion",
            }

        if task is None:
            if pending_path.exists():
                task = self._load_pending_approval(task_id)
            else:
                task = None

        if task is None:
            return {
                "task_id": task_id,
                "status": "unknown",
                "error": "no pending approval with this id",
            }

        self._merkle.log(
            action="task.approval",
            agent="orchestrator",
            result="approved" if approved else "denied",
            risk_level="high",
            payload={"approved": approved},
            task_id=task.id,
        )

        is_agentic = isinstance(task.metadata.get("agentic_state"), dict)

        if not approved:
            # ADR-032 dec.6/7: para un loop suspendido, un DENY sin abort inyecta
            # una denegación sintética y REANUDA (presión MemGPT → el modelo
            # re-planifica). Con abort=True (o tarea no-agéntica) → CANCELLED.
            if is_agentic and not abort:
                state = task.metadata["agentic_state"]
                state["denied"] = True
                state["deny_reason"] = "human"
                try:
                    pending_path.replace(executing_path)
                except OSError as exc:
                    return {
                        "task_id": task_id,
                        "status": "failed",
                        "error": f"no se pudo reservar ejecucion: {exc}",
                    }
                # No mark_confirmed: las mutaciones denegadas no se ejecutan; se
                # inyecta una denegación sintética y el modelo re-planifica.
                task.transition(TaskStatus.EXECUTING)
                resuspended = False
                try:
                    self._resume_agentic_loop(task)
                    resuspended = task.status == TaskStatus.AWAITING_APPROVAL
                except Exception as e:  # noqa: BLE001
                    task.transition(TaskStatus.FAILED)
                    task.error = str(e)
                finally:
                    executing_path.unlink(missing_ok=True)
                    if not resuspended:
                        pending_path.unlink(missing_ok=True)
                return {
                    "task_id": task.id,
                    "status": task.status.value,
                    "approved": False,
                    "denied_and_resumed": True,
                    "result": task.result,
                }
            task.transition(TaskStatus.CANCELLED)
            task.result = {"approved": False, "message": "Usuario rechazo la accion."}
            self._delete_pending_approval(task.id)
            return {"task_id": task.id, "status": task.status.value, "approved": False}

        try:
            pending_path.replace(executing_path)
        except OSError as exc:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"no se pudo reservar ejecucion: {exc}",
            }

        self._permissions.mark_confirmed(f"task:{task.id}")
        task.transition(TaskStatus.EXECUTING)
        # ADR-032: si el loop se vuelve a suspender (otra mutación más adelante),
        # NO borramos el nuevo <id>.json que _suspend_agentic_loop acaba de
        # persistir; solo limpiamos la reserva .executing.
        resuspended = False
        try:
            self._execute_task(task)
            resuspended = task.status == TaskStatus.AWAITING_APPROVAL
        except Exception as e:
            task.transition(TaskStatus.FAILED)
            task.error = str(e)
        finally:
            executing_path.unlink(missing_ok=True)
            if not resuspended:
                pending_path.unlink(missing_ok=True)

        return {
            "task_id": task.id,
            "status": task.status.value,
            "approved": True,
            "result": task.result,
        }

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
        if browser is not None:
            self._browser_tool = browser
        if editor is not None:
            self._editor_tool = editor
        if vision_loop is not None:
            self._vision_loop = vision_loop

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
        return self._gate_h.status_summary()

    def rebuild_memory(self) -> dict[str, int]:
        return self._gate_h.rebuild_memory(self._vector_store)

    def gate_h_receipts(self, n: int = 20) -> list[dict]:
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
        return self._pii_surrogate

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

            hub = _InferenceHub(mode="auto")
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

    def sync_offline_queue(self) -> dict:
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

    # ------------------------------------------------------------------
    # Pipeline interno
    # ------------------------------------------------------------------

    def _run_pipeline(self, task: Task) -> None:
        if self._gate_d_enabled:
            self._run_pipeline_gate_d(task)
            return

        # 1. Governance L0
        task.transition(TaskStatus.CLASSIFYING)
        gov = GovernanceL0.get_instance()
        if gov.in_emergency_mode:
            self._block_task(task, "Atlas en modo de emergencia.", "critical")
            return

        gate_f = self._parse_gate_f_command(task.intent)
        if gate_f is not None:
            self._route_gate_f_command(task, gate_f)
            return

        # 2. Clasificar
        result = self._classifier.classify(task.intent, sensitivity=task.sensitivity)

        if result.governance_blocked:
            self._block_task(task, result.reason, "critical")
            self._bus.publish_type(EventType.SECURITY_VIOLATION, {
                "reason": result.reason, "intent": task.intent
            }, task.id)
            return

        task.transition(TaskStatus.ROUTING)
        task.route = result.level
        self._merkle.log(
            action="task.classified",
            agent="classifier",
            result="success",
            risk_level="safe",
            payload={"route": result.level.value, "reason": result.reason},
            task_id=task.id,
        )

        # 3. Enrutar
        if result.level == RoutingLevel.BLOCKED:
            self._block_task(task, result.reason, "high")
            return

        if result.level == RoutingLevel.DELEGATE_HERMES:
            self._delegate_to_hermes(task)
            return

        if result.level == RoutingLevel.REQUIRES_APPROVAL:
            task.transition(TaskStatus.AWAITING_APPROVAL)
            task.result = {
                "message": f"Accion requiere aprobacion explicita. Razon: {result.reason}",
                "approved": False,
                "reason": result.reason,
            }
            with self._approvals_lock:
                self._pending_approvals[task.id] = task
            self._persist_pending_approval(task)
            self._merkle.log(
                action="task.routed",
                agent="router",
                result="pending",
                risk_level="high",
                payload={"requires_approval": True, "reason": result.reason},
                task_id=task.id,
            )
            self._bus.publish_type(EventType.APPROVAL_REQUIRED, {
                "task_id": task.id,
                "intent": task.intent,
                "reason": result.reason,
            }, task.id)
            return

        # DETERMINISTIC_TOOL o LOCAL_SAFE → ejecutar
        task.transition(TaskStatus.EXECUTING)
        self._execute_task(task)

    # ------------------------------------------------------------------
    # Gate D — pipeline integrado opt-in
    # ------------------------------------------------------------------

    def _run_pipeline_gate_d(self, task: Task) -> None:
        """
        Variante del pipeline que enlaza las piezas Gate D:

            governance -> ghost.lookup -> hybrid_classify (rule+SLM)
              -> route -> [execute|delegate|approve|block]
              -> ghost.record -> timetravel.record_step
        """
        # 0. Snapshot inicial
        if self._timetravel is None:
            raise RuntimeError(
                "Gate D pipeline: _timetravel no inicializado "
                "(llama a enable_gate_d_pipeline)"
            )
        if self._ghost_replay is None:
            raise RuntimeError(
                "Gate D pipeline: _ghost_replay no inicializado "
                "(llama a enable_gate_d_pipeline)"
            )
        if self._slm_classifier is None:
            raise RuntimeError(
                "Gate D pipeline: _slm_classifier no inicializado "
                "(llama a enable_gate_d_pipeline)"
            )

        self._timetravel.record_step(
            task.id, "received",
            {"intent": task.intent, "source": task.source.value},
        )

        # 1. Governance L0
        task.transition(TaskStatus.CLASSIFYING)
        gov = GovernanceL0.get_instance()
        if gov.in_emergency_mode:
            self._block_task(task, "Atlas en modo de emergencia.", "critical")
            self._timetravel.record_step(task.id, "blocked_emergency", {"intent": task.intent})
            return

        # 2. Ghost cache lookup — solo intenta para tareas que NO requieran
        # aprobacion ni delegacion. Para mantenerlo simple, consultamos
        # siempre antes del classifier: si hit, devolvemos directamente.
        sensitivity = task.sensitivity   # "low" | "medium" | "high"
        ctx_sig = "pipeline-d-v1"

        gate_f = self._parse_gate_f_command(task.intent)
        if gate_f is not None:
            self._route_gate_f_command(task, gate_f)
            self._timetravel.record_step(
                task.id,
                "gate_f_routed",
                {
                    "tool": gate_f.tool,
                    "action": gate_f.action,
                    "requires_approval": gate_f.requires_approval,
                },
            )
            return

        if self._ghost_cache_eligible(sensitivity):
            hit = self._ghost_replay.lookup(task.intent, sensitivity, ctx_sig)
        else:
            hit = None
        if hit is not None:
            # Camino corto: ya estamos en CLASSIFYING desde el paso 1.
            # Cumplimos el state machine CLASSIFYING -> ROUTING -> EXECUTING
            # -> DONE para mantener invariantes.
            task.transition(TaskStatus.ROUTING)
            task.route = RoutingLevel(hit.result.get("route", "local_safe"))
            task.tool_name = hit.result.get("tool_name") or "ghost.cache"
            task.transition(TaskStatus.EXECUTING)
            task.result = hit.result.get("payload", {"cached": True})
            task.transition(TaskStatus.DONE)
            self._merkle.log(
                action="task.ghost_hit",
                agent="orchestrator",
                result="success",
                risk_level="safe",
                payload={"intent": task.intent, "route": task.route.value},
                task_id=task.id,
            )
            self._timetravel.record_step(
                task.id, "ghost_hit",
                {"route": task.route.value, "cached": True},
            )
            self._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)
            return

        # 3. Hybrid classify
        cls = self._hybrid_classify(task.intent, task.sensitivity, task_id=task.id)

        if cls.governance_blocked:
            self._block_task(task, cls.reason, "critical")
            self._bus.publish_type(EventType.SECURITY_VIOLATION, {
                "reason": cls.reason, "intent": task.intent,
            }, task.id)
            self._timetravel.record_step(task.id, "blocked_governance", {"reason": cls.reason})
            return

        task.transition(TaskStatus.ROUTING)
        task.route = cls.level
        winner = "slm" if isinstance(cls.reason, str) and cls.reason.startswith("SLM:") else "rule"
        self._merkle.log(
            action="task.classified",
            agent="classifier_hybrid",
            result="success",
            risk_level="safe",
            payload={
                "route":      cls.level.value,
                "reason":     cls.reason,
                "confidence": cls.confidence,
                "winner":     winner,
            },
            task_id=task.id,
        )
        self._timetravel.record_step(
            task.id, "classified",
            {"route": cls.level.value, "confidence": cls.confidence, "reason": cls.reason},
        )

        # 4. Route
        if cls.level == RoutingLevel.BLOCKED:
            self._block_task(task, cls.reason, "high")
            return

        if cls.level == RoutingLevel.DELEGATE_HERMES:
            self._delegate_to_hermes(task)
            self._timetravel.record_step(task.id, "delegated", {"target": "hermes"})
            return

        if cls.level == RoutingLevel.REQUIRES_APPROVAL:
            task.transition(TaskStatus.AWAITING_APPROVAL)
            task.result = {
                "message": f"Accion requiere aprobacion explicita. Razon: {cls.reason}",
                "approved": False,
                "reason": cls.reason,
            }
            with self._approvals_lock:
                self._pending_approvals[task.id] = task
            self._persist_pending_approval(task)
            self._merkle.log(
                action="task.routed",
                agent="router",
                result="pending",
                risk_level="high",
                payload={"requires_approval": True, "reason": cls.reason},
                task_id=task.id,
            )
            self._bus.publish_type(EventType.APPROVAL_REQUIRED, {
                "task_id": task.id, "intent": task.intent, "reason": cls.reason,
            }, task.id)
            self._timetravel.record_step(task.id, "awaiting_approval", {"reason": cls.reason})
            return

        # 5. Execute (DETERMINISTIC_TOOL o LOCAL_SAFE)
        task.transition(TaskStatus.EXECUTING)
        self._execute_task(task)

        # 6. Ghost record si la ejecucion fue OK (nunca cachear approval/high)
        if task.status == TaskStatus.DONE and self._ghost_cache_eligible(
            sensitivity, route=task.route,
        ):
            try:
                self._ghost_replay.record(
                    task.intent, sensitivity, ctx_sig,
                    {
                        "route":     task.route.value if task.route else "local_safe",
                        "tool_name": task.tool_name,
                        "payload":   task.result or {},
                    },
                    metadata={"task_id": task.id},
                )
            except Exception:  # noqa: BLE001
                # Cache no debe romper la tarea
                pass
            self._timetravel.record_step(
                task.id, "done",
                {"tool": task.tool_name, "route": task.route.value if task.route else None},
            )

    def _hybrid_classify(
        self, intent: str, sensitivity: str | None, *, task_id: str | None = None,
    ) -> ClassificationResult:
        """
        Combina rule-based + SLM con politica de empate refinada:

        1. rule-based corre primero (microsegundos, sin red).
        2. Si governance_blocked OR confidence >= SLM_BYPASS_THRESHOLD (1.0)
           -> se confia en el rule, no se consulta SLM.
        3. Si el rule cae al default LOCAL_SAFE -> se consulta SLM. El SLM
           gana el empate cuando identifica una ruta MAS ESPECIFICA que
           LOCAL_SAFE (incluso con la misma confidence) o cuando su
           confidence es estrictamente mayor.

        Cada consulta al SLM y el ganador final quedan registrados en
        MerkleLogger para metricas.
        """
        rule = self._classifier.classify(intent, sensitivity=sensitivity or "default")
        if rule.governance_blocked or rule.confidence >= self.SLM_BYPASS_THRESHOLD:
            return rule

        assert self._slm_classifier is not None
        slm = self._slm_classifier.classify(intent)
        self._merkle.log(
            action="classify.slm_consulted",
            agent="classifier_hybrid",
            result="success",
            risk_level="safe",
            payload={
                "rule_level":      rule.level.value,
                "rule_confidence": rule.confidence,
                "slm_level":       slm.level.value,
                "slm_confidence":  slm.confidence,
                "slm_mode":        slm.mode,
                "slm_reason":      slm.reason,
            },
            task_id=task_id,
        )

        slm_wins = (
            slm.confidence > rule.confidence
            or (
                slm.level != RoutingLevel.LOCAL_SAFE
                and slm.confidence >= rule.confidence
            )
        )
        if not slm_wins:
            return rule

        # Safety net: only trust the SLM's BLOCKED verdict when the
        # rule-based classifier ALSO suspects something. The rule classifier
        # is deterministic and catches the real constitutional violations
        # (sudo, rm -rf, governance edits). If the rule says "Sin patron
        # especifico" (default LOCAL_SAFE) but the SLM hallucinates BLOCKED
        # for an ambiguous/conversational intent, we degrade to LOCAL_SAFE
        # to avoid bricking the bot on greetings or chitchat.
        if slm.level == RoutingLevel.BLOCKED and rule.level == RoutingLevel.LOCAL_SAFE:
            self._merkle.log(
                action="classify.slm_blocked_overridden",
                agent="classifier_hybrid",
                result="downgraded_to_local_safe",
                risk_level="safe",
                payload={
                    "slm_reason": slm.reason,
                    "rule_reason": rule.reason,
                },
                task_id=task_id,
            )
            return ClassificationResult(
                level=RoutingLevel.LOCAL_SAFE,
                confidence=max(slm.confidence, rule.confidence),
                matched_pattern=None,
                governance_blocked=False,
                reason=(
                    f"SLM proposed BLOCKED but rule classifier saw no danger; "
                    f"downgraded to LOCAL_SAFE. SLM: {slm.reason}"
                ),
            )

        return ClassificationResult(
            level=slm.level,
            confidence=slm.confidence,
            matched_pattern=None,
            governance_blocked=(slm.level == RoutingLevel.BLOCKED),
            reason=f"SLM: {slm.reason} (rule default: {rule.reason})",
        )

    def _execute_task(self, task: Task) -> None:
        """Ejecuta la tarea con la herramienta deterministica correspondiente."""
        if self._thermal_watchdog is not None:
            task.operational_mode = self._thermal_watchdog.current_operational_mode()

        tool_key = task.tool_name or "legacy"
        gate_h_block = self._check_gate_h_tool_allowed(tool_key, task.id)
        if gate_h_block:
            task.transition(TaskStatus.FAILED)
            task.error = gate_h_block
            task.result = {"error": gate_h_block, "paused": True}
            return

        # ADR-032: reanudación de un loop agéntico suspendido. Si la tarea trae
        # estado serializado, la aprobación HITL ya ejecutó mark_confirmed; aquí
        # se ejecutan las mutaciones pendientes y el loop continúa.
        if "agentic_state" in task.metadata:
            self._resume_agentic_loop(task)
            return

        if "gate_f_command" in task.metadata:
            self._execute_gate_f_task(task)
            return

        intent_lower = task.intent.lower()

        # Mapear intencion a herramienta
        if any(kw in intent_lower for kw in ["estado de atlas", "atlas status"]):
            task.tool_name = "atlas.status"
            task.result = self.status().__dict__
        elif any(kw in intent_lower for kw in ["git status", "estado git"]):
            task.tool_name = "git.status"
            task.result = self._run_git_status(task)
        elif any(
            kw in intent_lower
            for kw in [
                "git log",
                "historial",
                "commit",  # cubre "commits", "último commit", "recent commits"
                "últimos cambios",
                "ultimos cambios",
                "recent commits",
            ]
        ):
            # Grounding: preguntas factuales sobre commits van a la tool git real,
            # NO a inferencia LOCAL_SAFE (que inventaría hashes/mensajes).
            task.tool_name = "git.log"
            task.result = self._run_git_log(task)
        elif any(
            kw in intent_lower
            for kw in ["git diff", "diferencias", "qué cambió", "que cambio", "what changed"]
        ):
            task.tool_name = "git.diff"
            task.result = self._run_git_diff(task)
        elif any(kw in intent_lower for kw in ["lista", "listar", "list"]):
            task.tool_name = "fs.list_dir"
            task.result = self._list_workspace()
        else:
            # LOCAL_SAFE: si pipeline Gate D activo + InferenceHub disponible,
            # responder via inferencia real con MemoryDistiller + PIISurrogate.
            # Si no, fallback al passthrough informativo de v0.1.
            if self._gate_d_enabled and self._inference_hub is not None:
                self._execute_local_safe_via_inference(task)
            else:
                task.tool_name = "local_safe.passthrough"
                task.result = {
                    "message": "Tarea LOCAL_SAFE recibida. InferenceHub no inyectado en este Orchestrator.",
                    "intent": task.intent,
                }

        # ADR-032: el loop agéntico pudo SUSPENDERSE durante la inferencia
        # (mutación pendiente de aprobación). En ese caso la tarea ya está
        # AWAITING_APPROVAL y persistida; no la cerremos como DONE.
        if task.status == TaskStatus.AWAITING_APPROVAL:
            return

        self._merkle.log(
            action="tool.invoked",
            agent=task.tool_name or "unknown",
            result="success",
            risk_level="safe",
            payload={"tool": task.tool_name},
            task_id=task.id,
        )
        self._record_tool_receipt(
            task,
            purpose="Ejecucion de herramienta determinista",
            approval_path="explicit" if task.route == RoutingLevel.REQUIRES_APPROVAL else "automatic",
        )
        task.transition(TaskStatus.DONE)
        self._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)

    # ------------------------------------------------------------------
    # Gate F — Browser / Editor / VisionLoop routing
    # ------------------------------------------------------------------

    def _parse_gate_f_command(self, intent: str) -> GateFCommand | None:
        """
        Parser minimo y explicito para Gate F.

        Formatos aceptados:
          - browser navigate <url>
          - browser screenshot [name]
          - browser extract
          - browser click <selector>
          - browser fill <selector> :: <value>
          - editor read <path>
          - editor write <path> :: <content>
          - editor run <working_dir> :: <command>
          - editor apply_diff <path> :: <unified diff>
          - editor open <path>
          - vision propose [screenshot_name]
        """
        text = intent.strip()
        if not text:
            return None

        head, sep, tail = text.partition(" ")
        if not sep:
            return None
        tool = head.lower()
        if tool not in {"browser", "editor", "vision"}:
            return None

        action, _, rest = tail.strip().partition(" ")
        action = action.lower()
        rest = rest.strip()

        if tool == "browser":
            return self._parse_browser_command(action, rest)
        if tool == "editor":
            return self._parse_editor_command(action, rest)
        return self._parse_vision_command(action, rest)

    def _parse_browser_command(self, action: str, rest: str) -> GateFCommand | None:
        if action in {"navigate", "nav", "open", "abrir", "navegar"} and rest:
            return GateFCommand(
                tool="browser",
                action="navigate",
                args={"url": rest},
                requires_approval=True,
                reason="Browser navigation touches an external page.",
            )
        if action in {"screenshot", "captura"}:
            return GateFCommand(
                tool="browser",
                action="screenshot",
                args={"name": rest or None},
                requires_approval=False,
                reason="Browser screenshot observes current page only.",
            )
        if action in {"extract", "extrae", "leer"}:
            return GateFCommand(
                tool="browser",
                action="extract",
                args={},
                requires_approval=False,
                reason="Browser extract observes current page only.",
            )
        if action == "click" and rest:
            return GateFCommand(
                tool="browser",
                action="click",
                args={"selector": rest},
                requires_approval=True,
                reason="Browser click mutates page state.",
            )
        if action == "fill" and rest:
            selector, value = self._split_payload(rest)
            if selector and value is not None:
                return GateFCommand(
                    tool="browser",
                    action="fill",
                    args={"selector": selector, "value": value},
                    requires_approval=True,
                    reason="Browser fill mutates page state.",
                )
        return None

    def _parse_editor_command(self, action: str, rest: str) -> GateFCommand | None:
        if action in {"read", "lee", "leer"} and rest:
            return GateFCommand(
                tool="editor",
                action="read",
                args={"path": rest},
                requires_approval=False,
                reason="Editor read is observational and still goes through AtlasExecutor.",
            )
        if action in {"write", "escribe"} and rest:
            path, content = self._split_payload(rest)
            if path and content is not None:
                return GateFCommand(
                    tool="editor",
                    action="write",
                    args={"path": path, "content": content},
                    requires_approval=True,
                    reason="Editor write changes filesystem state.",
                )
        if action in {"run", "run_task"} and rest:
            working_dir, command = self._split_payload(rest)
            if working_dir and command is not None:
                generated = self._is_generated_tool_run(working_dir, command)
                return GateFCommand(
                    tool="editor",
                    action="run",
                    args={
                        "working_dir": working_dir,
                        "command": command,
                        "generated": generated,
                    },
                    requires_approval=True,
                    reason="Editor run executes a command."
                    + (" (Gate H generated audit)" if generated else ""),
                )
        if action == "apply_diff" and rest:
            path, diff_text = self._split_payload(rest)
            if path and diff_text is not None:
                return GateFCommand(
                    tool="editor",
                    action="apply_diff",
                    args={"path": path, "diff": diff_text},
                    requires_approval=True,
                    reason="Editor apply_diff changes filesystem state.",
                )
        if action == "open" and rest:
            return GateFCommand(
                tool="editor",
                action="open",
                args={"path": rest},
                requires_approval=True,
                reason="Editor open launches a host process.",
            )
        return None

    def _parse_vision_command(self, action: str, rest: str) -> GateFCommand | None:
        if action in {"propose", "proposal", "observa", "observe"}:
            return GateFCommand(
                tool="vision",
                action="propose",
                args={"screenshot_name": rest or "vision_loop"},
                requires_approval=False,
                reason="Vision loop proposes an action but does not execute it.",
            )
        return None

    def _split_payload(self, rest: str) -> tuple[str, str | None]:
        left, sep, right = rest.partition("::")
        if not sep:
            return rest.strip(), None
        return left.strip(), right.lstrip()

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
            task.transition(TaskStatus.AWAITING_APPROVAL)
            task.result = {
                "message": f"Accion Gate F requiere aprobacion explicita. Razon: {command.reason}",
                "approved": False,
                "reason": command.reason,
                "tool": task.tool_name,
            }
            with self._approvals_lock:
                self._pending_approvals[task.id] = task
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

        task.transition(TaskStatus.EXECUTING)
        self._execute_gate_f_task(task)

    def _execute_gate_f_task(self, task: Task) -> None:
        tool_key = task.tool_name or "gate_f"
        gate_h_block = self._check_gate_h_tool_allowed(tool_key, task.id)
        if gate_h_block:
            task.transition(TaskStatus.FAILED)
            task.error = gate_h_block
            task.result = {"error": task.error, "paused": True}
            return

        thermal_block = self._thermal_blocks_execution()
        if thermal_block:
            task.transition(TaskStatus.FAILED)
            task.error = thermal_block
            task.result = {"error": thermal_block, "thermal": True}
            return

        raw = task.metadata.get("gate_f_command")
        if not isinstance(raw, dict):
            raise RuntimeError("Gate F command metadata missing or invalid")
        tool = str(raw.get("tool", ""))
        action = str(raw.get("action", ""))
        args = raw.get("args", {})
        if not isinstance(args, dict):
            raise RuntimeError("Gate F command args missing or invalid")

        try:
            if tool == "browser":
                result = self._execute_browser_command(action, args)
            elif tool == "editor":
                result = self._execute_editor_command(action, args, task=task)
            elif tool == "vision":
                result = self._execute_vision_command(action, args)
            else:
                raise RuntimeError(f"Unknown Gate F tool: {tool}")
        except Exception as e:
            self._merkle.log(
                action="gate_f.tool_failed",
                agent=f"{tool}.{action}" if tool and action else "gate_f",
                result="failure",
                risk_level="moderate",
                payload={"error": str(e)[:500]},
                task_id=task.id,
            )
            self._gate_h.record_failure(
                tool_name=task.tool_name or "gate_f",
                failure_type="gate_f_execution",
                error=str(e),
                context={"tool": tool, "action": action, "args": args},
                task_id=task.id,
            )
            if self._timetravel is not None:
                self._timetravel.record_step(
                    task.id, "gate_h_failure",
                    {"tool": tool, "error": str(e)[:200]},
                )
            task.transition(TaskStatus.FAILED)
            task.error = str(e)
            self._bus.publish_type(EventType.TOOL_FAILED, {
                "task_id": task.id, "tool": task.tool_name, "error": str(e),
            }, task.id)
            return

        task.result = result
        self._merkle.log(
            action="tool.invoked",
            agent=task.tool_name or "gate_f",
            result="success",
            risk_level="medium" if task.route == RoutingLevel.REQUIRES_APPROVAL else "safe",
            payload={"tool": task.tool_name},
            task_id=task.id,
        )
        self._record_tool_receipt(
            task,
            purpose=f"Gate F {tool}.{action}",
            safety_checks=["PermissionProfile", "AtlasExecutor", "GateH", "MerkleLogger"],
            approval_path="explicit" if task.route == RoutingLevel.REQUIRES_APPROVAL else "automatic",
        )
        task.transition(TaskStatus.DONE)
        self._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)

    def _execute_browser_command(self, action: str, args: dict[str, Any]) -> dict:
        browser = self._get_browser_tool()
        if action == "navigate":
            return browser.navigate(str(args["url"])).__dict__
        if action == "screenshot":
            return browser.screenshot(args.get("name")).__dict__
        if action == "extract":
            return browser.extract().__dict__
        if action == "click":
            return browser.click(str(args["selector"])).__dict__
        if action == "fill":
            return browser.fill(str(args["selector"]), str(args["value"])).__dict__
        raise RuntimeError(f"Unsupported browser action: {action}")

    def _execute_editor_command(
        self,
        action: str,
        args: dict[str, Any],
        *,
        task: Task | None = None,
    ) -> dict:
        editor = self._get_editor_tool()
        clearance = f"task:{task.id}" if task is not None else None
        if action == "read":
            return editor.read_file(self._resolve_gate_f_path(str(args["path"]))).__dict__
        if action == "write":
            return editor.write_file(
                self._resolve_gate_f_path(str(args["path"])),
                str(args["content"]),
                clearance=clearance,
            ).__dict__
        if action == "run":
            return self._execute_editor_run_command(
                task, args, editor, clearance=clearance,
            )
        if action == "apply_diff":
            return editor.apply_diff(
                self._resolve_gate_f_path(str(args["path"])),
                str(args["diff"]),
                clearance=clearance,
            ).__dict__
        if action == "open":
            return editor.open_project(self._resolve_gate_f_path(str(args["path"]))).__dict__
        raise RuntimeError(f"Unsupported editor action: {action}")

    def _execute_vision_command(self, action: str, args: dict[str, Any]) -> dict:
        if action != "propose":
            raise RuntimeError(f"Unsupported vision action: {action}")
        proposal = self._get_vision_loop().propose_next(
            str(args.get("screenshot_name") or "vision_loop")
        )
        payload = proposal.__dict__
        if proposal.requires_approval:
            self._merkle.log(
                action="vision.proposal_requires_approval",
                agent="orchestrator",
                result="pending",
                risk_level="medium",
                payload=payload,
            )
        return payload

    def _execute_editor_run_command(
        self,
        task: Task | None,
        args: dict[str, Any],
        editor: Any,
        *,
        clearance: str | None,
    ) -> dict[str, Any]:
        working_dir = self._resolve_gate_f_path(str(args["working_dir"]))
        command = str(args["command"])
        generated = bool(args.get("generated"))

        if generated and task is not None:
            self._record_tool_receipt(
                task,
                purpose="Generated editor run (pre-exec)",
                safety_checks=["GeneratedCodePolicy", "AST Guard", "AtlasExecutor"],
                approval_path="explicit",
            )
            self._validate_generated_script_source(command, working_dir)
            self._gate_h.assert_generated_reusable(command, task_id=task.id)

        result = editor.run_task(working_dir, command, clearance=clearance)
        out: dict[str, Any] = dict(result.__dict__)
        if generated and task is not None:
            out = self._execute_generated_editor_run(
                task,
                {"working_dir": str(working_dir), "command": command},
                out,
            )
        return out

    def _validate_generated_script_source(self, command: str, working_dir: Path) -> None:
        import shlex

        policy = GeneratedCodePolicy()
        for part in shlex.split(command):
            if not part.endswith(".py"):
                continue
            script = Path(part)
            if not script.is_absolute():
                script = (working_dir / script).resolve()
            if script.is_file():
                check = policy.check_generated_source(script.read_text(encoding="utf-8"))
                if not check.passed:
                    raise RuntimeError(f"GeneratedCodePolicy: {check.reason}")

    def _execute_generated_editor_run(
        self,
        task: Task,
        input_data: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = task.tool_name or "editor.run"
        validation = self._gate_h.audit_generated_run(
            tool_name,
            input_data,
            result,
            task_id=task.id,
            promote=True,
        )
        result = dict(result)
        result["gate_h"] = {
            "valid": validation.valid,
            "reasons": list(validation.reasons),
        }
        if not validation.valid:
            task.error = "; ".join(validation.reasons)
        return result

    def _resolve_gate_f_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (self._workspace / path).resolve()

    def _get_browser_tool(self) -> Any:
        if self._browser_tool is None:
            from atlas.tools.browser import BrowserTool  # noqa: PLC0415

            self._browser_tool = BrowserTool(
                workspace=self._workspace,
                bridge=self._ssrf_bridge,
                merkle=self._merkle,
                allow_private_network=False,
            )
        return self._browser_tool

    def _get_editor_tool(self) -> Any:
        if self._editor_tool is None:
            from atlas.tools.editor import EditorTool  # noqa: PLC0415

            self._editor_tool = EditorTool(
                workspace=self._workspace,
                executor=self._executor,
            )
        return self._editor_tool

    def _get_vision_loop(self) -> Any:
        if self._vision_loop is None:
            from atlas.tools.computer_use.vision_loop import VisionLoop  # noqa: PLC0415

            self._vision_loop = VisionLoop(
                browser=self._get_browser_tool(),
                merkle=self._merkle,
            )
        return self._vision_loop

    # ------------------------------------------------------------------
    # Pending approval persistence (Gate G)
    # ------------------------------------------------------------------

    def _pending_summary(self, task: Task) -> dict:
        return {
            "task_id": task.id,
            "intent": task.intent,
            "reason": (task.result or {}).get("reason", "") if isinstance(task.result, dict) else "",
            "tool": task.tool_name,
            "route": task.route.value if task.route else None,
            "created_at": task.created_at,
        }

    def _persist_pending_approval(self, task: Task) -> None:
        try:
            self._pending_approval_dir.mkdir(parents=True, exist_ok=True)
            path = self._pending_approval_dir / f"{task.id}.json"
            task_payload = self._serialize_task(task)
            envelope = wrap_task_payload(task_payload)
            path.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._merkle.log(
                action="approval.persisted",
                agent="orchestrator",
                result="success",
                risk_level="safe",
                payload={"task_id": task.id, "path": str(path)},
                task_id=task.id,
            )
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.persist_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task.id, "error": str(exc)[:500]},
                task_id=task.id,
            )

    def _load_pending_approval(self, task_id: str) -> Task | None:
        path = self._pending_approval_dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("pending file is not a JSON object")
            if is_legacy_pending_file(raw):
                self._merkle.log(
                    action="approval.legacy_rejected",
                    agent="orchestrator",
                    result="failure",
                    risk_level="high",
                    payload={
                        "task_id": task_id,
                        "hint": "re-submit task; pending v1 requires HMAC envelope",
                    },
                    task_id=task_id,
                )
                return None
            task_data = unwrap_task_payload(raw)
            if task_data is None:
                self._merkle.log(
                    action="approval.tamper_detected",
                    agent="orchestrator",
                    result="failure",
                    risk_level="critical",
                    payload={"task_id": task_id, "path": str(path)},
                    task_id=task_id,
                )
                return None
            return self._deserialize_task(task_data)
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.load_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task_id, "error": str(exc)[:500]},
            )
            return None

    def _load_persisted_pending_approvals(self) -> list[Task]:
        if not self._pending_approval_dir.exists():
            return []
        tasks: list[Task] = []
        for path in sorted(self._pending_approval_dir.glob("*.json")):
            if ".executing" in path.name:
                continue
            task = self._load_pending_approval(path.stem)
            if task is not None:
                tasks.append(task)
        return tasks

    def _delete_pending_approval(self, task_id: str) -> None:
        try:
            (self._pending_approval_dir / f"{task_id}.json").unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.delete_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task_id, "error": str(exc)[:500]},
            )

    def _serialize_task(self, task: Task) -> dict:
        data = task.to_dict()
        data["operational_mode"] = task.operational_mode.value
        data["metadata"] = task.metadata
        return data

    def _deserialize_task(self, data: dict) -> Task:
        task = Task(
            intent=str(data["intent"]),
            source=TaskSource(str(data.get("source", TaskSource.CLI.value))),
            id=str(data["id"]),
            priority=int(data.get("priority", 3)),
            sensitivity=str(data.get("sensitivity", "low")),
            action=str(data.get("action", "")),
            operational_mode=OperationalMode(str(data.get("operational_mode", OperationalMode.NORMAL.value))),
            parent_id=data.get("parent_id"),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
            metadata=dict(data.get("metadata") or {}),
        )
        task.status = TaskStatus(str(data.get("status", TaskStatus.AWAITING_APPROVAL.value)))
        route = data.get("route")
        task.route = RoutingLevel(str(route)) if route else None
        task.tool_name = data.get("tool_name")
        task.result = data.get("result")
        task.error = data.get("error")
        task.audit_hash = data.get("audit_hash")
        return task

    def _execute_local_safe_via_inference(self, task: Task) -> None:
        """
        Ejecuta una tarea LOCAL_SAFE invocando al InferenceHub.

        Pipeline:
          1. PIISurrogate.redact sobre el intent (no salen datos sensibles).
          2. MemoryDistiller.build_context para curar el contexto del prompt
             si hay vector_store conectado (sin vector_store cae a system+intent).
          3. PIISurrogate.redact tambien sobre el contexto.
          4. InferenceHub.infer con prompt + context redactados.
          5. PIISurrogate.restore sobre el texto de respuesta.
          6. Si la inferencia falla, fallback a passthrough con error.

        El resultado se guarda en task.result con la respuesta restaurada y
        metadatos del proveedor (provider, model, latency, tokens).
        """
        thermal_policy = self._thermal_blocks_local_llm()
        if thermal_policy:
            task.tool_name = "local_safe.thermal_blocked"
            task.result = {
                "error": thermal_policy,
                "message": "Inferencia local pausada por modo termico (DEGRADED/OMEGA).",
                "thermal": True,
            }
            return

        # Lazy imports para evitar cargar litellm si nadie usa esto
        from atlas.core.inference_hub import InferenceLevel, InferenceRequest
        from atlas.memory.distiller import ChunkSource

        # 1. Redact intent
        redacted_intent = self._pii_surrogate.redact(task.intent)

        # 2. Distill context. Sin vector_store, gather_relevant devuelve [];
        # el contexto sera basicamente el system context (si esta cargado).
        system_text = ""
        if self._system_context is not None:
            system_text = self._system_context.as_system_context()
        if self._distiller is not None and system_text:
            ctx_text, _ = self._distiller.build_context(
                query=task.intent,
                system_chunks=[system_text] if system_text else None,
            )
        else:
            ctx_text = system_text

        # 2b. ADR-030: bloques de core memory siempre-en-contexto, antes del
        # contexto archival. Vacio si no hay bloques (no inyecta nada).
        blocks_text = self._block_memory.render()
        if blocks_text:
            ctx_text = f"{blocks_text}\n\n{ctx_text}" if ctx_text else blocks_text

        # 3. Redact context
        redacted_ctx = self._pii_surrogate.redact(ctx_text)

        # 4. Inference call. ADR-031: exponemos herramientas de grounding al
        # modelo. La PRIMERA llamada usa prompt+context (idéntico a v0.x: si el
        # modelo no pide tools, una sola iteración → comportamiento previo).
        tool_specs = self._agentic_tool_specs()
        request = InferenceRequest(
            prompt=redacted_intent.text,
            level=InferenceLevel.L1,
            context=redacted_ctx.text,
            max_tokens=512,
            temperature=0.3,
            task_id=task.id,
            tools=tool_specs,
        )
        response = self._inference_hub.infer(request)

        if not response.success:
            self._record_inference_failure(task, response)
            return

        # ADR-031: loop agéntico. Si el modelo pidió herramientas, las ejecutamos
        # (auditadas), reinyectamos resultados y volvemos a llamar hasta respuesta
        # final o tope de iteraciones. Las preguntas factuales se contestan con
        # datos reales (git, fs, blocks) en vez de alucinarse.
        iterations = 0
        tools_used: list[str] = []
        if response.tool_calls:
            messages: list[dict[str, Any]] = []
            if redacted_ctx.text:
                messages.append({"role": "system", "content": redacted_ctx.text})
            messages.append({"role": "user", "content": redacted_intent.text})

            # ADR-032: el loop puede suspenderse si el modelo pide una mutación
            # de host (browser/editor). En ese caso _drive_agentic_loop devuelve
            # None tras dejar la tarea AWAITING_APPROVAL; reanudaremos en
            # approve_pending. Si termina, devuelve (response, iterations).
            loop_result = self._drive_agentic_loop(
                task, messages, response, tool_specs, iterations, tools_used,
            )
            if loop_result is None:
                return
            response, iterations = loop_result

        # 5. Restore PII en la respuesta usando ambos mappings
        combined: dict[str, str] = {}
        combined.update(redacted_intent.mapping)
        combined.update(redacted_ctx.mapping)
        restored = self._pii_surrogate.restore(response.text, combined)

        task.tool_name = "inference_hub.complete"
        task.result = {
            "text":         restored,
            "provider":     response.provider,
            "model":        response.model,
            "latency_ms":   response.latency_ms,
            "tokens_used":  response.tokens_used,
            "mode":         response.mode,
            "pii_redacted": len(redacted_intent.matches) + len(redacted_ctx.matches),
            "iterations":   iterations,
            "tools_used":   tools_used,
        }
        self._merkle.log(
            action="inference.completed",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={
                "provider":     response.provider,
                "model":        response.model,
                "latency_ms":   response.latency_ms,
                "tokens_used":  response.tokens_used,
                "pii_redacted": len(redacted_intent.matches) + len(redacted_ctx.matches),
                "iterations":   iterations,
                "tools_used":   tools_used,
            },
            task_id=task.id,
        )

    def _record_inference_failure(self, task: Task, response: Any) -> None:
        task.tool_name = "inference_hub.failed"
        task.result = {
            "message": f"InferenceHub no devolvio respuesta: {response.error}",
            "provider": response.provider,
            "intent":   task.intent,
        }
        self._merkle.log(
            action="inference.failed",
            agent="orchestrator",
            result="failure",
            risk_level="moderate",
            payload={"provider": response.provider, "error": response.error},
            task_id=task.id,
        )

    # ------------------------------------------------------------------
    # ADR-031 — herramientas del loop agéntico
    # ------------------------------------------------------------------

    def _agentic_tool_specs(self) -> list[dict[str, Any]]:
        """Especificaciones de herramientas (formato OpenAI/LiteLLM) que el
        modelo puede invocar durante el loop agéntico. v1: lectura/grounding
        (git, fs, status, blocks) + escritura de block memory (auto-edición,
        ADR-030 fase 2). Las herramientas mutantes de host (browser/editor)
        siguen por el flujo AWAITING_APPROVAL, fuera del loop."""
        def fn(
            name: str,
            desc: str,
            props: dict[str, Any] | None = None,
            required: list[str] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": props or {},
                        "required": required or [],
                    },
                },
            }

        return [
            fn("git_log", "Últimos commits reales del repo (git log --oneline -10). Úsalo para preguntas sobre commits o historial; nunca inventes hashes."),
            fn("git_status", "Estado git real del árbol de trabajo (git status --short)."),
            fn("git_diff", "Diff resumido real (git diff --stat)."),
            fn("list_workspace", "Lista los archivos del workspace de Atlas."),
            fn("atlas_status", "Estado del runtime Atlas (componentes, versión)."),
            fn("read_memory_blocks", "Lee los bloques de core memory siempre-en-contexto."),
            fn(
                "edit_memory_block",
                "Reemplaza por completo el valor de un bloque de core memory.",
                {"label": {"type": "string"}, "value": {"type": "string"}},
                ["label", "value"],
            ),
            fn(
                "append_memory_block",
                "Añade texto al final de un bloque de core memory existente.",
                {"label": {"type": "string"}, "text": {"type": "string"}},
                ["label", "text"],
            ),
            # ADR-032: herramientas mutantes de host. El modelo puede pedirlas
            # dentro del razonamiento; el loop se SUSPENDE y pide aprobación
            # humana inline antes de ejecutarlas (HITL).
            fn(
                "editor_write",
                "Escribe (sobrescribe) un archivo. MUTA el host: requiere aprobación humana inline.",
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
            ),
            fn(
                "editor_apply_diff",
                "Aplica un diff unificado a un archivo. MUTA el host: requiere aprobación inline.",
                {"path": {"type": "string"}, "diff": {"type": "string"}},
                ["path", "diff"],
            ),
            fn(
                "editor_run",
                "Ejecuta un comando en un working_dir (sandbox). MUTA el host: requiere aprobación inline.",
                {"working_dir": {"type": "string"}, "command": {"type": "string"}},
                ["working_dir", "command"],
            ),
            fn(
                "browser_navigate",
                "Navega el browser a una URL. MUTA estado de host: requiere aprobación inline.",
                {"url": {"type": "string"}},
                ["url"],
            ),
            fn(
                "browser_click",
                "Hace click en un selector. MUTA estado de host: requiere aprobación inline.",
                {"selector": {"type": "string"}},
                ["selector"],
            ),
            fn(
                "browser_fill",
                "Rellena un campo de formulario. MUTA estado de host: requiere aprobación inline.",
                {"selector": {"type": "string"}, "value": {"type": "string"}},
                ["selector", "value"],
            ),
        ]

    # ADR-032: herramientas del loop que mutan el host. Reusar una sola fuente
    # de verdad de riesgo (no duplicar listas). El resto (git/fs/status/blocks)
    # son lectura/auto-edición y corren inline sin suspender.
    _AGENTIC_MUTATING_TOOLS = frozenset({
        "editor_write", "editor_apply_diff", "editor_run",
        "browser_navigate", "browser_click", "browser_fill",
    })

    def _agentic_tool_kind(self, name: str) -> str:
        """ADR-032: clasifica una herramienta del loop como 'read' (corre inline)
        o 'mutate' (suspende el loop para aprobación HITL)."""
        return "mutate" if name in self._AGENTIC_MUTATING_TOOLS else "read"

    def _stringify_tool_result(self, result: Any) -> str:
        if isinstance(result, dict):
            if "stdout" in result:
                out = (result.get("stdout") or "").strip()
                repo = result.get("repo_root")
                # Procedencia explícita: que el gemelo no invente la ruta del repo.
                prefix = f"repo_root: {repo}\n" if repo else ""
                return (prefix + out) if out else (prefix + "(salida vacía)")
            return json.dumps(result, ensure_ascii=False, default=str)[:2000]
        return str(result)

    def _dispatch_agentic_tool(
        self, name: str, arguments: str, task: Task
    ) -> str:
        """Ejecuta una herramienta pedida por el modelo y devuelve su resultado
        como texto. Cada invocación se audita. Los errores (incl. límite de
        bloque excedido = presión MemGPT) se devuelven como texto para que el
        modelo reaccione, no como excepción."""
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}

        self._merkle.log(
            action="tool.invoked",
            agent="orchestrator.agentic",
            result="ok",
            risk_level="safe",
            payload={"tool": name},
            task_id=task.id,
        )

        try:
            if name == "git_log":
                return self._stringify_tool_result(self._run_git_log(task))
            if name == "git_status":
                return self._stringify_tool_result(self._run_git_status(task))
            if name == "git_diff":
                return self._stringify_tool_result(self._run_git_diff(task))
            if name == "list_workspace":
                return self._stringify_tool_result(self._list_workspace())
            if name == "atlas_status":
                return self._stringify_tool_result(self.status().__dict__)
            if name == "read_memory_blocks":
                return self._block_memory.render() or "(sin bloques de memoria)"
            if name == "edit_memory_block":
                block = self._block_memory.set(args["label"], args["value"])
                return f"ok: bloque '{block.label}' actualizado ({block.chars} chars)"
            if name == "append_memory_block":
                block = self._block_memory.append(args["label"], args["text"])
                return f"ok: bloque '{block.label}' ampliado ({block.chars} chars)"
            return f"error: herramienta desconocida '{name}'"
        except BlockLimitExceeded as exc:
            return f"error: límite del bloque excedido — resume o acorta el contenido. {exc}"
        except (BlockNotFound, BlockMemoryError) as exc:
            return f"error: {exc}"
        except KeyError as exc:
            return f"error: falta argumento {exc}"
        except Exception as exc:  # noqa: BLE001 — devolvemos el error al modelo
            return f"error: {type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    # ADR-032 — loop agéntico suspendible/reanudable (HITL inline)
    # ------------------------------------------------------------------

    def _drive_agentic_loop(
        self,
        task: Task,
        messages: list[dict[str, Any]],
        response: Any,
        tool_specs: list[dict[str, Any]],
        iterations: int,
        tools_used: list[str],
    ) -> tuple[Any, int] | None:
        """Maneja el loop agéntico (ADR-031) con suspensión por mutación (ADR-032).

        Las herramientas de lectura corren inline; si el modelo pide una o más
        herramientas mutantes en un turno, se agrupan, el loop se SUSPENDE
        (AWAITING_APPROVAL, estado persistido) y devuelve None. Si el loop
        termina con normalidad devuelve (response_final, iterations). Si la
        inferencia falla, registra el fallo y devuelve None.

        El presupuesto `max_iters` cuenta a través de suspensiones: `iterations`
        entra con el valor acumulado y persiste en el estado serializado.
        """
        from atlas.core.inference_hub import InferenceLevel, InferenceRequest

        max_iters = 5
        while response.tool_calls and iterations < max_iters:
            iterations += 1
            messages.append({
                "role": "assistant",
                "content": response.text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in response.tool_calls
                ],
            })
            pending_mutations: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                tools_used.append(tc["name"])
                if self._agentic_tool_kind(tc["name"]) == "mutate":
                    # ADR-032 dec.5: agrupar TODAS las mutaciones del turno en una
                    # sola aprobación. No se ejecutan aún; se persiste el tool_call.
                    pending_mutations.append({
                        "id": tc["id"],
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    })
                    continue
                raw_result = self._dispatch_agentic_tool(
                    tc["name"], tc["arguments"], task
                )
                # Redactar PII del resultado antes de devolverlo al modelo.
                safe_result = self._pii_surrogate.redact(raw_result).text
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": safe_result,
                })

            if pending_mutations:
                self._suspend_agentic_loop(
                    task, messages, iterations, tools_used, pending_mutations,
                )
                return None

            request = InferenceRequest(
                prompt="",
                level=InferenceLevel.L1,
                messages=messages,
                tools=tool_specs,
                max_tokens=512,
                temperature=0.3,
                task_id=task.id,
            )
            response = self._inference_hub.infer(request)
            if not response.success:
                self._record_inference_failure(task, response)
                return None

        return response, iterations

    def _suspend_agentic_loop(
        self,
        task: Task,
        messages: list[dict[str, Any]],
        iterations: int,
        tools_used: list[str],
        pending_mutations: list[dict[str, Any]],
    ) -> None:
        """ADR-032: serializa el estado del loop y deja la tarea AWAITING_APPROVAL.

        El `messages` array ES la memoria del loop (dec.3). Se persiste en el
        registro de pending approval existente bajo `agentic_state` (dec.4); ya
        viene redactado de PII (los tool results se redactan antes de añadirse),
        así que no persistimos PII en claro. La reanudación ocurre en
        approve_pending al detectar `agentic_state`.
        """
        names = [m["name"] for m in pending_mutations]
        reason = (
            f"El razonamiento agéntico requiere ejecutar {len(names)} "
            f"mutación(es) de host: {', '.join(names)}"
        )
        task.metadata["agentic_state"] = {
            "messages": messages,
            "iterations": iterations,
            "tools_used": tools_used,
            "pending_mutations": pending_mutations,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        task.route = RoutingLevel.REQUIRES_APPROVAL
        task.tool_name = names[0] if names else "agentic.mutation"
        task.transition(TaskStatus.AWAITING_APPROVAL)
        task.result = {
            "message": "Loop agéntico suspendido; mutaciones requieren aprobación inline.",
            "approved": False,
            "reason": reason,
            "pending_mutations": names,
            "iterations": iterations,
        }
        with self._approvals_lock:
            self._pending_approvals[task.id] = task
        self._persist_pending_approval(task)
        self._merkle.log(
            action="task.suspended",
            agent="orchestrator.agentic",
            result="pending",
            risk_level="high",
            payload={"iterations": iterations, "pending_mutations": names},
            task_id=task.id,
        )
        self._bus.publish_type(EventType.APPROVAL_REQUIRED, {
            "task_id": task.id,
            "intent": task.intent,
            "reason": reason,
            "tool": task.tool_name,
        }, task.id)

    def _dispatch_agentic_mutation(
        self, name: str, arguments: str, task: Task
    ) -> str:
        """ADR-032: ejecuta una mutación de host APROBADA por la vía Gate F, con
        el clearance ya concedido (mark_confirmed("task:<id>") en approve). El
        AtlasExecutor sigue siendo el único que autoriza (dec.8). Devuelve el
        resultado como texto para reinyectarlo al loop."""
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}

        tool, _, action = name.partition("_")
        self._merkle.log(
            action="tool.invoked",
            agent=f"orchestrator.agentic.{name}",
            result="ok",
            risk_level="high",
            payload={"tool": name},
            task_id=task.id,
        )
        try:
            if tool == "editor":
                result = self._execute_editor_command(action, args, task=task)
            elif tool == "browser":
                result = self._execute_browser_command(action, args)
            else:
                return f"error: mutación desconocida '{name}'"
            return self._stringify_tool_result(result)
        except KeyError as exc:
            return f"error: falta argumento {exc}"
        except Exception as exc:  # noqa: BLE001 — devolvemos el error al modelo
            return f"error: {type(exc).__name__}: {exc}"

    def _resume_agentic_loop(self, task: Task) -> None:
        """ADR-032: reanuda un loop suspendido. Ejecuta las mutaciones pendientes
        (o inyecta denegación sintética si el humano las rechazó sin abortar),
        reinyecta los resultados y continúa el loop hasta respuesta final o nueva
        suspensión. `iterations` continúa desde el valor persistido (dec.9)."""
        from atlas.core.inference_hub import InferenceLevel, InferenceRequest

        state = task.metadata.get("agentic_state")
        if not isinstance(state, dict):
            raise RuntimeError("agentic_state ausente o inválido en resume")

        messages = list(state.get("messages") or [])
        iterations = int(state.get("iterations", 0))
        tools_used = list(state.get("tools_used") or [])
        pending_mutations = list(state.get("pending_mutations") or [])
        denied = bool(state.get("denied"))
        deny_reason = str(state.get("deny_reason", "human"))

        # Limpiar el estado para no re-resumir por accidente; si el loop vuelve a
        # suspender, _suspend_agentic_loop escribe un agentic_state nuevo.
        task.metadata.pop("agentic_state", None)

        for mut in pending_mutations:
            if denied:
                # dec.6: presión MemGPT — el modelo re-planifica, no crashea.
                safe_result = json.dumps(
                    {"denied": True, "reason": deny_reason}, ensure_ascii=False
                )
            else:
                raw_result = self._dispatch_agentic_mutation(
                    mut["name"], str(mut.get("arguments", "")), task
                )
                safe_result = self._pii_surrogate.redact(raw_result).text
            messages.append({
                "role": "tool",
                "tool_call_id": mut["id"],
                "content": safe_result,
            })

        tool_specs = self._agentic_tool_specs()
        request = InferenceRequest(
            prompt="",
            level=InferenceLevel.L1,
            messages=messages,
            tools=tool_specs,
            max_tokens=512,
            temperature=0.3,
            task_id=task.id,
        )
        response = self._inference_hub.infer(request)
        if not response.success:
            self._record_inference_failure(task, response)
            return

        loop_result = self._drive_agentic_loop(
            task, messages, response, tool_specs, iterations, tools_used,
        )
        if loop_result is None:
            return  # re-suspendido (nueva aprobación) o fallo ya registrado
        response, iterations = loop_result

        # PII: no persistimos el combined mapping (evitar PII en disco), así que
        # los surrogates no se restauran tras una suspensión (documentado en ADR).
        restored = self._pii_surrogate.restore(response.text, {})
        task.tool_name = "inference_hub.complete"
        task.result = {
            "text":        restored,
            "provider":    response.provider,
            "model":       response.model,
            "latency_ms":  response.latency_ms,
            "tokens_used": response.tokens_used,
            "mode":        response.mode,
            "iterations":  iterations,
            "tools_used":  tools_used,
            "resumed":     True,
            "denied":      denied,
        }
        self._merkle.log(
            action="inference.completed",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={
                "provider":   response.provider,
                "model":      response.model,
                "iterations": iterations,
                "tools_used": tools_used,
                "resumed":    True,
            },
            task_id=task.id,
        )
        task.transition(TaskStatus.DONE)
        self._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)

    def _delegate_to_hermes(self, task: Task) -> None:
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
        task.transition(TaskStatus.BLOCKED)
        task.error = reason
        self._merkle.log(
            action="task.blocked",
            agent="orchestrator",
            result="blocked",
            risk_level=risk_level,
            payload={"reason": reason, "intent": task.intent},
            task_id=task.id,
        )

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
    ) -> dict:
        """Helper comun: emite capability, ejecuta en sandbox y normaliza salida."""
        from atlas.security.capabilities import CapabilityDenied  # noqa: PLC0415
        from atlas.security.executor import ExecutorError          # noqa: PLC0415
        clearance = f"task:{task.id}" if task is not None else None
        try:
            cap = self._capability_issuer.issue_exec(
                command, args=args, timeout_s=10, clearance=clearance,
            )
            result = self._executor.execute_exec(cap)
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.exit_code,
                "duration_ms": result.duration_ms,
            }
        except CapabilityDenied as e:
            return {"error": f"capability denegada: {e}"}
        except ExecutorError as e:
            return {"error": f"executor: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def _git_args(self, sub: str, *extra: str) -> tuple[str, ...]:
        """Prefija `-C <repo_root>` cuando hay repo de código (grounding real).

        Sin repo (None) cae al comportamiento previo: git corre en el cwd del
        sandbox (workspace/tmp).
        """
        root = self._repo_root()
        if root is not None:
            return ("-C", str(root), sub, *extra)
        return (sub, *extra)

    def _with_repo_root(self, result: dict) -> dict:
        """Inyecta el repo_root real en el resultado git.

        Grounding de procedencia: el modelo gemelo (Hermes) NO debe inventar la
        ruta del repo. Sin este campo, al pedir "dónde está el repo" confabula
        un path inexistente. Con él, tiene la verdad en el output de la tool.
        """
        root = self._repo_root()
        if root is not None and "error" not in result:
            result["repo_root"] = str(root)
        return result

    def _run_git_status(self, task: Task | None = None) -> dict:
        return self._with_repo_root(
            self._run_via_executor("git", self._git_args("status", "--short"), task=task)
        )

    def _run_git_log(self, task: Task | None = None) -> dict:
        return self._with_repo_root(
            self._run_via_executor("git", self._git_args("log", "--oneline", "-10"), task=task)
        )

    def _run_git_diff(self, task: Task | None = None) -> dict:
        return self._with_repo_root(
            self._run_via_executor("git", self._git_args("diff", "--stat"), task=task)
        )

    def _list_workspace(self) -> dict:
        """
        Lista el workspace via iterdir() + log explicito en Merkle. No usa
        sandbox porque iterdir() es Python puro (no IO de proceso). Mantiene
        el contrato de auditoria registrando la operacion como leeria
        AtlasExecutor.
        """
        try:
            entries = [p.name for p in self._workspace.iterdir()]
            self._merkle.log(
                action="fs.list_dir",
                agent="atlas.executor",
                result="ok",
                risk_level="safe",
                payload={"path": str(self._workspace), "entries": len(entries)},
            )
            return {"entries": sorted(entries), "path": str(self._workspace)}
        except Exception as e:
            self._merkle.log(
                action="fs.list_dir",
                agent="atlas.executor",
                result="failed",
                risk_level="safe",
                payload={"path": str(self._workspace), "error": str(e)},
            )
            return {"error": str(e)}

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
        self._self_audit_runner = None

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
        self._pending_approvals: dict[str, Task] = {}
        self._approvals_lock = threading.Lock()
        self._pending_approval_dir = self._workspace / "memory" / "pending_approvals"

        # Telegram bot + monitors (opcionales, se inician con start_*).
        # Tipo declarado a nivel clase (ver bloque al inicio de Orchestrator).
        self._telegram_bot = None
        self._telegram_thread = None
        self._offline_monitor = None
        self._thermal_watchdog = None
        self._browser_tool = None
        self._editor_tool = None
        self._vision_loop = None

        # Gate D pipeline integrado — desactivado por defecto. Se activa con
        # enable_gate_d_pipeline() o con ATLAS_PIPELINE_GATE_D=1 en el env.
        # PIISurrogate es siempre construible (sin dependencias externas).
        self._distiller = None
        self._ghost_replay = None
        self._slm_classifier = None
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
        self._pending_approval_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._pending_approval_dir / f"{task_id}.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None, None
        return fd, lock_path

    def _thermal_blocks_local_llm(self) -> str | None:
        if self._thermal_watchdog is None:
            return None
        state = self._thermal_watchdog.current_state()
        if state.should_pause_local_llm:
            return state.policy
        return None

    def _thermal_blocks_execution(self) -> str | None:
        if self._thermal_watchdog is None:
            return None
        state = self._thermal_watchdog.current_state()
        if state.emergency:
            return state.policy
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
