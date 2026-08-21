#!/usr/bin/env python3
"""Independent consistency checks for the FR-000/FR-001 audit artifacts."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from schema_contracts import DOCUMENT_SCHEMA_CONTRACTS, JSONL_SCHEMA_CONTRACTS


EXPECTED_TAG = "atlas-n-cr001-20260820"
EXPECTED_COMMIT = "df4fbe7a96c70507094c24c7bf553efd297cc80a"
EXPECTED_TREE = "b790640b12ebff8eb100939f9f7a92f02de0b502"
EXPECTED_TAG_OBJECT = "c5652f6317cc8ad71033edad876fe4da40d7a3ce"
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PHASE = OUT / "phase_records"
REQUIRED = [
    "00_EXECUTION_MANIFEST.json", "01_SOURCE_COVERAGE_REGISTRY.jsonl",
    "02_SOURCE_CLASSIFICATION_SUMMARY.md", "03_CURRENT_COMPONENT_MAP.jsonl",
    "04_AUTHORITY_MAP.jsonl", "05_CALLER_WRITER_ANOMALIES.jsonl",
    "06_SUPERSESSION_GRAPH.jsonl", "07_DECISION_REALITY_MAP.jsonl",
    "08_FRONTIER_MAPPING.jsonl", "09_CANDIDATE_NEW_FRONTIERS.jsonl",
    "10_CONTRADICTIONS.jsonl", "11_NEGATIVE_EVIDENCE.jsonl",
    "12_EVIDENCE_REGISTRY.jsonl", "13_UNKNOWNS.jsonl",
    "14_UNCLASSIFIED.jsonl", "15_DOCS_INDEX_AUDITOR_AUDIT.md",
    "16_EVIDENCE_RETENTION_GAPS.md", "17_FR000_REPORT.md", "18_FR001_REPORT.md",
    "19_HANDOFF_TO_RECONCILIATION.md", "20_COVERAGE_REPORT.json",
]
SUPPLEMENTAL = [
    "build_artifacts.py", "validate_artifacts.py", "schema_contracts.py",
    "phase_records/adversarial_self_review.jsonl",
    "phase_records/adversarial_self_review_summary.json",
    "phase_records/review_reconciliation.jsonl",
    "phase_records/candidate_new_frontier_fit_assessment.jsonl",
    "phase_records/claim_registry.jsonl",
    "phase_records/reality_snapshot_20260821.json",
    "phase_records/codeoss_external_state.json",
    "phase_records/cross_model_review.json",
    "schemas/audit_record.schema.json", "schemas/schema_catalog.json",
    "tasks/plan.md", "tasks/todo.md",
]
MATURITIES = {
    "MISSING", "RESEARCH_ONLY", "PROPOSED_DESIGN", "ACCEPTED_DESIGN", "CODE_PRESENT",
    "TESTED", "WIRED", "RUNTIME_CONFIGURED", "LIVE_VERIFIED", "PRODUCT_ACCEPTED",
    "SUPERSEDED", "CONTRADICTED", "UNKNOWN",
}
DECISION_STATUSES = {"ACTIVE", "PROVISIONAL", "SUPERSEDED", "REJECTED", "CONTRADICTED", "HISTORICAL", "UNKNOWN"}


def fail(message: str) -> None:
    raise AssertionError(message)


def command(*args: str, binary: bool = False) -> Any:
    return subprocess.check_output(args, cwd=ROOT, text=not binary)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(name: str | Path) -> list[dict[str, Any]]:
    path = name if isinstance(name, Path) else OUT / name
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                fail(f"{path.name}:{line_no}: not an object")
            rows.append(value)
    return rows


def git_tree() -> dict[str, tuple[str, str, int]]:
    raw = command("git", "ls-tree", "-r", "-l", "-z", EXPECTED_TAG + "^{tree}", binary=True)
    result: dict[str, tuple[str, str, int]] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path_b = item.split(b"\t", 1)
        mode, _kind, blob, size = meta.decode().split(None, 3)
        result[path_b.decode("utf-8", "surrogateescape")] = (blob, mode, int(size))
    return result


def substantive_init(path: Path) -> bool:
    body = list(ast.parse(path.read_text(encoding="utf-8")).body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return bool(body)


def expected_component_paths() -> set[str]:
    paths: set[Path] = {path for path in (ROOT / "src/atlas").rglob("*.py") if path.name != "__init__.py"}
    paths.update(path for path in (ROOT / "src/atlas").rglob("__init__.py") if substantive_init(path))
    paths.update((ROOT / "src/atlas").rglob("*.html"))
    paths.update(
        path for path in (ROOT / "scripts").rglob("*.py")
        if path.name != "__init__.py" and "archive" not in path.parts and "__pycache__" not in path.parts
    )
    paths.update(path for path in (ROOT / "scripts").rglob("*.sh") if "archive" not in path.parts)
    for base in (ROOT / ".githooks", ROOT / "scripts/hooks"):
        paths.update(path for path in base.rglob("*") if path.is_file() and not path.suffix)
    paths.update(path for path in (ROOT / "setup_atlas.sh", ROOT / "verify_prometheus.sh") if path.is_file())
    paths.update((ROOT / "mission_console/lib").rglob("*.dart"))
    paths.update((ROOT / "mission_console/linux/runner").glob("*.cc"))
    paths.update((ROOT / "mission_console/linux/runner").glob("*.h"))
    for base in (ROOT / "prototypes/atlas_ui/flutter_micropoc", ROOT / "prototypes/atlas_ui/mission_console"):
        paths.update((base / "lib").rglob("*.dart"))
        paths.update((base / "linux/runner").glob("*.cc"))
        paths.update((base / "linux/runner").glob("*.h"))
        paths.update(path for path in (base / "shaders").glob("*") if path.is_file())
    return {str(path.relative_to(ROOT)) for path in paths}


def validate_schemas() -> int:
    checked = 0
    contracts = {**JSONL_SCHEMA_CONTRACTS, **DOCUMENT_SCHEMA_CONTRACTS}
    for filename, schema in JSONL_SCHEMA_CONTRACTS.items():
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for line_no, row in enumerate(load_jsonl(filename), 1):
            errors = sorted(validator.iter_errors(row), key=lambda error: list(error.absolute_path))
            if errors:
                fail(f"{filename}:{line_no}:{errors[0].json_path}: {errors[0].message}")
            checked += 1
    for filename, schema in DOCUMENT_SCHEMA_CONTRACTS.items():
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(load_json(OUT / filename)), key=lambda error: list(error.absolute_path))
        if errors:
            fail(f"{filename}:{errors[0].json_path}: {errors[0].message}")
        checked += 1
    catalog = load_json(OUT / "schemas/schema_catalog.json")
    if set(catalog) != set(contracts):
        fail("persisted schema catalog does not cover all static contracts")
    for artifact, schema_name in catalog.items():
        if load_json(OUT / "schemas" / schema_name) != contracts[artifact]:
            fail(f"persisted schema drift: {artifact}")
    return checked


def main() -> None:
    if command("git", "rev-parse", EXPECTED_TAG).strip() != EXPECTED_TAG_OBJECT:
        fail("annotated tag object identity mismatch")
    if command("git", "rev-parse", EXPECTED_TAG + "^{commit}").strip() != EXPECTED_COMMIT:
        fail("sealed commit identity mismatch")
    if command("git", "rev-parse", EXPECTED_TAG + "^{tree}").strip() != EXPECTED_TREE:
        fail("sealed tree identity mismatch")
    for name in REQUIRED + SUPPLEMENTAL:
        if not (OUT / name).is_file():
            fail(f"missing audit artifact: {name}")

    schema_records = validate_schemas()
    manifest = load_json(OUT / "00_EXECUTION_MANIFEST.json")
    coverage = load_json(OUT / "20_COVERAGE_REPORT.json")
    if manifest["baseline"]["peeled_commit"] != EXPECTED_COMMIT or manifest["baseline"]["tree"] != EXPECTED_TREE:
        fail("manifest baseline mismatch")
    f26 = manifest["f26"]
    if (f26["execution_outcome"], f26["automatic_grade"], f26["measurement_validity"], f26["rerun_in_this_audit"]) != ("FAIL", "1/6", "INCONCLUSIVE", False):
        fail("F2.6 execution result/measurement validity separation changed")

    tree = git_tree()
    sources = load_jsonl("01_SOURCE_COVERAGE_REGISTRY.jsonl")
    if len(sources) != len(tree) or {row["path"] for row in sources} != set(tree):
        fail("source registry is not the exact sealed-tree census")
    if len({row["source_id"] for row in sources}) != len(sources):
        fail("duplicate source IDs")
    for row in sources:
        blob, mode, size = tree[row["path"]]
        if (row["git_blob_sha"], row["git_mode"], row["size_bytes"]) != (blob, mode, size):
            fail(f"Git metadata mismatch: {row['path']}")
        digest = hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
        if row["sha256"] != digest or row["content_hash"] != "sha256:" + digest:
            fail(f"content hash mismatch: {row['path']}")
    source_by_path = {row["path"]: row for row in sources}
    generated_flutter = {
        path for path in tree
        if Path(path).name in {".metadata", "pubspec.lock", "generated_plugins.cmake"}
        or Path(path).name.startswith("generated_plugin_registrant.")
    }
    if len(generated_flutter) != 15 or any(source_by_path[path]["category"] != "GENERATED" or source_by_path[path]["lifecycle"] != "GENERATED" or source_by_path[path]["conceptual_entity"] for path in generated_flutter):
        fail("Flutter generated-material exclusion failed")
    archived_scripts = [row for row in sources if row["path"].startswith("scripts/archive/")]
    if len(archived_scripts) != 16 or any(row["lifecycle"] != "ARCHIVED" for row in archived_scripts):
        fail("archived tooling lifecycle failed")

    components = load_jsonl("03_CURRENT_COMPONENT_MAP.jsonl")
    expected_paths = expected_component_paths()
    observed_paths = {row["source_paths"][0] for row in components if len(row["source_paths"]) == 1}
    if len(expected_paths) != 471 or len(components) != 471 or observed_paths != expected_paths:
        fail("component population is not the independently reconstructed 471-unit set")
    if len({row["component_id"] for row in components}) != 471:
        fail("duplicate component IDs")
    evidence = load_jsonl("12_EVIDENCE_REGISTRY.jsonl")
    evidence_ids = {row["evidence_id"] for row in evidence}
    if len(evidence_ids) != len(evidence):
        fail("duplicate evidence IDs")
    for row in components:
        if not row["current"] or row["maturity"] not in MATURITIES:
            fail(f"invalid current component: {row['name']}")
        if source_by_path[row["source_paths"][0]]["category"] in {"TEST", "GENERATED", "HISTORICAL"}:
            fail(f"non-implementation source inflated component census: {row['name']}")
        transitions = {transition["to"] for transition in row["maturity_transitions"]}
        transition_evidence = {eid for transition in row["maturity_transitions"] for eid in transition["evidence_ids"]}
        if "CODE_PRESENT" not in transitions or transition_evidence - evidence_ids:
            fail(f"unsupported component transition: {row['name']}")
        if row["maturity"] == "TESTED" and ("TESTED" not in transitions or not row["tested_property_locators"]):
            fail(f"unsupported TESTED promotion: {row['name']}")
        if row["maturity"] in {"WIRED", "RUNTIME_CONFIGURED", "LIVE_VERIFIED"} and row["maturity"] not in transitions:
            fail(f"unsupported higher maturity: {row['name']}")
        if row["maturity"] == "PRODUCT_ACCEPTED":
            fail("PRODUCT_ACCEPTED was inferred without explicit product evidence")
    by_name = {row["name"]: row for row in components}
    mission = by_name["atlas.knowledge.mission"]
    if mission["maturity"] != "WIRED" or "EV-MISSION-CALLER" not in {eid for step in mission["maturity_transitions"] for eid in step["evidence_ids"]}:
        fail("Mission interactive caller correction missing")
    browser = by_name["atlas.tools.browser"]
    if browser["maturity"] != "RUNTIME_CONFIGURED" or "TESTED" in {step["to"] for step in browser["maturity_transitions"]} or not any("test_browser.py" in path for path in browser["excluded_test_locators"]):
        fail("Browser computer_use exclusion/maturity boundary failed")
    wired_expectations = {
        "atlas.api.server": ("EV-WIRING-API-SERVER", "src/atlas/interfaces/cli.py:1804-1812"),
        "atlas.core.inference_hub": ("EV-WIRING-INFERENCE-HUB", "src/atlas/api/coding_server.py:94-98"),
        "atlas.core.orchestrator": ("EV-WIRING-ORCHESTRATOR", "src/atlas/interfaces/cli.py:32-38"),
        "atlas.mcp.catalog": ("EV-WIRING-MCP-CATALOG", "src/atlas/mcp/trunk_server.py:519-536"),
    }
    for module, (expected_evidence, expected_locator) in wired_expectations.items():
        row = by_name[module]
        wired_steps = [step for step in row["maturity_transitions"] if step["to"] == "WIRED"]
        if row["maturity"] != "WIRED" or len(wired_steps) != 1 or expected_evidence not in wired_steps[0]["evidence_ids"] or expected_locator not in wired_steps[0]["locator"]:
            fail(f"WIRED promotion lacks exact real-caller evidence: {module}")

    authority = load_jsonl("04_AUTHORITY_MAP.jsonl")
    if Counter(row["record_kind"] for row in authority) != {"COMPONENT_AUTHORITY": 20, "STATE_DOMAIN_AUTHORITY": 11}:
        fail("critical authority overlay population changed")
    component_authority = {row["component"]: row for row in authority if row["record_kind"] == "COMPONENT_AUTHORITY"}
    if not any("knowledge_trunk.py:131-150" in caller for caller in component_authority["Mission"]["callers"]):
        fail("Mission real caller absent from authority map")
    product_domain = next(row for row in authority if row.get("domain") == "Product events")
    if not product_domain["multiple_writers"] or len(product_domain["writers"]) < 5:
        fail("Product EventStore logical writers remain incomplete")

    anomalies = load_jsonl("05_CALLER_WRITER_ANOMALIES.jsonl")
    anomaly_by_id = {row["anomaly_id"]: row for row in anomalies}
    if len(anomalies) != 13 or len(anomaly_by_id) != 13:
        fail("anomaly population changed")
    if anomaly_by_id["A-008"]["status"] != "SUPERSEDED_BY_SELF_REVIEW" or anomaly_by_id["A-008-R"]["status"] != "OPEN":
        fail("self-review did not preserve/supersede the original Mission finding")

    relations = load_jsonl("06_SUPERSESSION_GRAPH.jsonl")
    canonical_relations = [row for row in relations if row["source"] == "docs/canon/supersession_registry.jsonl"]
    atomic_pairs = sum(len(row["from_ids"]) * len(row["to_ids"]) for row in canonical_relations)
    if len(relations) != 17 or len(canonical_relations) != 15 or atomic_pairs != 18 or any(row["chronology_inferred"] for row in relations):
        fail("explicit supersession/contradiction graph population changed")

    decisions = load_jsonl("07_DECISION_REALITY_MAP.jsonl")
    canonical_ids = {row["id"] for row in load_jsonl(ROOT / "docs/canon/decision_registry.jsonl")}
    work_orders = yaml.safe_load((ROOT / "docs/canon/implementation_registry.yaml").read_text(encoding="utf-8"))["work_orders"]
    work_ids = {row["id"] for row in work_orders}
    program_ids = {f"P{number:02d}" for number in range(13)}
    relation_endpoints = {did for row in relations for did in row["from_ids"] + row["to_ids"]}
    expected_decision_ids = canonical_ids | work_ids | program_ids | relation_endpoints
    if len(decisions) != len(expected_decision_ids) or {row["decision_id"] for row in decisions} != expected_decision_ids:
        fail("decision population is not registry + work orders + programs + relation endpoints")
    decision_by_id = {row["decision_id"]: row for row in decisions}
    current_records = [row for row in decisions if row["current"]]
    subject_groups: dict[str, list[dict[str, Any]]] = {}
    for row in decisions:
        subject_groups.setdefault(row["decision_subject_key"], []).append(row)
    if any(len({row["status"] for row in rows}) != 1 for rows in subject_groups.values()):
        fail("semantic decision subject has conflicting statuses")
    unique_decisions = [rows[0] for rows in subject_groups.values()]
    current = [rows[0] for rows in subject_groups.values() if any(row["current"] for row in rows)]
    partition = Counter(
        "ADC" if row["record_kind"] == "ADC_WORK_ORDER" else
        "PROGRAM" if row["record_kind"] == "PROGRAM_DECISION" else "CANON"
        for row in current_records
    )
    if len(current_records) != 134 or len(current) != 126 or len(unique_decisions) != 268 or partition != {"CANON": 85, "ADC": 36, "PROGRAM": 13}:
        fail(f"current decision authority denominator mismatch: {partition}")
    canon_current = [row for row in current_records if row["record_kind"] not in {"ADC_WORK_ORDER", "PROGRAM_DECISION"}]
    if Counter(row["status"] for row in canon_current) != {"ACTIVE": 73, "PROVISIONAL": 10, "REJECTED": 2}:
        fail("current canonical decision status partition changed")
    if any(row["status"] not in DECISION_STATUSES for row in decisions):
        fail("invalid decision status")
    required_status = {
        "ADC-WO-107": "CONTRADICTED", "ADC-WO-109": "CONTRADICTED", "ADC-WO-124": "CONTRADICTED",
        "ADR-057": "PROVISIONAL", "ADR-058": "PROVISIONAL", "ADR-069": "PROVISIONAL", "ADR-078": "PROVISIONAL",
        "OSM-042": "PROVISIONAL", "ATR-QUESTION-OPEN-6885DDD3AD62": "CONTRADICTED",
    }
    if any(decision_by_id[did]["status"] != status for did, status in required_status.items()):
        fail("focused decision classification changed")
    for did in ("ADC-WO-107", "ADR-057", "ADR-058", "ADR-069", "ADR-078"):
        row = decision_by_id[did]
        if len(row["status_evidence_ids"]) != 2 or set(row["status_evidence_ids"]) - evidence_ids or not row["evidence_for_status"] or not row["evidence_against_or_limiting"]:
            fail(f"focused both-way evidence missing: {did}")
    if sum(bool(row["semantic_duplicate_of"]) for row in decisions) != 8:
        fail("decision semantic companion deduplication changed")

    mapping = load_jsonl("08_FRONTIER_MAPPING.jsonl")
    mapping_kinds = Counter(row["record_kind"] for row in mapping)
    if mapping_kinds != {"FRONTIER_R0": 109, "SOURCE": len(sources), "COMPONENT": len(components), "DECISION": len(decisions)}:
        fail(f"cross-mapping population mismatch: {mapping_kinds}")
    program_counts = {0: 8, 1: 7, 2: 6, 3: 8, 4: 11, 5: 2, 6: 11, 7: 9, 8: 10, 9: 12, 10: 8, 11: 7, 12: 10}
    expected_frontiers = {f"FR-P{program:02d}-{number:03d}" for program, count in program_counts.items() for number in range(1, count + 1)}
    frontier_rows = [row for row in mapping if row["record_kind"] == "FRONTIER_R0"]
    if {row["frontier_id"] for row in frontier_rows} != expected_frontiers or any(not row["examined"] for row in frontier_rows):
        fail("R0 frontier set/examination mismatch")
    merge = [row for row in frontier_rows if row["assessment"] == "MERGE_CANDIDATE"]
    split = [row for row in frontier_rows if row["assessment"] == "SPLIT_CANDIDATE"]
    if {row["frontier_id"] for row in merge} != {"FR-P06-010", "FR-P10-005"} or {row["frontier_id"] for row in split} != {"FR-P00-007"}:
        fail("merge/split candidate identity changed")
    if any(row["confidence"] != "LOW" or row["assessment_basis"] != "PACK_INTERNAL_ONLY_REQUIRES_INDEPENDENT_RECONCILIATION" for row in merge + split):
        fail("pack-only merge/split candidates are overconfident")

    contradictions = load_jsonl("10_CONTRADICTIONS.jsonl")
    contradiction_by_id = {row["contradiction_id"]: row for row in contradictions}
    if len(contradictions) != 22 or len(contradiction_by_id) != 22 or "CUR-CON-ADC-WO-109" not in contradiction_by_id:
        fail("contradiction preservation mismatch")
    for row in contradictions:
        if set(row["evidence_ids"]) - evidence_ids or set(row["frontier_ids"]) - expected_frontiers:
            fail(f"dangling contradiction reference: {row['contradiction_id']}")

    fit = load_jsonl(PHASE / "candidate_new_frontier_fit_assessment.jsonl")
    fit_subjects = {row["subject_kind"] + ":" + row["subject_id"] for row in fit}
    expected_fit = {
        *("CALLER_WRITER_ANOMALY:" + row["anomaly_id"] for row in anomalies),
        *("CURRENT_CONTRADICTION:" + row["contradiction_id"] for row in contradictions if row["origin"] != "FRONTIER_PACK"),
    }
    if fit_subjects != expected_fit or any(not row["existing_frontier_ids"] for row in fit):
        fail("candidate-new-frontier fit assessment is incomplete")
    candidates = load_jsonl("09_CANDIDATE_NEW_FRONTIERS.jsonl")
    derived_candidates = [row for row in fit if row["fit_result"] == "CANDIDATE_NEW_FRONTIER"]
    if len(candidates) != len(derived_candidates):
        fail("candidate-new-frontier output is not derived from fit assessment")

    claims = load_jsonl(PHASE / "claim_registry.jsonl")
    claim_ids = {row["claim_id"] for row in claims}
    evidence_claim_refs = {claim for row in evidence for claim in row["supports"] + row["contradicts"]}
    negative = load_jsonl("11_NEGATIVE_EVIDENCE.jsonl")
    if (evidence_claim_refs | {row["claim_examined"] for row in negative}) - claim_ids:
        fail("claim registry has dangling references")
    for row in evidence:
        if set(row["derived_from_evidence_ids"]) - evidence_ids:
            fail(f"dangling derived evidence: {row['evidence_id']}")
    ev = {row["evidence_id"]: row for row in evidence}
    if ev["EV-PACK-ZIP"]["independence_key"] != ev["EV-PACK-VALIDATION"]["independence_key"]:
        fail("pack validator improperly inflates evidence independence")
    if ev["EV-SEALED-TREE"]["independence_key"] != ev["EV-SOURCE-CENSUS"]["independence_key"]:
        fail("tree census improperly inflates evidence independence")
    for missing_id in ("EV-SEMGREP-CR001-RAW-ABSENT", "EV-F26-CR001-RAW-ABSENT"):
        if ev[missing_id]["raw_preserved"] or ev[missing_id]["source_hash"] is not None:
            fail(f"missing raw evidence silently promoted: {missing_id}")

    unknowns = load_jsonl("13_UNKNOWNS.jsonl")
    if len(unknowns) != 24 or len({row["unknown_id"] for row in unknowns}) != 24:
        fail("explicit semantic unknown registry changed")
    for row in unknowns:
        if set(row["evidence_ids"]) - evidence_ids:
            fail(f"dangling unknown evidence: {row['unknown_id']}")
    if load_jsonl("14_UNCLASSIFIED.jsonl"):
        fail("unclassified-current registry is not empty")

    current_sources = [row for row in sources if row["lifecycle"] == "CURRENT"]
    unknown_dimensions = {
        "semantic_unknown_registry": len(unknowns),
        "source_lifecycle_unknown": sum(row["lifecycle"] == "UNKNOWN" for row in sources),
        "source_program_unknown": sum(row["program"] == "UNKNOWN" for row in sources),
        "source_frontier_mapping_unknown": sum(row.get("mapping_status") == "UNKNOWN" for row in mapping if row["record_kind"] == "SOURCE"),
        "component_maturity_unknown": sum(row["maturity"] == "UNKNOWN" for row in components),
        "component_program_unknown": sum(row["program"] == "UNKNOWN" for row in components),
        "component_frontier_mapping_unknown": sum(row.get("mapping_status") == "UNKNOWN" for row in mapping if row["record_kind"] == "COMPONENT"),
        "decision_status_unknown": sum(row["status"] == "UNKNOWN" for row in decisions),
        "decision_program_unknown": sum(row["program"] == "UNKNOWN" for row in decisions),
        "decision_frontier_mapping_unknown": sum(row.get("mapping_status") == "UNKNOWN" for row in mapping if row["record_kind"] == "DECISION"),
        "frontier_assessment_unknown": sum(row["assessment"] == "UNKNOWN" for row in frontier_rows),
    }
    if coverage["unknown_classifications_by_dimension"] != unknown_dimensions or coverage["unknown_classifications_total"] != sum(unknown_dimensions.values()):
        fail("UNKNOWN dimension coverage mismatch")
    expected_coverage = {
        "all_tracked_sources_total": len(sources), "current_sources_total": len(current_sources),
        "current_components_total": len(components), "all_decisions_total": len(unique_decisions),
        "current_decisions_total": len(current), "frontier_r0_total": len(frontier_rows),
        "candidate_new_frontiers": len(candidates), "contradictions": len(contradictions),
        "unknowns": len(unknowns), "unclassified_current": 0,
    }
    for key, value in expected_coverage.items():
        if coverage[key] != value:
            fail(f"coverage mismatch {key}: {coverage[key]} != {value}")
    for key in ("CURRENT_SOURCE_COVERAGE", "CURRENT_COMPONENT_COVERAGE", "CURRENT_DECISION_COVERAGE", "CURRENT_FRONTIER_MAPPING_COVERAGE", "CRITICAL_CAPABILITY_AUTHORITY_COVERAGE"):
        if coverage[key]["ratio"] != 1.0:
            fail(f"classification/examination coverage not total: {key}")
    if coverage["current_decision_denominator_partition"] != {"canonical_current_authority": 77, "adc_work_orders": 36, "program_decisions": 13, "graph_endpoints_excluded": 5, "semantic_duplicate_records_excluded": 8}:
        fail("current decision denominator partition changed")
    if coverage["current_decision_record_partition"] != {"canonical_current_authority_records": 85, "adc_work_order_records": 36, "program_decision_records": 13}:
        fail("current decision record partition changed")
    if coverage["current_decision_records_total"] != 134 or coverage["current_decision_semantic_duplicates"] != 8:
        fail("current decision record/subject deduplication changed")
    if not coverage["ready_for_external_adversarial_review"] or len(coverage["stop_conditions"]) < 10 or not all(coverage["stop_conditions"].values()):
        fail("readiness is not supported by all explicit stop conditions")

    self_review = load_jsonl(PHASE / "adversarial_self_review.jsonl")
    reconciliation = load_jsonl(PHASE / "review_reconciliation.jsonl")
    if len(self_review) != 16 or not any(row["status"] == "SUPERSEDED_BY_SELF_REVIEW" for row in self_review) or len(reconciliation) != 6:
        fail("adversarial self-review/reconciliation record incomplete")
    if "- [ ]" in (OUT / "tasks/todo.md").read_text(encoding="utf-8"):
        fail("audit task list still contains unchecked work")

    changed = command("git", "diff", "--name-only").splitlines()
    staged = command("git", "diff", "--cached", "--name-only").splitlines()
    status = command("git", "status", "--porcelain=v1").splitlines()
    allowed_prefix = "work/frontier_reconciliation/fr000_fr001/"
    if any(not path.startswith(allowed_prefix) for path in changed + staged):
        fail(f"tracked/staged changes outside audit scope: changed={changed}, staged={staged}")
    for line in status:
        path = line[3:].split(" -> ")[-1]
        if not path.startswith(allowed_prefix) and path != "work/frontier_reconciliation/":
            fail(f"unrelated worktree state: {line}")
    subprocess.check_call(["git", "diff", "--check"], cwd=ROOT)
    subprocess.check_call(["git", "diff", "--cached", "--check"], cwd=ROOT)

    result = {
        "status": "PASS",
        "validated_at": "2026-08-21",
        "checks": {
            "sealed_tag_commit_tree": True,
            "required_and_supplemental_files": len(REQUIRED) + len(SUPPLEMENTAL),
            "schema_validated_records": schema_records,
            "tracked_source_paths_and_hashes": len(sources),
            "implementation_units": len(components),
            "critical_authority_rows": len(authority),
            "anomaly_rows": len(anomalies),
            "decision_rows": len(decisions),
            "current_decision_authority_records": len(current_records),
            "current_decision_independent_subjects": len(current),
            "relation_records": len(relations),
            "canonical_relation_atomic_pairs": atomic_pairs,
            "frontier_rows": len(frontier_rows),
            "artifact_mapping_rows": len(mapping) - len(frontier_rows),
            "candidate_fit_assessments": len(fit),
            "evidence_rows": len(evidence),
            "claim_rows": len(claims),
            "contradiction_rows": len(contradictions),
            "negative_evidence_rows": len(negative),
            "semantic_unknown_rows": len(unknowns),
            "explicit_unknown_dimensions": sum(unknown_dimensions.values()),
            "unclassified_current": 0,
            "self_review_rows": len(self_review),
            "git_scope": True,
            "git_diff_check": True,
        },
    }
    (PHASE / "validation_results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
