"""Espejos pydantic de los contratos del Fabric — la autoridad es schemas/*.json.

Paridad vigilada por tests (required ↔ sin default), como atlas/events/schemas.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from atlas.events.schemas import Risk

__all__ = [
    "CapabilitySpec",
    "ConnectionRecipe",
    "ConnectorCategory",
    "ConnectorHealth",
    "ConnectorPack",
    "DataClass",
    "DefaultMode",
    "Difficulty",
    "GateStatus",
    "GateTicket",
    "HealthIssue",
    "HealthStatus",
    "PermissionsExplainer",
    "PolicyAppliesTo",
    "PolicyEffect",
    "PolicyRule",
    "RouteType",
    "SetupStep",
    "StepKind",
    "UnlessCondition",
]


class GateStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class GateTicket(BaseModel):
    """schemas/gate_ticket.schema.json — ceremonia de decisión humana."""

    model_config = ConfigDict(extra="forbid")

    gate_ticket_id: str = Field(pattern=r"^gt_[A-Za-z0-9_-]+$")
    gate_id: str = Field(pattern=r"^gate_[A-Za-z0-9_-]+$")
    action: str
    subject_ref: str
    risk: Risk
    status: GateStatus
    reason: str = Field(min_length=1)
    requested_by: str
    requested_at: str
    evidence: list[str]
    resolved_by: str | None = None
    resolved_at: str | None = None
    decision_note: str | None = None


class RouteType(str, Enum):
    """Peldaños de la Connection Ladder, en orden de preferencia (API-first)."""

    NATIVE_API = "native_api"
    MANAGED_OAUTH = "managed_oauth"
    OPENAPI_REST = "openapi_rest"
    ASYNCAPI_EVENTS = "asyncapi_events"
    WEBHOOKS = "webhooks"
    MCP = "mcp"
    DATABASE_FILE = "database_file"
    IMPORT_EXPORT_BATCH = "import_export_batch"
    BROWSER_EXTENSION_BRIDGE = "browser_extension_bridge"
    DESKTOP_AUTOMATION = "desktop_automation"
    COMPUTER_USE = "computer_use"
    HUMAN_MANUAL = "human_manual"


class ConnectorCategory(str, Enum):
    COMMUNICATION = "communication"
    AI_PROVIDER = "ai_provider"
    CRM = "crm"
    ERP_ACCOUNTING = "erp_accounting"
    ECOMMERCE = "ecommerce"
    FILES_DOCUMENTS = "files_documents"
    DATABASES = "databases"
    POS_RETAIL_RESTAURANT = "pos_retail_restaurant"
    NO_API_APPS = "no_api_apps"


class Difficulty(str, Enum):
    EASY = "easy"
    GUIDED = "guided"
    TECHNICAL = "technical"
    EXPERT = "expert"


class DefaultMode(str, Enum):
    READ_ONLY = "read_only"
    READ_DRAFT = "read_draft"
    IMPORT_ONLY = "import_only"
    FULL_GATED = "full_gated"


class StepKind(str, Enum):
    AUTOMATIC = "automatic"
    USER_ACTION = "user_action"
    MANUAL_SECRET = "manual_secret"
    EXTERNAL_PAGE = "external_page"
    FILE_PICK = "file_pick"


class DataClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    CREDENTIALS = "credentials"


class PolicyEffect(str, Enum):
    DENY = "deny"
    REQUIRE_GATE = "require_gate"
    ALLOW_READONLY = "allow_readonly"
    ALLOW = "allow"


class UnlessCondition(str, Enum):
    HUMAN_APPROVED = "human_approved"
    GATE_APPROVED = "gate_approved"
    LOCAL_ONLY = "local_only"
    SANDBOXED = "sandboxed"


class HealthStatus(str, Enum):
    NEVER_CONNECTED = "never_connected"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    AUTH_EXPIRED = "auth_expired"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class SetupStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    kind: StepKind
    description: str


class PermissionsExplainer(BaseModel):
    """En lenguaje llano: qué hará Atlas y qué NO hará con esta conexión."""

    model_config = ConfigDict(extra="forbid")

    will: list[str]
    will_not: list[str]


class CredentialSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_mode: str
    storage: str = Field(pattern=r"^credential_reference_only$")


class ConnectionRecipe(BaseModel):
    """schemas/connection_recipe.schema.json."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    human_name: str = Field(min_length=1)
    category: ConnectorCategory
    recommended_route: RouteType
    fallback_routes: list[RouteType]
    difficulty: Difficulty
    default_mode: DefaultMode
    safe_defaults: dict[str, bool]
    capabilities: list[str]
    gated_capabilities: dict[str, str]
    forbidden_capabilities: list[str]
    setup_steps: list[SetupStep] = Field(min_length=1)
    permissions_explainer: PermissionsExplainer
    demo: bool
    credential: CredentialSpec | None = None
    legal_notes: str | None = None


class ConnectorPack(BaseModel):
    """schemas/connector_pack.schema.json."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str = Field(pattern=r"^[a-z0-9_]+_pack$")
    sector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(min_length=1)
    connectors: list[str] = Field(min_length=1)
    setup_order: list[str] = Field(min_length=1)
    demo: bool
    optional_connectors: list[str] = Field(default_factory=list)
    rationale: str | None = None


class HealthIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    detail: str


class ConnectorHealth(BaseModel):
    """schemas/connector_health.schema.json."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    status: HealthStatus
    issues: list[HealthIssue]
    last_check: str | None = None
    simulated: bool = False


class CapabilitySpec(BaseModel):
    """schemas/capability.schema.json."""

    model_config = ConfigDict(extra="forbid")

    capability: str = Field(pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
    risk: Risk
    data_class: DataClass
    description: str = Field(min_length=1)
    gate_required: bool
    gate_id: str | None = Field(default=None, pattern=r"^gate_[A-Za-z0-9_-]+$")


class PolicyAppliesTo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    data_classes: list[DataClass] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)


class PolicyRule(BaseModel):
    """schemas/policy_rule.schema.json — hard=true está además en código."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(pattern=r"^pol_[a-z0-9_]+$")
    description: str = Field(min_length=1)
    applies_to: PolicyAppliesTo
    effect: PolicyEffect
    enabled: bool
    unless: list[UnlessCondition] = Field(default_factory=list)
    hard: bool = False
    notes: str | None = None
