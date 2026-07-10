"""Modelos pydantic de fabric/governance OS — espejo de schemas/*.schema.json.

Igual que atlas/events/schemas.py: la autoridad es el JSON Schema; esto valida
en runtime sin dependencia jsonschema.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atlas.events.schemas import Risk


class AuthMode(str, Enum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    HMAC = "hmac"
    LOCAL = "local"
    IMPORT_FILE = "import_file"
    NONE = "none"


class ConnectorMode(str, Enum):
    REAL = "real"
    MOCK = "mock"
    SANDBOX = "sandbox"


class ConnectorSpec(BaseModel):
    """schemas/connector.schema.json — jamás secretos planos."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(pattern=r"^conn_[A-Za-z0-9_-]+$")
    display_name: str
    provider: str
    auth_mode: AuthMode
    credential_reference: str | None = None
    read_capabilities: list[str]
    write_capabilities: list[str]
    risk_level: Risk
    permission_scope: list[str]
    sync_status: str = "never"
    last_sync: str | None = None
    health: str = "unknown"
    memory_policy: str
    automation_policy: str
    audit_policy: str
    mode: ConnectorMode
    revocation: str | None = None
    fallback: str | None = None
    legal_notes: str | None = None


class GateSpec(BaseModel):
    """schemas/gate.schema.json."""

    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(pattern=r"^gate_[A-Za-z0-9_-]+$")
    display_name: str
    applies_to: list[str]
    risk_threshold: Risk
    approval_mode: str
    default_decision: str
    enabled: bool = True
    notes: str | None = None


class PermissionEvaluation(BaseModel):
    """schemas/permission.schema.json — contrato de representación; la
    autoridad de governance sigue siendo governance/ + config/governance.json."""

    model_config = ConfigDict(extra="forbid")

    action: str
    resource: str
    actor: str | None = None
    decision: str
    risk: Risk
    reason: str
    policy_id: str | None = None
    gate_id: str | None = None
    evaluated_at: str
    reversible: bool | None = None


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    workspace_id: str | None = None


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    actor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
