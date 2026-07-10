"""Espejos pydantic del Business Core — la autoridad es schemas/*.json."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Activation",
    "AdaptiveQuestion",
    "Answer",
    "BusinessCore",
    "BusinessEntity",
    "Canonicality",
    "CanonicalityMode",
    "CoreStatus",
    "CreatedFrom",
    "CreatedFromKind",
    "EntityCandidate",
    "EntityKind",
    "EntityStatus",
    "FollowupRule",
    "InputType",
    "LegacyLink",
    "LegacyLinkMode",
    "Modules",
    "OnboardingSession",
    "Proposed",
    "QuestionOption",
    "QuestionPack",
    "QuestionValidation",
    "SessionStatus",
]


class EntityKind(str, Enum):
    CUSTOMER = "customer"
    CONTACT = "contact"
    COMPANY = "company"
    SUPPLIER = "supplier"
    PRODUCT = "product"
    SERVICE = "service"
    ORDER = "order"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    DELIVERY_NOTE = "delivery_note"
    STOCK_ITEM = "stock_item"
    TASK = "task"
    OPPORTUNITY = "opportunity"
    QUOTE = "quote"
    PROJECT = "project"
    CASE_FILE = "case_file"
    DOCUMENT = "document"
    COMMUNICATION = "communication"
    PAYMENT = "payment"
    EVENT = "event"
    NOTE = "note"
    RISK = "risk"
    EVIDENCE = "evidence"


class CoreStatus(str, Enum):
    DRAFT = "draft"
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    ARCHIVED = "archived"


class EntityStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CanonicalityMode(str, Enum):
    EXTERNAL_CANONICAL = "external_canonical"
    ATLAS_CANONICAL = "atlas_canonical"
    HYBRID_CANONICAL = "hybrid_canonical"


class CreatedFromKind(str, Enum):
    ONBOARDING = "onboarding"
    IMPORT = "import"
    LEGACY_LINK = "legacy_link"
    MANUAL = "manual"


class LegacyLinkMode(str, Enum):
    READ_ONLY_MIRROR = "read_only_mirror"
    PARTIAL_SYNC = "partial_sync"
    MIGRATION = "migration"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PREVIEW = "preview"
    CONFIRMED = "confirmed"
    ABANDONED = "abandoned"


class InputType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    TEXT = "text"
    NUMBER = "number"
    FILE_REF = "file_ref"


class Canonicality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: CanonicalityMode
    source_of_truth: str
    per_entity: dict[str, CanonicalityMode] = Field(default_factory=dict)


class Modules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crm: bool
    erp: bool


class CreatedFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CreatedFromKind
    ref: str


class Activation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(pattern=r"^gate_[A-Za-z0-9_-]+$")
    approved: bool
    approved_by: str | None = None
    approved_at: str | None = None


class LegacyLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str
    mode: LegacyLinkMode
    sync_enabled: bool


class BusinessCore(BaseModel):
    """schemas/business_core.schema.json — draft-first, activación gateada."""

    model_config = ConfigDict(extra="forbid")

    business_core_id: str = Field(pattern=r"^bc_[A-Za-z0-9_-]+$")
    sector_id: str
    status: CoreStatus
    canonicality: Canonicality
    modules: Modules
    entity_ids: list[str]
    created_from: CreatedFrom
    activation: Activation
    created_at: str
    updated_at: str
    legacy_link: LegacyLink | None = None
    demo: bool = False


class BusinessEntity(BaseModel):
    """schemas/business_entity.schema.json."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(pattern=r"^be_[A-Za-z0-9_-]+$")
    business_core_id: str = Field(pattern=r"^bc_[A-Za-z0-9_-]+$")
    kind: EntityKind
    label: str = Field(min_length=1)
    status: EntityStatus
    data: dict[str, Any]
    source_refs: list[str]
    requires_review: bool
    confidence: float | None = Field(default=None, ge=0, le=1)
    canonical_source: str | None = None


class EntityCandidate(BaseModel):
    """schemas/entity_candidate.schema.json — requires_review es const true."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    kind: EntityKind
    label: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    source_refs: list[str] = Field(min_length=1)
    proposed_data: dict[str, Any]
    requires_review: Literal[True]


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str


class QuestionValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_selected: int | None = Field(default=None, ge=0)
    max_selected: int | None = Field(default=None, ge=1)
    pattern: str | None = None
    min: float | None = None
    max: float | None = None


class FollowupRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    when_option: str
    ask: str


class AdaptiveQuestion(BaseModel):
    """Pregunta concreta: declara por qué, para qué y qué estructura produce."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1)
    why_this_is_needed: str = Field(min_length=1)
    what_atlas_will_do_with_it: str = Field(min_length=1)
    input_type: InputType
    options: list[QuestionOption]
    validation: QuestionValidation
    followup_rules: list[FollowupRule]
    skip_allowed: bool
    uncertainty_allowed: bool
    resulting_entities: list[str]
    resulting_capabilities: list[str]
    resulting_workbenches: list[str]


class QuestionPack(BaseModel):
    """schemas/question_pack.schema.json."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str = Field(pattern=r"^qp_[a-z0-9_]+$")
    sector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(min_length=1)
    questions: list[AdaptiveQuestion] = Field(min_length=1)


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    value: str | list[str] | float | None
    uncertain: bool
    interpreted: str
    confirmed: bool


class Proposed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[str]
    capabilities: list[str]
    workbenches: list[str]
    connector_pack: str | None


class OnboardingSession(BaseModel):
    """schemas/onboarding_session.schema.json — lazo pregunta→interpreta→confirma."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^obs_[A-Za-z0-9_-]+$")
    sector_id: str
    pack_id: str
    status: SessionStatus
    answers: list[Answer]
    pending_questions: list[str]
    created_at: str
    updated_at: str
    understanding_summary: str | None = None
    proposed: Proposed | None = None
    demo: bool = False
