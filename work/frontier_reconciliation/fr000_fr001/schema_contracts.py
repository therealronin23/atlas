"""Static JSON Schema contracts for the FR-000/FR-001 machine-readable outputs.

The contracts in this module are deliberately independent from the generated
records.  A validator may therefore use them to detect generator drift instead
of deriving a schema from the very output it is supposed to check.

No runtime dependency is required to import this module.  Consumers may use
``jsonschema.Draft202012Validator`` when that package is already available, or
another Draft 2020-12 implementation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

CONFIDENCE = ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
RELEVANCE = ["HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"]
CATEGORIES = [
    "CODE",
    "TEST",
    "ADR",
    "CANON",
    "SPEC",
    "PLAN",
    "DESIGN",
    "RESEARCH",
    "BENCHMARK",
    "FIXTURE",
    "RUNTIME_CONFIG",
    "CI",
    "PRODUCT",
    "PROTOTYPE",
    "GENERATED",
    "HISTORICAL",
    "TOOLING",
    "SCHEMA",
    "EVIDENCE",
    "OTHER",
]
LIFECYCLES = [
    "CURRENT",
    "HISTORICAL",
    "ARCHIVED",
    "SUPERSEDED",
    "GENERATED",
    "UNKNOWN",
]
MATURITIES = [
    "MISSING",
    "RESEARCH_ONLY",
    "PROPOSED_DESIGN",
    "ACCEPTED_DESIGN",
    "CODE_PRESENT",
    "TESTED",
    "WIRED",
    "RUNTIME_CONFIGURED",
    "LIVE_VERIFIED",
    "PRODUCT_ACCEPTED",
    "SUPERSEDED",
    "CONTRADICTED",
    "UNKNOWN",
]
DECISION_STATUSES = [
    "ACTIVE",
    "PROVISIONAL",
    "SUPERSEDED",
    "REJECTED",
    "CONTRADICTED",
    "HISTORICAL",
    "UNKNOWN",
]
FRONTIER_ASSESSMENTS = [
    "CONFIRMED",
    "REFORMULATE",
    "MERGE_CANDIDATE",
    "SPLIT_CANDIDATE",
    "DELETE_CANDIDATE",
    "SUPERSEDED",
    "HISTORICAL",
    "NEW_EVIDENCE",
    "UNKNOWN",
]
ARTIFACT_MAPPING_STATUSES = [
    "MAPPED",
    "DUPLICATE",
    "SUPERSEDED",
    "HISTORICAL",
    "IRRELEVANT",
    "NEW_FRONTIER",
    "UNKNOWN",
]
MEASUREMENT_VALIDITY = [
    "VALID",
    "PARTIAL",
    "INCONCLUSIVE",
    "INVALID",
    "NOT_APPLICABLE",
]


def _nonempty_string() -> dict[str, Any]:
    return {"type": "string", "minLength": 1}


def _nullable_string() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _string_array(*, min_items: int = 0, unique: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "items": _nonempty_string(),
        "minItems": min_items,
    }
    if unique:
        schema["uniqueItems"] = True
    return schema


def _confidence() -> dict[str, Any]:
    return {"type": "string", "enum": CONFIDENCE}


def _program() -> dict[str, Any]:
    return {
        "type": "string",
        "enum": [*(f"P{number:02d}" for number in range(13)), "P04P05", "UNKNOWN"],
    }


def _id_string() -> dict[str, Any]:
    return {"type": "string", "minLength": 2, "pattern": r"^[^\s].*[^\s]$|^[^\s]$"}


def _schema(title: str, required: list[str], properties: dict[str, Any], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "$schema": DRAFT_2020_12,
        "title": title,
        "type": "object",
        "required": required,
        "properties": properties,
        # The generator may add qualified audit metadata, but the named core
        # contract may not disappear or change type.
        "additionalProperties": True,
    }
    result.update(extra)
    return result


SOURCE_SCHEMA = _schema(
    "FR-000 source coverage record",
    [
        "source_id",
        "path",
        "sha256",
        "content_hash",
        "git_blob_sha",
        "git_mode",
        "size_bytes",
        "category",
        "lifecycle",
        "lifecycle_basis",
        "apparent_owner",
        "program",
        "related_frontier_ids",
        "authority_relevance",
        "runtime_relevance",
        "evidence_relevance",
        "generated_from",
        "superseded_by",
        "project_owned",
        "third_party_or_vendor",
        "tracked_atlas_n",
        "conceptual_entity",
        "canonical_content_copy",
        "content_duplicate_count",
        "semantic_duplicate_count",
        "semantic_normalization_hash",
        "source_family_id",
        "confidence",
        "independence_key",
    ],
    {
        "source_id": {"type": "string", "pattern": r"^SRC-[0-9A-F]{8,}$"},
        "path": _nonempty_string(),
        "sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "content_hash": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
        "git_blob_sha": {"type": "string", "pattern": r"^[0-9a-f]{40}$"},
        "git_mode": {"type": "string", "pattern": r"^[0-7]{6}$"},
        "size_bytes": {"type": "integer", "minimum": 0},
        "category": {"type": "string", "enum": CATEGORIES},
        "lifecycle": {"type": "string", "enum": LIFECYCLES},
        "lifecycle_basis": _nonempty_string(),
        "apparent_owner": _nonempty_string(),
        "program": _program(),
        "related_frontier_ids": _string_array(unique=True),
        "authority_relevance": {"type": "string", "enum": RELEVANCE},
        "runtime_relevance": {"type": "string", "enum": RELEVANCE},
        "evidence_relevance": {"type": "string", "enum": RELEVANCE},
        "generated_from": _string_array(unique=True),
        "superseded_by": _string_array(unique=True),
        "project_owned": {"type": "boolean"},
        "third_party_or_vendor": {"type": "boolean"},
        "tracked_atlas_n": {"type": "boolean"},
        "conceptual_entity": {"type": "boolean"},
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
        "canonical_content_copy": _nonempty_string(),
        "content_duplicate_count": {"type": "integer", "minimum": 1},
        "semantic_duplicate_count": {"type": "integer", "minimum": 0},
        "semantic_normalization_hash": {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
            ]
        },
        "source_family_id": _nonempty_string(),
    },
)


MATURITY_TRANSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["to", "evidence_ids", "locator"],
    "properties": {
        "to": {"type": "string", "enum": MATURITIES},
        "evidence_ids": _string_array(min_items=1, unique=True),
        "locator": {
            "anyOf": [
                _nonempty_string(),
                {"type": "array", "minItems": 1},
                {"type": "object", "minProperties": 1},
            ]
        },
        "scope_limit": _nonempty_string(),
    },
    "additionalProperties": True,
}


COMPONENT_SCHEMA = _schema(
    "FR-000 current implementation-unit record",
    [
        "component_id",
        "component_kind",
        "name",
        "purpose",
        "purpose_confidence",
        "owner",
        "program",
        "source_paths",
        "public_contracts",
        "maturity",
        "maturity_transitions",
        "direct_test_locators",
        "tested_property_locators",
        "excluded_test_locators",
        "related_frontier_ids",
        "current",
        "confidence",
        "independence_key",
        "epistemic_limit",
    ],
    {
        "component_id": {"type": "string", "pattern": r"^COMP-[0-9A-F]{8,}$"},
        "component_kind": _nonempty_string(),
        "name": _nonempty_string(),
        "capability_group": _nullable_string(),
        "purpose": _nonempty_string(),
        "purpose_confidence": _confidence(),
        "owner": _nonempty_string(),
        "program": _program(),
        "source_paths": _string_array(min_items=1, unique=True),
        "public_contracts": _string_array(unique=True),
        "maturity": {"type": "string", "enum": MATURITIES},
        "maturity_transitions": {
            "type": "array",
            "minItems": 1,
            "items": MATURITY_TRANSITION_SCHEMA,
        },
        "direct_test_locators": _string_array(unique=True),
        "tested_property_locators": _string_array(unique=True),
        "excluded_test_locators": _string_array(unique=True),
        "related_frontier_ids": _string_array(unique=True),
        "current": {"const": True},
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
        "epistemic_limit": _nonempty_string(),
    },
)


AUTHORITY_COMMON_PROPERTIES: dict[str, Any] = {
    "record_kind": {
        "type": "string",
        "enum": ["COMPONENT_AUTHORITY", "STATE_DOMAIN_AUTHORITY"],
    },
    "authority_id": {"type": "string", "pattern": r"^AUTH(?:-DOMAIN)?-[0-9A-F]{8,}$"},
    "confidence": _confidence(),
}

COMPONENT_AUTHORITY_PROPERTIES: dict[str, Any] = {
    "component": _nonempty_string(),
    "owner": _nonempty_string(),
    "program": _nonempty_string(),
    "callers": _string_array(),
    "writers": _string_array(),
    "state_owner": _string_array(),
    "read_paths": _string_array(),
    "write_paths": _string_array(),
    "alternative_paths": _string_array(),
    "bypasses": _string_array(),
    "public_ports": _string_array(),
    "mutation_boundaries": _string_array(),
    "failure_semantics": _string_array(),
    "source_paths": _string_array(min_items=1),
    "public_contracts": _string_array(),
    "observed_maturity_claim": {
        "type": "object",
        "required": ["level", "evidence", "test_present"],
        "properties": {
            "level": _nonempty_string(),
            "evidence": _string_array(),
            "test_present": _string_array(),
        },
        "additionalProperties": True,
    },
    "related_frontier_ids": _string_array(unique=True),
    "epistemic_limit": _nonempty_string(),
}

STATE_AUTHORITY_PROPERTIES: dict[str, Any] = {
    "domain": _nonempty_string(),
    "canonical_owner": _nonempty_string(),
    "writers": _string_array(min_items=1),
    "risk": _nonempty_string(),
    "multiple_writers": {"type": "boolean"},
}

AUTHORITY_SCHEMA = _schema(
    "FR-000 caller/writer/authority record",
    ["record_kind", "authority_id", "confidence"],
    {
        **AUTHORITY_COMMON_PROPERTIES,
        **COMPONENT_AUTHORITY_PROPERTIES,
        **STATE_AUTHORITY_PROPERTIES,
    },
    oneOf=[
        {
            "properties": {"record_kind": {"const": "COMPONENT_AUTHORITY"}},
            "required": [
                "component",
                "owner",
                "program",
                "callers",
                "writers",
                "state_owner",
                "read_paths",
                "write_paths",
                "alternative_paths",
                "bypasses",
                "public_ports",
                "mutation_boundaries",
                "failure_semantics",
                "source_paths",
                "public_contracts",
                "observed_maturity_claim",
                "related_frontier_ids",
                "epistemic_limit",
            ],
        },
        {
            "properties": {"record_kind": {"const": "STATE_DOMAIN_AUTHORITY"}},
            "required": ["domain", "canonical_owner", "writers", "risk", "multiple_writers"],
        },
    ],
)


ANOMALY_SCHEMA = _schema(
    "FR-000 caller/writer anomaly",
    [
        "anomaly_id",
        "kind",
        "severity",
        "finding",
        "evidence",
        "status",
        "resolution",
        "independence_key",
    ],
    {
        "anomaly_id": _id_string(),
        "kind": {
            "type": "string",
            "enum": [
                "audit-bypass",
                "audit-gap",
                "authority-duplication",
                "budget-semantics",
                "bypass",
                "caller-gap",
                "error-swallow",
                "graph-coverage",
                "legacy/mock-gap",
                "mocked-vs-real-gap",
                "multiple-writers",
                "runtime-gap",
                "secrets-boundary",
                "untraced-caller",
                "writer-gap",
            ],
        },
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "finding": _nonempty_string(),
        "evidence": _string_array(min_items=1),
        "status": {
            "type": "string",
            "enum": ["OPEN", "CLOSED", "SUPERSEDED_BY_SELF_REVIEW"],
        },
        "resolution": _nonempty_string(),
        "superseded_by_self_review": _nullable_string(),
        "independence_key": _nonempty_string(),
    },
)


SUPERSESSION_RELATIONS = [
    "CONTRADICTS",
    "DOES_NOT_AMEND",
    "DOES_NOT_SUPERSEDE",
    "EXTENDS",
    "EXTENDS_PARTIALLY",
    "PARTIALLY_SUPERSEDES",
    "PROMOTES_SLICE",
    "REFINES",
    "RESOLVES_SCOPE",
    "RETIRES",
    "REVISES",
    "SUPERSEDES",
    "SUPERSEDES_FRAMING",
]

SUPERSESSION_SCHEMA = _schema(
    "FR-001 explicit decision relation",
    [
        "edge_id",
        "relation",
        "from_ids",
        "to_ids",
        "from",
        "to",
        "scope",
        "source",
        "explicit",
        "chronology_inferred",
        "confidence",
        "independence_key",
    ],
    {
        "edge_id": _id_string(),
        "relation": {"type": "string", "enum": SUPERSESSION_RELATIONS},
        "from_ids": _string_array(min_items=1, unique=True),
        "to_ids": _string_array(min_items=1, unique=True),
        "from": _nonempty_string(),
        "to": _nonempty_string(),
        "scope": _nonempty_string(),
        "date": _nullable_string(),
        "authority": _nullable_string(),
        "preserved": _string_array(),
        "annulled": _string_array(),
        "source_path": _nullable_string(),
        "source_ref": _nullable_string(),
        "source": _nonempty_string(),
        "explicit": {"const": True},
        "chronology_inferred": {"const": False},
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
    },
)


DECISION_SCHEMA = _schema(
    "FR-001 decision reality record",
    [
        "decision_id",
        "record_kind",
        "title",
        "date",
        "status",
        "source_status",
        "authority",
        "authority_scope",
        "current",
        "program",
        "programs_related",
        "locators",
        "supersedes",
        "superseded_by",
        "contradicts",
        "depends_on",
        "implemented_by",
        "tested_by",
        "runtime_evidence",
        "non_supersession_relations",
        "falsifier",
        "falsifier_status",
        "source_independence",
        "source_occurrence_count",
        "unique_content_hash_count",
        "semantic_duplicate_of",
        "decision_subject_key",
        "confidence",
        "independence_key",
    ],
    {
        "decision_id": _id_string(),
        "record_kind": _nonempty_string(),
        "title": _nonempty_string(),
        "date": _nullable_string(),
        "status": {"type": "string", "enum": DECISION_STATUSES},
        "source_status": _nullable_string(),
        "authority": _nullable_string(),
        "authority_scope": {
            "type": "string",
            "enum": [
                "CURRENT",
                "CURRENT_CANON_REGISTRY_CLAIM",
                "GRAPH_ENDPOINT_ONLY",
                "HISTORICAL_OR_EXTERNAL_DISPOSITION",
            ],
        },
        "current": {"type": "boolean"},
        "program": _program(),
        "programs_related": _string_array(),
        "locators": _string_array(min_items=1),
        "supersedes": _string_array(unique=True),
        "superseded_by": _string_array(unique=True),
        "contradicts": _string_array(unique=True),
        "depends_on": _string_array(unique=True),
        "non_supersession_relations": _string_array(unique=True),
        "implemented_by": _string_array(),
        "tested_by": _string_array(),
        "runtime_evidence": _string_array(),
        "falsifier": _nonempty_string(),
        "falsifier_status": {
            "type": "string",
            "enum": [
                "PASS",
                "FAIL",
                "NOT_RUN",
                "NOT_RUN_IN_FR000_FR001",
                "NOT_APPLICABLE",
                "UNKNOWN",
            ],
        },
        "evidence_qualification": _nullable_string(),
        "source_independence": _nonempty_string(),
        "source_occurrence_count": {"type": "integer", "minimum": 1},
        "unique_content_hash_count": {"type": "integer", "minimum": 1},
        "semantic_duplicate_of": _nullable_string(),
        "decision_subject_key": _nonempty_string(),
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
    },
)


FRONTIER_R0_PROPERTIES: dict[str, Any] = {
    "frontier_id": {"type": "string", "pattern": r"^FR-P(?:0[0-9]|1[0-2])-[0-9]{3}$"},
    "name": _nonempty_string(),
    "program": {"type": "string", "pattern": r"^(?:P(?:0[0-9]|1[0-2])|P04P05)$"},
    "pack_assessment": _nonempty_string(),
    "pack_disposition": _nonempty_string(),
    "pack_epistemic_status": _nonempty_string(),
    "assessment": {"type": "string", "enum": FRONTIER_ASSESSMENTS},
    "examined": {"const": True},
    "evidence_ids": _string_array(min_items=1, unique=True),
    "referenced_current_sources_present": _string_array(unique=True),
    "mapping_note": _nonempty_string(),
    "case_for": _nonempty_string(),
    "case_against": _nonempty_string(),
    "merge_group": _nullable_string(),
    "split_group": _nullable_string(),
}

ARTIFACT_MAPPING_PROPERTIES: dict[str, Any] = {
    "artifact_id": _nonempty_string(),
    "artifact_locator": {
        "anyOf": [_nonempty_string(), _string_array(min_items=1)]
    },
    "mapping_status": {"type": "string", "enum": ARTIFACT_MAPPING_STATUSES},
    "frontier_ids": _string_array(unique=True),
    "candidate_program": _program(),
    "reason": _nonempty_string(),
}

FRONTIER_MAPPING_SCHEMA = _schema(
    "FR-001 frontier and current-artifact cross-mapping record",
    ["record_kind", "confidence", "independence_key"],
    {
        "record_kind": {
            "type": "string",
            "enum": ["FRONTIER_R0", "SOURCE", "COMPONENT", "DECISION"],
        },
        **FRONTIER_R0_PROPERTIES,
        **ARTIFACT_MAPPING_PROPERTIES,
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
    },
    oneOf=[
        {
            "properties": {"record_kind": {"const": "FRONTIER_R0"}},
            "required": list(FRONTIER_R0_PROPERTIES),
        },
        {
            "properties": {
                "record_kind": {
                    "type": "string",
                    "enum": ["SOURCE", "COMPONENT", "DECISION"],
                }
            },
            "required": list(ARTIFACT_MAPPING_PROPERTIES),
        },
    ],
)


CANDIDATE_NEW_FRONTIER_SCHEMA = _schema(
    "FR-001 candidate new frontier",
    [
        "problem",
        "why_distinct",
        "evidence",
        "affected_components",
        "dependencies",
        "proposed_program",
        "confidence",
    ],
    {
        "candidate_frontier_id": _nonempty_string(),
        "problem": _nonempty_string(),
        "why_distinct": _nonempty_string(),
        "evidence": _string_array(min_items=1, unique=True),
        "affected_components": _string_array(min_items=1, unique=True),
        "dependencies": _string_array(unique=True),
        "proposed_program": _program(),
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
    },
)


CONTRADICTION_SCHEMA = _schema(
    "FR-000/FR-001 contradiction",
    [
        "contradiction_id",
        "claim",
        "counterevidence",
        "status",
        "origin",
        "frontier_ids",
        "evidence_ids",
        "resolution",
        "resolution_status",
        "confidence",
        "independence_key",
    ],
    {
        "contradiction_id": _nonempty_string(),
        "claim": _nonempty_string(),
        "counterevidence": {
            "anyOf": [_nonempty_string(), _string_array(min_items=1)]
        },
        "status": _nonempty_string(),
        "origin": {
            "type": "string",
            "enum": [
                "CURRENT_AUDIT",
                "CURRENT_COMPONENT_AUTHORITY_AUDIT",
                "FRONTIER_PACK",
                "SELF_REVIEW",
            ],
        },
        "frontier_ids": _string_array(unique=True),
        "evidence_ids": _string_array(min_items=1, unique=True),
        "resolution": _nonempty_string(),
        "resolution_status": {
            "type": "string",
            "enum": ["OPEN", "CLOSED", "SUPERSEDED_BY_SELF_REVIEW"],
        },
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
        "superseded_by_self_review": _nullable_string(),
    },
)


NEGATIVE_EVIDENCE_SCHEMA = _schema(
    "FR-000/FR-001 bounded negative evidence",
    [
        "negative_evidence_id",
        "claim_examined",
        "observed_absence",
        "search_scope",
        "locator",
        "caveat",
        "effect_on_claim",
        "confidence",
        "independence_key",
    ],
    {
        "negative_evidence_id": {"type": "string", "pattern": r"^NEG-[0-9A-F]{8,}$"},
        "claim_examined": {"type": "string", "pattern": r"^CLAIM-[A-Z0-9-]+$"},
        "observed_absence": _nonempty_string(),
        "search_scope": {
            "anyOf": [_nonempty_string(), _string_array(min_items=1)]
        },
        "locator": {
            "anyOf": [_nonempty_string(), _string_array(min_items=1)]
        },
        "caveat": _nonempty_string(),
        "effect_on_claim": _nonempty_string(),
        # Retained as an optional compatibility field; it cannot substitute for
        # the explicit effect_on_claim relation above.
        "supports": _string_array(unique=True),
        "confidence": _confidence(),
        "independence_key": _nonempty_string(),
    },
)


TRISTATE = {
    "oneOf": [
        {"type": "boolean"},
        {"const": "unknown"},
    ]
}

EVIDENCE_SCHEMA = _schema(
    "FR-000/FR-001 evidence quality record",
    [
        "evidence_id",
        "type",
        "locator",
        "source_hash",
        "raw_preserved",
        "reproducible",
        "independently_verifiable",
        "freshness",
        "measurement_validity",
        "contamination",
        "independence_key",
        "supports",
        "contradicts",
        "confidence",
        "observation",
    ],
    {
        "evidence_id": {"type": "string", "pattern": r"^EV-[A-Z0-9-]+$"},
        "type": _nonempty_string(),
        "locator": {
            "anyOf": [
                _nonempty_string(),
                _string_array(min_items=1),
                {"type": "object", "minProperties": 1},
            ]
        },
        "source_hash": {
            "anyOf": [
                {"type": "null"},
                _nonempty_string(),
            ]
        },
        "raw_preserved": {"type": "boolean"},
        "reproducible": TRISTATE,
        "independently_verifiable": TRISTATE,
        "freshness": {"type": "string", "enum": ["current", "historical", "unknown"]},
        "measurement_validity": {"type": "string", "enum": MEASUREMENT_VALIDITY},
        "contamination": _string_array(unique=True),
        "independence_key": _nonempty_string(),
        "supports": _string_array(unique=True),
        "contradicts": _string_array(unique=True),
        "derived_from_evidence_ids": _string_array(unique=True),
        "confidence": _confidence(),
        "observation": _nonempty_string(),
    },
)


UNKNOWN_SCHEMA = _schema(
    "FR-000/FR-001 explicit unknown",
    [
        "unknown_id",
        "question",
        "status",
        "origin",
        "closure_condition",
        "evidence_ids_or_locators",
        "classification",
        "confidence_that_unknown_is_real",
        "independence_key",
    ],
    {
        "unknown_id": {"type": "string", "pattern": r"^UNK-[0-9A-F]{8,}$"},
        "question": _nonempty_string(),
        "status": {"type": "string", "enum": ["OPEN", "CLOSED"]},
        "origin": _nonempty_string(),
        "closure_condition": _nonempty_string(),
        "evidence_ids_or_locators": _string_array(unique=True),
        "classification": {"const": "UNKNOWN"},
        "confidence_that_unknown_is_real": _confidence(),
        "independence_key": _nonempty_string(),
    },
)


UNCLASSIFIED_SCHEMA = _schema(
    "FR-000/FR-001 unclassified-current registry entry",
    [
        "unclassified_id",
        "record_kind",
        "locator",
        "reason",
        "current",
        "independence_key",
    ],
    {
        "unclassified_id": _nonempty_string(),
        "record_kind": {
            "type": "string",
            "enum": ["SOURCE", "COMPONENT", "DECISION", "FRONTIER", "OTHER"],
        },
        "locator": {
            "anyOf": [_nonempty_string(), _string_array(min_items=1)]
        },
        "reason": _nonempty_string(),
        "current": {"const": True},
        "independence_key": _nonempty_string(),
    },
)


COVERAGE_RATIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["numerator", "denominator", "ratio", "percent"],
    "properties": {
        "numerator": {"type": "integer", "minimum": 0},
        "denominator": {"type": "integer", "minimum": 0},
        "ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "percent": {"type": "number", "minimum": 0, "maximum": 100},
    },
    "additionalProperties": False,
}

BASELINE_COVERAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tag", "commit", "tree"],
    "properties": {
        "tag": {"const": "atlas-n-cr001-20260820"},
        "commit": {"const": "df4fbe7a96c70507094c24c7bf553efd297cc80a"},
        "tree": {"const": "b790640b12ebff8eb100939f9f7a92f02de0b502"},
    },
    "additionalProperties": False,
}

COVERAGE_COUNTER_FIELDS = [
    "all_tracked_sources_total",
    "all_tracked_sources_classified",
    "current_sources_total",
    "current_sources_classified",
    "current_components_total",
    "current_components_mapped",
    "all_decisions_total",
    "all_decisions_classified",
    "historical_decisions_total",
    "current_decisions_total",
    "current_decisions_classified",
    "frontier_r0_total",
    "frontier_r0_examined",
    "candidate_new_frontiers",
    "merge_candidate_groups",
    "merge_candidate_frontier_rows",
    "split_candidate_groups",
    "split_candidate_frontier_rows",
    "contradictions",
    "unknowns",
    "unclassified_current",
]

COVERAGE_SCHEMA = _schema(
    "FR-000/FR-001 coverage report",
    [
        "baseline",
        "denominator_definitions",
        *COVERAGE_COUNTER_FIELDS,
        "CURRENT_SOURCE_COVERAGE",
        "CURRENT_COMPONENT_COVERAGE",
        "CURRENT_DECISION_COVERAGE",
        "CURRENT_FRONTIER_MAPPING_COVERAGE",
        "mapping_status_counts",
        "unknown_classifications_by_dimension",
        "unknown_classifications_total",
        "resolution_ratios_by_dimension",
        "stop_conditions",
        "classification_note",
    ],
    {
        "baseline": BASELINE_COVERAGE_SCHEMA,
        "denominator_definitions": {
            "type": "object",
            "required": ["source_universe", "components", "decisions", "frontiers"],
            "properties": {
                "source_universe": _nonempty_string(),
                "components": _nonempty_string(),
                "decisions": _nonempty_string(),
                "frontiers": _nonempty_string(),
            },
            "additionalProperties": True,
        },
        **{field: {"type": "integer", "minimum": 0} for field in COVERAGE_COUNTER_FIELDS},
        "CURRENT_SOURCE_COVERAGE": COVERAGE_RATIO_SCHEMA,
        "CURRENT_COMPONENT_COVERAGE": COVERAGE_RATIO_SCHEMA,
        "CURRENT_DECISION_COVERAGE": COVERAGE_RATIO_SCHEMA,
        "CURRENT_FRONTIER_MAPPING_COVERAGE": COVERAGE_RATIO_SCHEMA,
        "mapping_status_counts": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0},
        },
        "unknown_classifications_by_dimension": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0},
        },
        "unknown_classifications_total": {"type": "integer", "minimum": 0},
        "resolution_ratios_by_dimension": {
            "type": "object",
            "additionalProperties": COVERAGE_RATIO_SCHEMA,
        },
        "stop_conditions": {
            "type": "object",
            "minProperties": 10,
            "additionalProperties": {"type": "boolean"},
        },
        "classification_note": _nonempty_string(),
    },
)


MANIFEST_BASELINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "version",
        "checkpoint",
        "tag",
        "tag_object",
        "peeled_commit",
        "tree",
        "identity_verified",
    ],
    "properties": {
        "version": {"const": "Atlas 0.12.0"},
        "checkpoint": {"const": "CR-001"},
        "tag": {"const": "atlas-n-cr001-20260820"},
        "tag_object": {"type": "string", "pattern": r"^[0-9a-f]{40}$"},
        "peeled_commit": {"const": "df4fbe7a96c70507094c24c7bf553efd297cc80a"},
        "tree": {"const": "b790640b12ebff8eb100939f9f7a92f02de0b502"},
        "identity_verified": {"const": True},
        "tag_semantics_note": _nonempty_string(),
    },
    "additionalProperties": True,
}

F26_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "execution_outcome",
        "automatic_grade",
        "measurement_validity",
        "rerun_in_this_audit",
    ],
    "properties": {
        "execution_outcome": {"const": "FAIL"},
        "automatic_grade": {"const": "1/6"},
        "measurement_validity": {"const": "INCONCLUSIVE"},
        "rerun_in_this_audit": {"const": False},
        "notification_surface": _nonempty_string(),
    },
    "additionalProperties": True,
}

MANIFEST_SCHEMA = _schema(
    "FR-000/FR-001 execution manifest",
    [
        "execution_id",
        "generated_at",
        "status",
        "baseline",
        "state_categories",
        "graph",
        "tests",
        "f26",
        "semgrep",
        "required_files",
        "phase_records",
        "coverage_report",
        "functional_code_modified",
        "docs_index_modified",
        "commit_created",
        "staged",
        "prohibited_actions_performed",
        "PRESERVED_CONSTRAINTS",
        "NEW_EVIDENCE",
        "INVALIDATED_CLAIMS",
        "NEW_UNKNOWNS",
        "NEW_CONTRADICTIONS",
        "UNCLASSIFIED_COUNT",
    ],
    {
        "execution_id": _nonempty_string(),
        "generated_at": {"type": "string", "format": "date-time"},
        "status": {
            "type": "string",
            "enum": [
                "READY_FOR_EXTERNAL_ADVERSARIAL_REVIEW",
                "INCOMPLETE",
                "CHECKPOINT_IDENTITY_MISMATCH",
                "BLOCKED",
            ],
        },
        "baseline": MANIFEST_BASELINE_SCHEMA,
        "state_categories": {
            "type": "object",
            "required": [
                "TRACKED_ATLAS_N",
                "OPERATOR_INPUT",
                "GENERATED_AUDIT_OUTPUT",
                "UNRELATED_LOCAL_STATE",
            ],
            "properties": {
                "TRACKED_ATLAS_N": {"type": "object", "minProperties": 2},
                "OPERATOR_INPUT": {"type": "object", "minProperties": 3},
                "GENERATED_AUDIT_OUTPUT": {"type": "object", "minProperties": 2},
                "UNRELATED_LOCAL_STATE": {"type": "object", "minProperties": 1},
            },
            "additionalProperties": False,
        },
        "skill_installation": {"type": "object"},
        "graph": {
            "type": "object",
            "required": ["status", "commit", "modules_latest", "raw_queries", "limit"],
            "properties": {
                "status": {"type": "string", "enum": ["FRESH", "STALE", "UNKNOWN"]},
                "commit": {"type": ["string", "null"]},
                "modules_latest": {"type": "integer", "minimum": 0},
                "bitemporal_nodes": {"type": "integer", "minimum": 0},
                "import_edges": {"type": "integer", "minimum": 0},
                "raw_queries": _nonempty_string(),
                "limit": _nonempty_string(),
            },
            "additionalProperties": True,
        },
        "tests": {"type": "object", "minProperties": 1},
        "f26": F26_SCHEMA,
        "semgrep": {
            "type": "object",
            "required": ["rescanned", "classification"],
            "properties": {
                "rescanned": {"const": False},
                "classification": {
                    "type": "array",
                    "contains": {"const": "RAW_EVIDENCE_NOT_RETAINED"},
                    "minContains": 1,
                },
            },
            "additionalProperties": True,
        },
        "required_files": _string_array(min_items=21, unique=True),
        "phase_records": _string_array(min_items=1, unique=True),
        "coverage_report": COVERAGE_SCHEMA,
        "functional_code_modified": {"const": False},
        "docs_index_modified": {"const": False},
        "commit_created": {"type": "boolean"},
        "staged": {"type": "boolean"},
        "prohibited_actions_performed": {"type": "array", "maxItems": 0},
        "PRESERVED_CONSTRAINTS": _string_array(min_items=1),
        "NEW_EVIDENCE": _string_array(),
        "INVALIDATED_CLAIMS": _string_array(),
        "NEW_UNKNOWNS": {"type": "integer", "minimum": 0},
        "NEW_CONTRADICTIONS": {"type": "integer", "minimum": 0},
        "UNCLASSIFIED_COUNT": {"type": "integer", "minimum": 0},
    },
)


JSONL_SCHEMA_CONTRACTS: dict[str, dict[str, Any]] = {
    "01_SOURCE_COVERAGE_REGISTRY.jsonl": SOURCE_SCHEMA,
    "03_CURRENT_COMPONENT_MAP.jsonl": COMPONENT_SCHEMA,
    "04_AUTHORITY_MAP.jsonl": AUTHORITY_SCHEMA,
    "05_CALLER_WRITER_ANOMALIES.jsonl": ANOMALY_SCHEMA,
    "06_SUPERSESSION_GRAPH.jsonl": SUPERSESSION_SCHEMA,
    "07_DECISION_REALITY_MAP.jsonl": DECISION_SCHEMA,
    "08_FRONTIER_MAPPING.jsonl": FRONTIER_MAPPING_SCHEMA,
    "09_CANDIDATE_NEW_FRONTIERS.jsonl": CANDIDATE_NEW_FRONTIER_SCHEMA,
    "10_CONTRADICTIONS.jsonl": CONTRADICTION_SCHEMA,
    "11_NEGATIVE_EVIDENCE.jsonl": NEGATIVE_EVIDENCE_SCHEMA,
    "12_EVIDENCE_REGISTRY.jsonl": EVIDENCE_SCHEMA,
    "13_UNKNOWNS.jsonl": UNKNOWN_SCHEMA,
    "14_UNCLASSIFIED.jsonl": UNCLASSIFIED_SCHEMA,
}

DOCUMENT_SCHEMA_CONTRACTS: dict[str, dict[str, Any]] = {
    "00_EXECUTION_MANIFEST.json": MANIFEST_SCHEMA,
    "20_COVERAGE_REPORT.json": COVERAGE_SCHEMA,
}

SCHEMA_CONTRACTS: dict[str, dict[str, Any]] = {
    **DOCUMENT_SCHEMA_CONTRACTS,
    **JSONL_SCHEMA_CONTRACTS,
}


def schema_for(filename: str) -> dict[str, Any]:
    """Return an isolated copy of the contract for *filename*.

    Returning a copy prevents a validator implementation from accidentally
    mutating the process-wide contract and weakening later checks.
    """

    try:
        return deepcopy(SCHEMA_CONTRACTS[filename])
    except KeyError as error:
        known = ", ".join(sorted(SCHEMA_CONTRACTS))
        raise KeyError(f"no FR-000/FR-001 schema contract for {filename!r}; known: {known}") from error


__all__ = [
    "DOCUMENT_SCHEMA_CONTRACTS",
    "JSONL_SCHEMA_CONTRACTS",
    "SCHEMA_CONTRACTS",
    "schema_for",
]
