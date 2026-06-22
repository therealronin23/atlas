"""Pipeline de ejecución de tareas — extraído del god-object ``Orchestrator`` (ADR-039).

Agrupa los métodos del pipeline interno:
    _run_pipeline, _run_pipeline_gate_d, _hybrid_classify,
    _execute_task, _block_task, _run_via_executor.

Inyección: ``PipelineRunner(orch)`` guarda ``self._orch`` y accede a todos los
colaboradores del Orchestrator en tiempo de llamada (patrón ``MaintenanceFacade``).
El import de ``Orchestrator`` se hace bajo ``TYPE_CHECKING`` para evitar ciclos.

LECCIÓN DE SEGURIDAD: todas las llamadas a métodos que los tests podrían
monkeypatchear sobre la clase ``Orchestrator`` se enrutan por ``self._orch.X()``,
no por ``self.X()``, para que cualquier monkeypatch sobre la instancia del
Orchestrator se respete exactamente igual que antes del refactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.core.contracts import (
    EventType,
    RoutingLevel,
    Task,
    TaskStatus,
)
from atlas.core.decider import (
    Allow,
    DecisionAction,
    Deny,
    RequiresHuman,
)
from atlas.governance.governance_l0 import GovernanceL0
from atlas.router.classifier import ClassificationResult

if TYPE_CHECKING:
    from atlas.core.orchestrator import Orchestrator


class PipelineRunner:
    """Ejecutor del pipeline de tareas (ADR-039).

    El Orchestrator instancia este objeto en ``_init_components`` y delega
    ``_run_pipeline``, ``_execute_task``, etc. a él. Todas las llamadas a
    colaboradores del Orchestrator (``_merkle``, ``_bus``, ``_classifier``,
    etc.) se realizan en tiempo de llamada via ``self._orch``.
    """

    def __init__(self, orch: "Orchestrator") -> None:
        self._orch = orch

    # ------------------------------------------------------------------
    # Pipeline interno
    # ------------------------------------------------------------------

    def _run_pipeline(self, task: Task) -> None:
        if self._orch._gate_d_enabled:
            self._orch._run_pipeline_gate_d(task)
            return

        # 1. Governance L0
        task.transition(TaskStatus.CLASSIFYING)
        gov = GovernanceL0.get_instance()
        if gov.in_emergency_mode:
            self._orch._block_task(task, "Atlas en modo de emergencia.", "critical")
            return

        gate_f = self._orch._parse_gate_f_command(task.intent)
        if gate_f is not None:
            self._orch._route_gate_f_command(task, gate_f)
            return

        # 2. Clasificar
        result = self._orch._classifier.classify(task.intent, sensitivity=task.sensitivity)

        if result.governance_blocked:
            self._orch._block_task(task, result.reason, "critical")
            self._orch._bus.publish_type(EventType.SECURITY_VIOLATION, {
                "reason": result.reason, "intent": task.intent
            }, task.id)
            return

        task.transition(TaskStatus.ROUTING)
        task.route = result.level
        self._orch._merkle.log(
            action="task.classified",
            agent="classifier",
            result="success",
            risk_level="safe",
            payload={"route": result.level.value, "reason": result.reason},
            task_id=task.id,
        )

        # 3. Enrutar
        if result.level == RoutingLevel.BLOCKED:
            self._orch._block_task(task, result.reason, "high")
            return

        if result.level == RoutingLevel.DELEGATE_HERMES:
            self._orch._delegate_to_hermes(task)
            return

        if result.level == RoutingLevel.REQUIRES_APPROVAL:
            verdict, _ = self._orch._consult_decider(
                DecisionAction(
                    kind="route",
                    requires_approval=True,
                    sensitivity=task.sensitivity,
                    reason=result.reason,
                ),
                task,
            )
            if isinstance(verdict, RequiresHuman):
                task.transition(TaskStatus.AWAITING_APPROVAL)
                task.result = {
                    "message": f"Accion requiere aprobacion explicita. Razon: {result.reason}",
                    "approved": False,
                    "reason": result.reason,
                }
                self._orch._approvals.register(task)
                self._orch._persist_pending_approval(task)
                self._orch._merkle.log(
                    action="task.routed",
                    agent="router",
                    result="pending",
                    risk_level="high",
                    payload={"requires_approval": True, "reason": result.reason},
                    task_id=task.id,
                )
                self._orch._bus.publish_type(EventType.APPROVAL_REQUIRED, {
                    "task_id": task.id,
                    "intent": task.intent,
                    "reason": result.reason,
                }, task.id)
                return
            if isinstance(verdict, Deny):
                self._orch._block_task(task, verdict.reason or result.reason, "high")
                return
            # Allow → el decisor autoriza sin humano; cae a ejecución.

        # DETERMINISTIC_TOOL o LOCAL_SAFE (o Allow del decisor) → ejecutar
        task.transition(TaskStatus.EXECUTING)
        self._orch._execute_task(task)

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
        if self._orch._timetravel is None:
            raise RuntimeError(
                "Gate D pipeline: _timetravel no inicializado "
                "(llama a enable_gate_d_pipeline)"
            )
        if self._orch._ghost_replay is None:
            raise RuntimeError(
                "Gate D pipeline: _ghost_replay no inicializado "
                "(llama a enable_gate_d_pipeline)"
            )
        if self._orch._slm_classifier is None:
            raise RuntimeError(
                "Gate D pipeline: _slm_classifier no inicializado "
                "(llama a enable_gate_d_pipeline)"
            )

        self._orch._timetravel.record_step(
            task.id, "received",
            {"intent": task.intent, "source": task.source.value},
        )

        # 1. Governance L0
        task.transition(TaskStatus.CLASSIFYING)
        gov = GovernanceL0.get_instance()
        if gov.in_emergency_mode:
            self._orch._block_task(task, "Atlas en modo de emergencia.", "critical")
            self._orch._timetravel.record_step(task.id, "blocked_emergency", {"intent": task.intent})
            return

        # 2. Ghost cache lookup — solo intenta para tareas que NO requieran
        # aprobacion ni delegacion. Para mantenerlo simple, consultamos
        # siempre antes del classifier: si hit, devolvemos directamente.
        sensitivity = task.sensitivity   # "low" | "medium" | "high"
        ctx_sig = "pipeline-d-v1"

        gate_f = self._orch._parse_gate_f_command(task.intent)
        if gate_f is not None:
            self._orch._route_gate_f_command(task, gate_f)
            self._orch._timetravel.record_step(
                task.id,
                "gate_f_routed",
                {
                    "tool": gate_f.tool,
                    "action": gate_f.action,
                    "requires_approval": gate_f.requires_approval,
                },
            )
            return

        if self._orch._ghost_cache_eligible(sensitivity):
            hit = self._orch._ghost_replay.lookup(task.intent, sensitivity, ctx_sig)
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
            self._orch._merkle.log(
                action="task.ghost_hit",
                agent="orchestrator",
                result="success",
                risk_level="safe",
                payload={"intent": task.intent, "route": task.route.value},
                task_id=task.id,
            )
            self._orch._timetravel.record_step(
                task.id, "ghost_hit",
                {"route": task.route.value, "cached": True},
            )
            self._orch._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)
            return

        # 3. Hybrid classify
        cls = self._orch._hybrid_classify(task.intent, task.sensitivity, task_id=task.id)

        if cls.governance_blocked:
            self._orch._block_task(task, cls.reason, "critical")
            self._orch._bus.publish_type(EventType.SECURITY_VIOLATION, {
                "reason": cls.reason, "intent": task.intent,
            }, task.id)
            self._orch._timetravel.record_step(task.id, "blocked_governance", {"reason": cls.reason})
            return

        task.transition(TaskStatus.ROUTING)
        task.route = cls.level
        winner = "slm" if isinstance(cls.reason, str) and cls.reason.startswith("SLM:") else "rule"
        self._orch._merkle.log(
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
        self._orch._timetravel.record_step(
            task.id, "classified",
            {"route": cls.level.value, "confidence": cls.confidence, "reason": cls.reason},
        )

        # 4. Route
        if cls.level == RoutingLevel.BLOCKED:
            self._orch._block_task(task, cls.reason, "high")
            return

        if cls.level == RoutingLevel.DELEGATE_HERMES:
            self._orch._delegate_to_hermes(task)
            self._orch._timetravel.record_step(task.id, "delegated", {"target": "hermes"})
            return

        if cls.level == RoutingLevel.REQUIRES_APPROVAL:
            verdict, _ = self._orch._consult_decider(
                DecisionAction(
                    kind="route",
                    requires_approval=True,
                    sensitivity=task.sensitivity,
                    reason=cls.reason,
                ),
                task,
            )
            if isinstance(verdict, RequiresHuman):
                task.transition(TaskStatus.AWAITING_APPROVAL)
                task.result = {
                    "message": f"Accion requiere aprobacion explicita. Razon: {cls.reason}",
                    "approved": False,
                    "reason": cls.reason,
                }
                self._orch._approvals.register(task)
                self._orch._persist_pending_approval(task)
                self._orch._merkle.log(
                    action="task.routed",
                    agent="router",
                    result="pending",
                    risk_level="high",
                    payload={"requires_approval": True, "reason": cls.reason},
                    task_id=task.id,
                )
                self._orch._bus.publish_type(EventType.APPROVAL_REQUIRED, {
                    "task_id": task.id, "intent": task.intent, "reason": cls.reason,
                }, task.id)
                self._orch._timetravel.record_step(task.id, "awaiting_approval", {"reason": cls.reason})
                return
            if isinstance(verdict, Deny):
                self._orch._block_task(task, verdict.reason or cls.reason, "high")
                self._orch._timetravel.record_step(task.id, "denied", {"reason": verdict.reason or cls.reason})
                return
            # Allow → el decisor autoriza sin humano; cae a ejecución.

        # 5. Execute (DETERMINISTIC_TOOL o LOCAL_SAFE o Allow del decisor)
        task.transition(TaskStatus.EXECUTING)
        self._orch._execute_task(task)

        # 6. Ghost record si la ejecucion fue OK (nunca cachear approval/high)
        if task.status == TaskStatus.DONE and self._orch._ghost_cache_eligible(
            sensitivity, route=task.route,
        ):
            try:
                self._orch._ghost_replay.record(
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
            self._orch._timetravel.record_step(
                task.id, "done",
                {"tool": task.tool_name, "route": task.route.value if task.route else None},
            )

    def _hybrid_classify(
        self, intent: str, sensitivity: str | None, *, task_id: str | None = None,
    ) -> ClassificationResult:
        return self._orch._hybrid.classify(intent, sensitivity, task_id=task_id)

    def _execute_task(self, task: Task) -> None:
        """Ejecuta la tarea con la herramienta deterministica correspondiente."""
        if self._orch._thermal_watchdog is not None:
            task.operational_mode = self._orch._thermal_watchdog.current_operational_mode()

        tool_key = task.tool_name or "legacy"
        gate_h_block = self._orch._check_gate_h_tool_allowed(tool_key, task.id)
        if gate_h_block:
            task.transition(TaskStatus.FAILED)
            task.error = gate_h_block
            task.result = {"error": gate_h_block, "paused": True}
            return

        # ADR-032: reanudación de un loop agéntico suspendido. Si la tarea trae
        # estado serializado, la aprobación HITL ya ejecutó mark_confirmed; aquí
        # se ejecutan las mutaciones pendientes y el loop continúa.
        if "agentic_state" in task.metadata:
            self._orch._agentic_executor.resume(task)
            return

        if "gate_f_command" in task.metadata:
            self._orch._execute_gate_f_task(task)
            return

        intent_lower = task.intent.lower()

        # Mapear intencion a herramienta
        if any(kw in intent_lower for kw in ["estado de atlas", "atlas status"]):
            task.tool_name = "atlas.status"
            task.result = self._orch.status().__dict__
        elif any(kw in intent_lower for kw in ["git status", "estado git"]):
            task.tool_name = "git.status"
            task.result = self._orch._run_git_status(task)
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
            task.result = self._orch._run_git_log(task)
        elif any(
            kw in intent_lower
            for kw in ["git diff", "diferencias", "qué cambió", "que cambio", "what changed"]
        ):
            task.tool_name = "git.diff"
            task.result = self._orch._run_git_diff(task)
        elif any(kw in intent_lower for kw in ["lista", "listar", "list"]):
            task.tool_name = "fs.list_dir"
            task.result = self._orch._list_workspace()
        else:
            # LOCAL_SAFE: si pipeline Gate D activo + InferenceHub disponible,
            # responder via inferencia real con MemoryDistiller + PIISurrogate.
            # Si no, fallback al passthrough informativo de v0.1.
            if self._orch._gate_d_enabled and self._orch._inference_hub is not None:
                self._orch._agentic_executor.execute_local_safe(task)
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

        self._orch._merkle.log(
            action="tool.invoked",
            agent=task.tool_name or "unknown",
            result="success",
            risk_level="safe",
            payload={"tool": task.tool_name},
            task_id=task.id,
        )
        self._orch._record_tool_receipt(
            task,
            purpose="Ejecucion de herramienta determinista",
            approval_path="explicit" if task.route == RoutingLevel.REQUIRES_APPROVAL else "automatic",
        )
        task.transition(TaskStatus.DONE)
        self._orch._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)

    def _block_task(self, task: Task, reason: str, risk_level: str) -> None:
        task.transition(TaskStatus.BLOCKED)
        task.error = reason
        self._orch._merkle.log(
            action="task.blocked",
            agent="orchestrator",
            result="blocked",
            risk_level=risk_level,
            payload={"reason": reason, "intent": task.intent},
            task_id=task.id,
        )

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
        """Helper comun: emite capability, ejecuta en sandbox y normaliza salida."""
        from atlas.security.capabilities import CapabilityDenied  # noqa: PLC0415
        from atlas.security.executor import ExecutorError          # noqa: PLC0415
        clearance = f"task:{task.id}" if task is not None else None
        try:
            cap = self._orch._capability_issuer.issue_exec(
                command, args=args, timeout_s=10, clearance=clearance,
            )
            result = self._orch._executor.execute_exec(cap)
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
