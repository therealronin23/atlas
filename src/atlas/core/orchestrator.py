"""
Atlas Core — Orquestador
Coordina: Governance L0 → Permission Profile → Classifier → Tools → Merkle Logger.
Decision final: Atlas decide. Todo lo demas sirve a Atlas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.contracts import (
    DelegationPayload, Event, EventType, RoutingLevel,
    Task, TaskSource, TaskStatus, Tool, ToolLevel, PermissionLevel,
)
from atlas.core.event_bus import EventBus
from atlas.governance.governance_l0 import GovernanceL0
from atlas.governance.permission_profile import PermissionProfile
from atlas.hermes.hermes import DelegationBuilder, HermesMockAdapter, OfflineQueue
from atlas.logging.merkle_logger import MerkleLogger
from atlas.memory.memory_system import (
    ErrorRegistry, ApprovedPatternStore, ProviderMetricsStore, SystemContextLoader, ToolRegistry,
)
from atlas.router.classifier import Classifier
from atlas.security.ast_guard import ASTGuard


@dataclass
class AtlasStatus:
    version: str
    workspace: str
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

    VERSION = "0.1.0"

    def __init__(self, workspace: Path | None = None) -> None:
        self._workspace = workspace or self._resolve_workspace()
        self._start_time = datetime.now(timezone.utc)
        self._init_dirs()
        self._init_components()
        self._log_session_start()

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
        hermes_status = self._hermes_mock.health_check()
        uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        return AtlasStatus(
            version=self.VERSION,
            workspace=str(self._workspace),
            governance_ok=not gov.in_emergency_mode,
            chain_ok=chain_ok,
            tool_count=len(self._tool_registry.enabled()),
            queue_depth=self._offline_queue.depth,
            hermes_mode=hermes_status.mode,
            record_count=self._merkle.record_count,
            uptime_seconds=round(uptime, 1),
            emergency_mode=gov.in_emergency_mode,
        )

    def audit_tail(self, n: int = 20) -> list[dict]:
        return [r.to_dict() for r in self._merkle.tail(n)]

    def tools(self) -> list[dict]:
        return [t.to_dict() for t in self._tool_registry.all()]

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

    @property
    def bus(self) -> EventBus:
        return self._bus

    # ------------------------------------------------------------------
    # Pipeline interno
    # ------------------------------------------------------------------

    def _run_pipeline(self, task: Task) -> None:
        # 1. Governance L0
        task.transition(TaskStatus.CLASSIFYING)
        gov = GovernanceL0.get_instance()
        if gov.in_emergency_mode:
            self._block_task(task, "Atlas en modo de emergencia.", "critical")
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
            }
            self._merkle.log(
                action="task.routed",
                agent="router",
                result="pending",
                risk_level="high",
                payload={"requires_approval": True, "reason": result.reason},
                task_id=task.id,
            )
            return

        # DETERMINISTIC_TOOL o LOCAL_SAFE → ejecutar
        task.transition(TaskStatus.EXECUTING)
        self._execute_task(task)

    def _execute_task(self, task: Task) -> None:
        """Ejecuta la tarea con la herramienta deterministica correspondiente."""
        intent_lower = task.intent.lower()

        # Mapear intencion a herramienta
        if any(kw in intent_lower for kw in ["estado de atlas", "atlas status"]):
            task.tool_name = "atlas.status"
            task.result = self.status().__dict__
        elif any(kw in intent_lower for kw in ["git status", "estado git"]):
            task.tool_name = "git.status"
            task.result = self._run_git_status()
        elif any(kw in intent_lower for kw in ["git log", "historial"]):
            task.tool_name = "git.log"
            task.result = self._run_git_log()
        elif any(kw in intent_lower for kw in ["git diff", "diferencias"]):
            task.tool_name = "git.diff"
            task.result = self._run_git_diff()
        elif any(kw in intent_lower for kw in ["lista", "listar", "list"]):
            task.tool_name = "fs.list_dir"
            task.result = self._list_workspace()
        else:
            task.tool_name = "local_safe.passthrough"
            task.result = {
                "message": "Tarea LOCAL_SAFE recibida. Modelo local requerido (no disponible en v0.1).",
                "intent": task.intent,
            }

        self._merkle.log(
            action="tool.invoked",
            agent=task.tool_name or "unknown",
            result="success",
            risk_level="safe",
            payload={"tool": task.tool_name},
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
        # enqueue_task firma el payload internamente; recuperamos el firmado
        receipt = self._hermes_mock.enqueue_task(payload)

        # Recuperar el payload firmado del mock para persistirlo en la cola offline
        signed_payload = self._hermes_mock._queue.get(payload.id, payload)

        entry_cls = __import__(
            "atlas.hermes.hermes", fromlist=["QueueEntry"]
        ).QueueEntry
        self._offline_queue.enqueue(entry_cls(delegation=signed_payload))

        task.transition(TaskStatus.DELEGATED)
        task.result = {
            "delegation_id": receipt.delegation_id,
            "accepted": receipt.accepted,
            "queue_position": receipt.queue_position,
            "note": "Payload generado y encolado. Hermes en modo mock (v0.1).",
        }
        self._merkle.log(
            action="hermes.mock_queued",
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

    def _run_git_status(self) -> dict:
        import subprocess
        try:
            r = subprocess.run(
                ["git", "status", "--short"],
                cwd=self._workspace,
                capture_output=True, text=True, timeout=10
            )
            return {"stdout": r.stdout, "returncode": r.returncode}
        except Exception as e:
            return {"error": str(e)}

    def _run_git_log(self) -> dict:
        import subprocess
        try:
            r = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=self._workspace,
                capture_output=True, text=True, timeout=10
            )
            return {"stdout": r.stdout, "returncode": r.returncode}
        except Exception as e:
            return {"error": str(e)}

    def _run_git_diff(self) -> dict:
        import subprocess
        try:
            r = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self._workspace,
                capture_output=True, text=True, timeout=10
            )
            return {"stdout": r.stdout, "returncode": r.returncode}
        except Exception as e:
            return {"error": str(e)}

    def _list_workspace(self) -> dict:
        try:
            entries = [p.name for p in self._workspace.iterdir()]
            return {"entries": sorted(entries), "path": str(self._workspace)}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Inicializacion
    # ------------------------------------------------------------------

    def _resolve_workspace(self) -> Path:
        env = os.environ.get("ATLAS_HOME")
        return Path(env).expanduser().resolve() if env else Path.home() / "atlas"

    def _init_dirs(self) -> None:
        for sub in ["projects", "tmp", "skills", "memory/system_context",
                    "memory/error_registry", "memory/approved_patterns",
                    "memory/performance", "memory/audit", "config"]:
            (self._workspace / sub).mkdir(parents=True, exist_ok=True)

    def _init_components(self) -> None:
        config_dir = self._workspace / "config"

        # Copiar config defaults si no existen
        self._copy_defaults(config_dir)

        # Governance L0
        GovernanceL0.initialize(config_dir / "governance.json")

        # Permission Profile
        self._permissions = PermissionProfile(
            config_dir / "permissions.yaml", self._workspace
        )

        # Merkle Logger
        self._merkle = MerkleLogger(self._workspace / "memory" / "audit")

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

        # Memoria
        self._system_context = SystemContextLoader.load(
            self._workspace / "memory" / "system_context"
        )
        self._error_registry = ErrorRegistry(self._workspace / "memory" / "error_registry")
        self._approved_patterns = ApprovedPatternStore(self._workspace / "memory" / "approved_patterns")
        self._provider_metrics = ProviderMetricsStore(self._workspace / "memory" / "performance")
        self._tool_registry = ToolRegistry()

        # Hermes
        self._hermes_mock = HermesMockAdapter()
        self._offline_queue = OfflineQueue(self._workspace / "memory")

        # Event Bus
        self._bus = EventBus()

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

    def _log_session_start(self) -> None:
        self._merkle.log(
            action="session.started",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={"version": self.VERSION, "workspace": str(self._workspace)},
        )
        self._bus.publish_type(EventType.SESSION_STARTED, {"version": self.VERSION})
