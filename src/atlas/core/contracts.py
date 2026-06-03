"""
Atlas Core — Contratos de sistema
Task, Event, Tool, DelegationPayload, HermesStatus, QueueStatus.
Todos los schemas son dataclasses tipadas con invariantes en __post_init__.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ===========================================================================
# Task
# ===========================================================================

class TaskStatus(str, Enum):
    PENDING           = "pending"
    CLASSIFYING       = "classifying"
    ROUTING           = "routing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING         = "executing"
    DELEGATED         = "delegated"
    DONE              = "done"
    FAILED            = "failed"
    BLOCKED           = "blocked"
    CANCELLED         = "cancelled"


class RoutingLevel(str, Enum):
    DETERMINISTIC_TOOL = "deterministic_tool"
    LOCAL_SAFE         = "local_safe"
    REQUIRES_APPROVAL  = "requires_approval"
    DELEGATE_HERMES    = "delegate_hermes"
    BLOCKED            = "blocked"


class TaskSource(str, Enum):
    CLI      = "cli"
    TELEGRAM = "telegram"
    API      = "api"
    INTERNAL = "internal"


# Transiciones validas de estado
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING:           {TaskStatus.CLASSIFYING, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.CLASSIFYING:       {TaskStatus.ROUTING, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.ROUTING:           {TaskStatus.AWAITING_APPROVAL, TaskStatus.EXECUTING,
                                   TaskStatus.DELEGATED, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.EXECUTING, TaskStatus.DELEGATED,
                                   TaskStatus.CANCELLED, TaskStatus.BLOCKED},
    # ADR-032: un loop agéntico en ejecución puede SUSPENDERSE a la espera de
    # aprobación humana inline cuando el modelo pide una mutación de host.
    TaskStatus.EXECUTING:         {TaskStatus.DONE, TaskStatus.FAILED,
                                   TaskStatus.AWAITING_APPROVAL},
    TaskStatus.DELEGATED:         {TaskStatus.DONE, TaskStatus.FAILED},
    TaskStatus.DONE:              set(),
    TaskStatus.FAILED:            set(),
    TaskStatus.BLOCKED:           set(),
    TaskStatus.CANCELLED:         set(),
}


class OperationalMode(str, Enum):
    """
    Tres tiers de operacion basados en estado termico y RAM disponible.
    NORMAL   (<70C, RAM OK)  : sin restricciones, todos los modelos disponibles.
    DEGRADED (70-79C o <1GB) : LLMs pesados pausados, funciones criticas activas.
    OMEGA    (>=80C)         : emergencia — solo L-det y Hermes, parar no critico.
    """
    NORMAL   = "normal"    # Operacion completa sin restricciones
    DEGRADED = "degraded"  # LLMs pesados deshabilitados, funciones criticas OK
    OMEGA    = "omega"     # Emergencia: solo L-det y delegacion a Hermes


@dataclass
class Task:
    intent: str
    source: TaskSource
    id: str                    = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int              = 3
    sensitivity: str           = "low"          # "low" | "medium" | "high"
    action: str                = ""             # Tipo de accion descriptivo
    status: TaskStatus         = TaskStatus.PENDING
    operational_mode: OperationalMode = OperationalMode.NORMAL
    route: RoutingLevel | None = None
    tool_name: str | None      = None
    parent_id: str | None      = None
    created_at: str            = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str            = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    result: Any | None         = None
    error: str | None          = None
    audit_hash: str | None     = None
    metadata: dict             = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 1 <= self.priority <= 5:
            raise ValueError(f"priority debe ser 1-5, recibido: {self.priority}")
        if not self.intent.strip():
            raise ValueError("intent no puede estar vacio")
        if self.sensitivity not in ("low", "medium", "high"):
            raise ValueError(f"sensitivity debe ser low|medium|high, recibido: {self.sensitivity}")

    def transition(self, new_status: TaskStatus) -> None:
        valid = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Transicion invalida: {self.status} → {new_status}. "
                f"Validas: {[s.value for s in valid]}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["source"] = self.source.value
        d["route"] = self.route.value if self.route else None
        return d


@dataclass
class ReasoningReceipt:
    purpose: str
    data_touched: list[str]
    permissions_required: list[str]
    safety_checks: list[str]
    approval_path: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TruthSnapshot:
    id: str
    tool_name: str
    input_data: dict[str, Any]
    expected_output_shape: dict[str, Any]
    invariants: dict[str, Any] = field(default_factory=dict)
    source_task_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Event
# ===========================================================================

class EventType(str, Enum):
    TASK_RECEIVED      = "task.received"
    TASK_CLASSIFIED    = "task.classified"
    TASK_COMPLETED     = "task.completed"
    TOOL_INVOKED       = "tool.invoked"
    TOOL_FAILED        = "tool.failed"
    MODEL_TIMEOUT      = "model.timeout"
    SECURITY_VIOLATION = "security.violation"
    THERMAL_ALERT      = "thermal.alert"
    HERMES_MESSAGE     = "hermes.message"
    SHADOW_ALERT       = "shadow.alert"
    HERMES_RECONNECTED = "hermes.reconnected"   # ADR-012: transicion offline->online
    APPROVAL_REQUIRED  = "approval.required"
    AGENTIC_PROGRESS   = "agentic.progress"    # ADR-033: traza por iteración del loop
    MEMORY_UPDATED         = "memory.updated"
    SESSION_STARTED        = "session.started"
    SESSION_ENDED          = "session.ended"
    HERMES_WEBHOOK_RECEIVED = "hermes_webhook.received"
    HERMES_ONLINE_CONFIRMED = "hermes_online.confirmed"
    DECIDER_VERDICT         = "decider.verdict"   # ADR-040: canal on-the-loop


@dataclass
class Event:
    type: EventType
    payload: dict      = field(default_factory=dict)
    id: str            = field(default_factory=lambda: str(uuid.uuid4()))
    producer: str      = "atlas_core"
    task_id: str | None = None
    timestamp: str     = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


# ===========================================================================
# Tool
# ===========================================================================

class ToolLevel(str, Enum):
    L_DET = "L-det"
    L0    = "L0"
    L1    = "L1"
    L2    = "L2"


class PermissionLevel(str, Enum):
    AUTO    = "auto"
    CONFIRM = "confirm"
    APPROVE = "approve"
    BLOCKED = "blocked"


@dataclass
class Tool:
    name: str
    description: str
    level: ToolLevel
    permission_level: PermissionLevel
    schema_input: dict         = field(default_factory=dict)
    schema_output: dict        = field(default_factory=dict)
    credentials_required: list = field(default_factory=list)
    estimated_cost: str        = "free"
    resource_profile: dict     = field(default_factory=dict)
    known_failures: list[str]  = field(default_factory=list)
    skill_md_path: str | None  = None
    enabled: bool              = True
    last_used: str | None      = None
    success_rate: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        d["permission_level"] = self.permission_level.value
        return d


# ===========================================================================
# Delegation
# ===========================================================================

@dataclass
class DelegationPayload:
    task_id: str
    task_intent: str
    priority: int
    timeout_seconds: int  = 300
    callback_endpoint: str = "atlas://core/hermes/callback"
    id: str               = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str       = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: str       = field(default="")
    encrypted: bool       = False
    signature: str        = ""
    metadata: dict        = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds)
            ).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DelegationReceipt:
    delegation_id: str
    accepted: bool
    queue_position: int | None      = None
    estimated_eta_seconds: int | None = None
    error: str | None               = None


@dataclass
class DelegationResult:
    delegation_id: str
    task_id: str
    status: str
    result: dict | None    = None
    error: str | None      = None
    completed_at: str | None = None
    skill_generated: bool  = False
    skill_md: str | None   = None


# ===========================================================================
# Hermes status
# ===========================================================================

@dataclass
class HermesStatus:
    reachable: bool
    mode: str               # "live" | "mock" | "offline"
    queue_depth: int        = 0
    last_seen: str | None   = None
    version: str | None     = None


@dataclass
class QueueStatus:
    depth: int
    oldest_task_age_seconds: int | None
    next_task_id: str | None
    processing: bool
