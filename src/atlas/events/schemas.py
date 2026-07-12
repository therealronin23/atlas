"""Modelos pydantic del canon Atlas OS — espejo 1:1 de schemas/*.schema.json.

La autoridad del contrato son los JSON Schema versionados en `schemas/`;
estos modelos existen para validar en runtime sin añadir la dependencia
`jsonschema` (invariante 6: pydantic ya está en pyproject). Si cambias un
campo aquí, cambia el .schema.json en el mismo commit —
tests/test_os_event_schema.py cruza ambos.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class Risk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class Causality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_event_id: str | None = None
    trace_id: str | None = None


class AuditRef(BaseModel):
    """Referencia a auditoría REAL. merkle_hash solo puede venir del
    TransparencyLog; inventarlo viola OS-R9 (docs/risks/RISK_REGISTER.md)."""

    model_config = ConfigDict(extra="allow")

    merkle_hash: str | None = None
    previous_hash: str | None = None
    reversible: bool | None = None


class UiHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int | None = Field(default=None, ge=0, le=100)
    surface: list[str] | None = None
    motion: str | None = None


class OsEvent(BaseModel):
    """Evento canónico de Atlas OS (schemas/event.schema.json v1.0)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^evt_[A-Za-z0-9_-]+$")
    type: str
    timestamp: str
    schema_version: str = SCHEMA_VERSION
    source: str
    workspace_id: str | None = None
    intent_id: str | None = None
    process_id: str | None = None
    actor: str | None = None
    summary: str
    status: EventStatus
    risk: Risk
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    visible: bool
    simulated: bool | None = None
    payload: dict[str, Any]
    causality: Causality | None = None
    audit: AuditRef | None = None
    ui: UiHints | None = None


class GraphNode(BaseModel):
    """Nodo del Living Knowledge Graph (schemas/node.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^node_[A-Za-z0-9_-]+$")
    type: str
    label: str
    state: NodeState
    confidence: float = Field(ge=0.0, le=1.0)
    activity: float = Field(ge=0.0, le=1.0)
    risk: Risk
    source: str
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    """Arista del Living Knowledge Graph (schemas/edge.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^edge_[A-Za-z0-9_-]+$")
    source: str
    target: str
    relation: str
    weight: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
