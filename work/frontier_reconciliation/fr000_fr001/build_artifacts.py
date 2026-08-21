#!/usr/bin/env python3
"""Build the FR-000/FR-001 audit artifacts from the sealed Atlas N tree.

This program is audit tooling only.  It reads the checked-out Git tree, the
bounded phase records produced during this audit, and the external R0 pack.
It never edits Atlas functional source, tests, canonical records, or history.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


EXPECTED_TAG = "atlas-n-cr001-20260820"
EXPECTED_COMMIT = "df4fbe7a96c70507094c24c7bf553efd297cc80a"
EXPECTED_TREE = "b790640b12ebff8eb100939f9f7a92f02de0b502"
EXPECTED_VERSION = "Atlas 0.12.0"
PACK_SHA256 = "e7aacd2b0dfaaaa0281eb2e27f01c0368d4e13198f57acf7fcc7bf6370329011"

CATEGORIES = {
    "CODE", "TEST", "ADR", "CANON", "SPEC", "PLAN", "DESIGN",
    "RESEARCH", "BENCHMARK", "FIXTURE", "RUNTIME_CONFIG", "CI",
    "PRODUCT", "PROTOTYPE", "GENERATED", "HISTORICAL", "TOOLING",
    "SCHEMA", "EVIDENCE", "OTHER",
}
LIFECYCLES = {
    "CURRENT", "HISTORICAL", "ARCHIVED", "SUPERSEDED", "GENERATED", "UNKNOWN",
}
MATURITIES = {
    "MISSING", "RESEARCH_ONLY", "PROPOSED_DESIGN", "ACCEPTED_DESIGN",
    "CODE_PRESENT", "TESTED", "WIRED", "RUNTIME_CONFIGURED",
    "LIVE_VERIFIED", "PRODUCT_ACCEPTED", "SUPERSEDED", "CONTRADICTED", "UNKNOWN",
}
DECISION_STATUSES = {
    "ACTIVE", "PROVISIONAL", "SUPERSEDED", "REJECTED", "CONTRADICTED",
    "HISTORICAL", "UNKNOWN",
}
FRONTIER_ASSESSMENTS = {
    "CONFIRMED", "REFORMULATE", "MERGE_CANDIDATE", "SPLIT_CANDIDATE",
    "DELETE_CANDIDATE", "SUPERSEDED", "HISTORICAL", "NEW_EVIDENCE", "UNKNOWN",
}
ARTIFACT_MAPPING_STATUSES = {
    "MAPPED", "DUPLICATE", "SUPERSEDED", "HISTORICAL", "IRRELEVANT",
    "NEW_FRONTIER", "UNKNOWN",
}


def find_repo(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root not found")


OUT = Path(__file__).resolve().parent
ROOT = find_repo(OUT)
PHASE = OUT / "phase_records"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:16].upper()}"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_text_if_possible(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def docs_index_lifecycle() -> dict[str, str]:
    data = yaml.safe_load((ROOT / "docs/INDEX.yaml").read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    mapping = {
        "vigente": "CURRENT",
        "propuesto": "CURRENT",
        "historico": "HISTORICAL",
        "superseded": "SUPERSEDED",
    }
    for entry in data.get("entries", []):
        result[str(entry["path"])] = mapping.get(str(entry.get("status", "")).lower(), "UNKNOWN")
    return result


def classify_category(path: str) -> str:
    lower = path.lower()
    name = Path(path).name.lower()
    if (
        "/generated/" in lower
        or "/__pycache__/" in f"/{lower}/"
        or name.endswith(".pyc")
        or name == ".metadata"
        or name.startswith("generated_plugin_registrant.")
        or name in {
            "generated_plugins.cmake", "package-lock.json", "poetry.lock",
            "pubspec.lock", "uv.lock", "ui_quality_gate_results.json",
        }
    ):
        return "GENERATED"
    if path.startswith("fixtures/") or "/fixtures/" in f"/{lower}/":
        return "FIXTURE"
    if (
        path.startswith("tests/")
        or path.startswith("mission_console/test/")
        or (path.startswith("prototypes/") and "/test/" in f"/{lower}/")
    ):
        return "TEST"
    if path.startswith("src/"):
        return "CODE"
    if path.startswith("schemas/") or path.startswith("docs/canon/schemas/"):
        return "SCHEMA"
    if path.startswith("docs/decisions/") or "/decisions/adr/" in lower:
        return "ADR"
    if path.startswith("docs/canon/"):
        return "CANON"
    if path.startswith("docs/archive/") or path.startswith("docs/handoff/"):
        return "HISTORICAL"
    if "/spec" in lower or path.startswith("docs/superpowers/specs/"):
        return "SPEC"
    if "/plan" in lower or name in {"work_ledger.md", "programs.md"} or "backlog" in name:
        return "PLAN"
    if path.startswith("docs/design/") or path.startswith("docs/architecture/"):
        return "DESIGN"
    if path.startswith("docs/knowledge/") or "research" in lower:
        return "RESEARCH"
    if "benchmark" in lower or "fitness" in lower:
        return "BENCHMARK"
    if path.startswith("docs/audits/") or path.startswith("work/"):
        return "EVIDENCE"
    if path.startswith("scripts/") or path.startswith(".githooks/"):
        return "TOOLING"
    if path.startswith(".github/"):
        return "CI"
    if path.startswith("config/") or "systemd" in lower or name.endswith((".service", ".timer")):
        return "RUNTIME_CONFIG"
    if path.startswith("mission_console/"):
        return "PRODUCT"
    if path.startswith(("prototypes/", "workspace/", "atlas-experiments/")):
        return "PROTOTYPE"
    if path.startswith("docs/"):
        return "OTHER"
    if name in {"pyproject.toml", "dockerfile", "docker-compose.yml", "docker-compose.yaml", "makefile"}:
        return "TOOLING"
    return "OTHER"


def classify_lifecycle(path: str, category: str, indexed: dict[str, str]) -> tuple[str, str]:
    lower = path.lower()
    name = Path(path).name.lower()
    if path.startswith("docs/archive/"):
        return "ARCHIVED", "archive namespace"
    if path.startswith("scripts/archive/"):
        return "ARCHIVED", "archived tooling namespace"
    if path.startswith("docs/handoff/GENERATED/"):
        return "GENERATED", "generated handoff namespace"
    if path.startswith("docs/handoff/"):
        return "HISTORICAL", "handoff snapshot namespace"
    if path.startswith("work/checkpoints/") or path.startswith("work/canon-compiler/"):
        return "HISTORICAL", "preserved work/checkpoint evidence"
    if path.startswith("work/"):
        return "HISTORICAL", "tracked work evidence predates this audit"
    if path in indexed:
        return indexed[path], "docs/INDEX.yaml stated lifecycle"
    if category == "GENERATED" or "/generated/" in lower or name.endswith(".lock") or name == "package-lock.json":
        return "GENERATED", "generated or dependency-lock material"
    return "CURRENT", "present in sealed tree with no archival/supersession marker"


def apparent_owner(path: str) -> str:
    parts = Path(path).parts
    if path.startswith("src/atlas/") and len(parts) > 2:
        return "atlas." + parts[2]
    if path.startswith("tests/"):
        return "atlas test suite"
    if path.startswith("docs/canon/"):
        return "canon maintainers / operator authority"
    if path.startswith("docs/decisions/"):
        return "decision authors / operator authority"
    if path.startswith("docs/"):
        return "documentation maintainers"
    if path.startswith("scripts/"):
        return "repository automation maintainers"
    if path.startswith("mission_console/"):
        return "Mission Console product maintainers"
    if path.startswith("prototypes/"):
        return "prototype owners"
    if path.startswith("work/"):
        return "evidence producer / historical operator"
    return "repository maintainers"


def infer_program(path: str) -> str:
    lower = path.lower()
    rules = [
        (("docs/canon/", "docs/decisions/", "work/canon-compiler"), "P00"),
        (("governance", "authorization", "permission", "constitution"), "P01"),
        (("project_graph", "graphify", "context", "retrieval"), "P02"),
        (("inference", "orchestrator", "planner", "deliberation", "provider"), "P03"),
        (("memory", "lesson", "user_twin", "preference"), "P04"),
        (("knowledge", "world_model"), "P05"),
        (("self_", "cold_update", "golden_route", "fitness", "evolution"), "P06"),
        (("/mcp/", "connector", "fabric", "a2a", "acp", "ag_ui"), "P07"),
        (("/api/", "mission_console", "product", "workbench", "interface"), "P08"),
        (("security", "sandbox", "merkle", "audit", "recovery", "reality"), "P09"),
        (("hermes", "federation", "maintainer"), "P10"),
        (("runtime", "service", "deployment", "thermal", "hardware"), "P11"),
        (("membrana", "osmosis", "privacy", "consent", "schema", "cost"), "P12"),
    ]
    for needles, program in rules:
        if any(needle in lower for needle in needles):
            return program
    return "UNKNOWN"


def relevance(path: str, category: str) -> tuple[str, str, str]:
    authority = "HIGH" if category in {"ADR", "CANON", "RUNTIME_CONFIG"} or path in {"AGENTS.md", "WORK_LEDGER.md", "PROGRAMS.md"} else "LOW"
    runtime = "HIGH" if category in {"CODE", "RUNTIME_CONFIG", "PRODUCT"} else ("MEDIUM" if category in {"TEST", "FIXTURE", "TOOLING"} else "LOW")
    evidence = "HIGH" if category in {"TEST", "EVIDENCE", "BENCHMARK"} else ("MEDIUM" if category in {"CODE", "ADR", "CANON"} else "LOW")
    return authority, runtime, evidence


def generated_from(path: str) -> list[str]:
    if path.startswith("docs/handoff/GENERATED/"):
        return ["atlas handoff generation pipeline; exact input set not encoded in file path"]
    if Path(path).name == "package-lock.json":
        return [str(Path(path).with_name("package.json"))]
    if Path(path).name == "pubspec.lock":
        return [str(Path(path).with_name("pubspec.yaml"))]
    if Path(path).name.startswith("generated_plugin_registrant.") or Path(path).name == "generated_plugins.cmake":
        return ["Flutter platform scaffolding generator"]
    if Path(path).name == "ui_quality_gate_results.json":
        return ["prototype UI quality-gate execution"]
    if "/graphify-out/" in path or "/graphify-vault/" in path:
        return ["Graphify structural/semantic pipeline"]
    return []


KNOWN_SUPERSESSION = {
    "docs/decisions/adr/adr_032_tool_execution_and_approval.md": ["ADR-040 (partial scope only)"],
    "docs/decisions/adr/adr_033_hitl_approval.md": ["ADR-040 (partial scope only)"],
    "docs/decisions/adr/adr_059_atlas_os_ui_web_first.md": ["ADR-071 (final product UX scope only)"],
    "docs/decisions/adr/adr_066_visual_orchestrator_territories.md": ["ADR-068 (self-construction framing only)"],
}


def git_tree_rows() -> list[dict[str, Any]]:
    raw = subprocess.check_output(["git", "ls-tree", "-r", "-l", "-z", EXPECTED_TAG + "^{tree}"], cwd=ROOT)
    indexed = docs_index_lifecycle()
    preliminary: list[dict[str, Any]] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, path_b = entry.split(b"\t", 1)
        mode, obj_type, blob, size_b = meta.decode().split(None, 3)
        path = path_b.decode("utf-8", "surrogateescape")
        payload = (ROOT / path).read_bytes()
        content_hash = sha256_bytes(payload)
        category = classify_category(path)
        lifecycle, lifecycle_basis = classify_lifecycle(path, category, indexed)
        text = read_text_if_possible(ROOT / path)
        frontier_ids = sorted(set(re.findall(r"FR-P(?:0[0-9]|1[0-2])-\d{3}", text)))
        authority, runtime, evidence = relevance(path, category)
        third_party = (
            "/node_modules/" in f"/{path}/" or "/vendor/" in f"/{path}/"
            or path.endswith("gradle-wrapper.jar")
        )
        generated_inputs = generated_from(path)
        conceptual = (
            category not in {"FIXTURE", "GENERATED"}
            and lifecycle != "GENERATED"
            and not generated_inputs
            and not third_party
        )
        family = (
            "docs-fixtures" if path.startswith("docs/fixtures/") else
            "graveyard-ui" if path.startswith("docs/archive/_graveyard/") else
            "historical-handoff" if path.startswith("docs/handoff/") else
            "test-fixtures" if path.startswith("fixtures/") else
            "project-source"
        )
        preliminary.append({
            "source_id": stable_id("SRC", path),
            "path": path,
            "sha256": content_hash,
            "content_hash": f"sha256:{content_hash}",
            "git_blob_sha": blob,
            "git_mode": mode,
            "size_bytes": int(size_b) if size_b != "-" else len(payload),
            "category": category,
            "lifecycle": lifecycle,
            "lifecycle_basis": lifecycle_basis,
            "apparent_owner": apparent_owner(path),
            "program": infer_program(path),
            "related_frontier_ids": frontier_ids,
            "authority_relevance": authority,
            "runtime_relevance": runtime,
            "evidence_relevance": evidence,
            "generated_from": generated_inputs,
            "superseded_by": KNOWN_SUPERSESSION.get(path, []),
            "confidence": "HIGH" if path in indexed or category in {"CODE", "TEST", "ADR", "CANON", "SCHEMA", "FIXTURE"} else "MEDIUM",
            "tracked_atlas_n": True,
            "project_owned": not third_party,
            "third_party_or_vendor": third_party,
            "conceptual_entity": conceptual,
            "source_family_id": family,
            "independence_key": f"sha256:{content_hash}",
            "semantic_normalization_hash": (
                "sha256:" + sha256_bytes(re.sub(r"\s+", " ", text.lower()).strip().encode())
                if text else None
            ),
        })
    by_hash = Counter(r["sha256"] for r in preliminary)
    by_semantic = Counter(r["semantic_normalization_hash"] for r in preliminary if r["semantic_normalization_hash"])
    first_hash: dict[str, str] = {}
    for row in preliminary:
        first_hash.setdefault(row["sha256"], row["path"])
        row["content_duplicate_count"] = by_hash[row["sha256"]]
        row["canonical_content_copy"] = first_hash[row["sha256"]]
        row["semantic_duplicate_count"] = by_semantic.get(row["semantic_normalization_hash"], 0)
    return preliminary


def module_name(path: str) -> str:
    dotted = path[:-3].replace("/", ".")
    dotted = dotted[4:] if dotted.startswith("src.") else dotted
    return dotted.removesuffix(".__init__")


def module_contracts(path: Path) -> tuple[str, list[str], bool]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "AST parse failed; purpose unknown.", [], False
    doc = ast.get_docstring(tree) or ""
    purpose = re.split(r"(?<=[.!?])\s+", doc.strip(), maxsplit=1)[0] if doc.strip() else "No module docstring; purpose remains UNKNOWN beyond source location."
    contracts = [
        node.name for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    return purpose, contracts, bool(doc.strip())


CRITICAL_FRONTIERS: dict[str, list[str]] = {
    "Mission": ["FR-P01-005"],
    "Task": ["FR-P01-005"],
    "Orchestrator": ["FR-P03-005", "FR-P03-006"],
    "InferenceHub": ["FR-P03-001", "FR-P03-002", "FR-P03-004"],
    "Memory": ["FR-P04-001", "FR-P04-002", "FR-P04-011"],
    "Knowledge": ["FR-P05-001"],
    "Project Graph": ["FR-P02-001", "FR-P02-004"],
    "Reality": ["FR-P00-006", "FR-P09-011"],
    "Evidence and Merkle audit": ["FR-P09-005", "FR-P09-006"],
    "Governance and Constitution": ["FR-P01-003", "FR-P01-006", "FR-P12-006"],
    "ColdUpdate": ["FR-P06-001", "FR-P06-002"],
    "Self-Build": ["FR-P06-001", "FR-P06-004", "FR-P06-005"],
    "Foundry/Fabric": ["FR-P07-006", "FR-P08-008"],
    "MCP": ["FR-P07-001", "FR-P07-008", "FR-P07-009"],
    "Security": ["FR-P09-002", "FR-P09-003", "FR-P09-004", "FR-P09-012"],
    "Sandbox": ["FR-P09-001"],
    "Product/API bridge": ["FR-P08-001", "FR-P01-003"],
    "Hermes/federation": ["FR-P10-001", "FR-P10-006"],
    "Budget": ["FR-P03-003", "FR-P12-007", "FR-P12-008"],
    "Secrets": ["FR-P07-007", "FR-P12-002"],
}

CRITICAL_PRIMARY_MODULE = {
    "atlas.knowledge.mission": "Mission",
    "atlas.core.contracts": "Task",
    "atlas.core.orchestrator": "Orchestrator",
    "atlas.core.inference_hub": "InferenceHub",
    "atlas.memory.memory_system": "Memory",
    "atlas.knowledge.base": "Knowledge",
    "atlas.memory.project_graph": "Project Graph",
    "atlas.core.reality": "Reality",
    "atlas.core.verify": "Evidence and Merkle audit",
    "atlas.logging.merkle_logger": "Evidence and Merkle audit",
    "atlas.governance.governance_l0": "Governance and Constitution",
    "atlas.core.cold_update_manager": "ColdUpdate",
    "atlas.core.self_maintenance.self_build_runner": "Self-Build",
    "atlas.fabric.registry": "Foundry/Fabric",
    "atlas.mcp.catalog": "MCP",
    "atlas.mcp.trunk_server": "MCP",
    "atlas.security.authorization": "Security",
    "atlas.security.sandbox": "Sandbox",
    "atlas.api.server": "Product/API bridge",
    "atlas.hermes.hermes": "Hermes/federation",
    "atlas.core.token_budget": "Budget",
    "atlas.fabric.auth_broker": "Secrets",
}

LIVE_OVERRIDES = {
    "atlas.knowledge.mission": "WIRED",
    "atlas.memory.project_graph": "LIVE_VERIFIED",
    "atlas.core.reality": "LIVE_VERIFIED",
    "atlas.security.sandbox": "RUNTIME_CONFIGURED",
    "atlas.tools.browser": "RUNTIME_CONFIGURED",
    "atlas.mcp.trunk_server": "LIVE_VERIFIED",
    "atlas.api.server": "WIRED",
    "atlas.core.orchestrator": "WIRED",
    "atlas.core.inference_hub": "WIRED",
    "atlas.mcp.catalog": "WIRED",
}


HIGHER_MATURITY_EVIDENCE: dict[str, tuple[str, Any]] = {
    "atlas.knowledge.mission": (
        "EV-MISSION-CALLER",
        [
            "src/atlas/mcp/knowledge_trunk.py:131-150",
            "src/atlas/knowledge/run.py:17-38",
            "src/atlas/knowledge/mission.py:40-52",
        ],
    ),
    "atlas.memory.project_graph": (
        "EV-GRAPH-QUERIES",
        "phase_records/graph_first_queries.json: successful live trunk graph rebuild/read queries at the sealed commit",
    ),
    "atlas.mcp.trunk_server": (
        "EV-GRAPH-QUERIES",
        "phase_records/graph_first_queries.json: actual trunk_invoke_readonly calls completed through the running MCP trunk",
    ),
    "atlas.core.reality": (
        "EV-REALITY-CURRENT",
        "phase_records/reality_snapshot_20260821.json: atlas reality --json completed in the isolated audit worktree",
    ),
    "atlas.security.sandbox": (
        "EV-REALITY-CURRENT",
        "phase_records/reality_snapshot_20260821.json: bubblewrap was present; this is configuration, not an executed jail proof",
    ),
    "atlas.tools.browser": (
        "EV-REALITY-CURRENT",
        "phase_records/reality_snapshot_20260821.json: browser status ready; computer_use test lane remained unknown/deselected",
    ),
    "atlas.api.server": (
        "EV-WIRING-API-SERVER",
        ["src/atlas/interfaces/cli.py:1804-1812", "src/atlas/api/server.py:1255-1275"],
    ),
    "atlas.core.inference_hub": (
        "EV-WIRING-INFERENCE-HUB",
        ["src/atlas/api/coding_server.py:94-98", "src/atlas/api/coding_server.py:196-206"],
    ),
    "atlas.core.orchestrator": (
        "EV-WIRING-ORCHESTRATOR",
        ["src/atlas/interfaces/cli.py:32-38", "src/atlas/interfaces/dashboard.py:136-144"],
    ),
    "atlas.mcp.catalog": (
        "EV-WIRING-MCP-CATALOG",
        ["src/atlas/mcp/trunk_server.py:519-536"],
    ),
}


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def source_surface_contracts(paths: list[str]) -> list[str]:
    contracts: set[str] = set()
    for rel in paths:
        text = read_text_if_possible(ROOT / rel)
        suffix = Path(rel).suffix
        if suffix == ".dart":
            contracts.update(re.findall(r"(?m)^\s*(?:class|enum|mixin|extension|typedef)\s+([A-Za-z_]\w*)", text))
            contracts.update(re.findall(r"(?m)^\s*(?:Future<[^>]+>|Future|void|Widget|String|int|bool)\s+([a-zA-Z_]\w*)\s*\(", text))
        elif suffix in {".cc", ".cpp", ".c", ".h", ".hpp"}:
            contracts.update(re.findall(r"(?m)^\s*(?:class|struct)\s+([A-Za-z_]\w*)", text))
            contracts.update(re.findall(r"(?m)^\s*[A-Za-z_:<>~*& ]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:\{|;)", text))
    return sorted(contracts)


def substantive_package_init(path: Path) -> bool:
    """Return whether a package initializer contributes executable structure."""
    try:
        body = list(ast.parse(path.read_text(encoding="utf-8")).body)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return bool(body)


def extra_implementation_units() -> list[tuple[str, str, str, list[str]]]:
    """Return current non-ordinary-Python implementation units.

    The census counts independently locatable code-bearing files, not semantic
    capabilities. Tests, generated Flutter files, vendor payloads and archived
    tooling are deliberately excluded.
    """
    units: list[tuple[str, str, str, list[str]]] = []

    for path in sorted((ROOT / "src/atlas").rglob("__init__.py")):
        if substantive_package_init(path):
            rel = str(path.relative_to(ROOT))
            units.append((rel, "PYTHON_PACKAGE_MODULE", "Executable Python package initializer.", []))

    for path in sorted((ROOT / "src/atlas").rglob("*.html")):
        rel = str(path.relative_to(ROOT))
        units.append((rel, "JINJA_TEMPLATE", "Current dashboard Jinja template.", []))

    tooling: set[Path] = set()
    tooling.update(
        path for path in (ROOT / "scripts").rglob("*.py")
        if path.name != "__init__.py" and "archive" not in path.parts and "__pycache__" not in path.parts
    )
    tooling.update(path for path in (ROOT / "scripts").rglob("*.sh") if "archive" not in path.parts)
    for base in (ROOT / ".githooks", ROOT / "scripts/hooks"):
        if base.exists():
            tooling.update(path for path in base.rglob("*") if path.is_file() and not path.suffix)
    tooling.update(path for path in (ROOT / "setup_atlas.sh", ROOT / "verify_prometheus.sh") if path.is_file())
    for path in sorted(tooling):
        rel = str(path.relative_to(ROOT))
        units.append((rel, "TOOLING_PROGRAM", "Current repository automation program or Git hook.", []))

    mission_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "mission_console/test").rglob("*.dart"))
    mission_paths = sorted((ROOT / "mission_console/lib").rglob("*.dart"))
    mission_paths += sorted((ROOT / "mission_console/linux/runner").glob("*.cc"))
    mission_paths += sorted((ROOT / "mission_console/linux/runner").glob("*.h"))
    for path in mission_paths:
        rel = str(path.relative_to(ROOT))
        units.append((rel, "PRODUCT_IMPLEMENTATION_UNIT", "Current Mission Console product implementation unit.", mission_tests))

    for base in (ROOT / "prototypes/atlas_ui/flutter_micropoc", ROOT / "prototypes/atlas_ui/mission_console"):
        prototype_tests = sorted(str(path.relative_to(ROOT)) for path in (base / "test").rglob("*.dart"))
        prototype_paths = sorted((base / "lib").rglob("*.dart"))
        prototype_paths += sorted((base / "linux/runner").glob("*.cc"))
        prototype_paths += sorted((base / "linux/runner").glob("*.h"))
        prototype_paths += sorted(path for path in (base / "shaders").glob("*") if path.is_file())
        for path in prototype_paths:
            rel = str(path.relative_to(ROOT))
            units.append((rel, "PROTOTYPE_IMPLEMENTATION_UNIT", "Current preserved UI prototype implementation unit.", prototype_tests))

    return units


def build_components(source_rows: list[dict[str, Any]], component_findings: dict[str, Any], test_result: dict[str, Any]) -> list[dict[str, Any]]:
    source_by_path = {r["path"]: r for r in source_rows}
    tests: list[tuple[str, str]] = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        tests.append((str(path.relative_to(ROOT)), path.read_text(encoding="utf-8", errors="replace")))
    suite_passed = test_result.get("status") == "PASS"
    critical_detail = {r["component"]: r for r in component_findings["component_inventory"]}
    rows: list[dict[str, Any]] = []
    paths = sorted(p for p in (ROOT / "src/atlas").rglob("*.py") if p.name != "__init__.py")
    for file_path in paths:
        rel = str(file_path.relative_to(ROOT))
        module = module_name(rel)
        purpose, contracts, has_doc = module_contracts(file_path)
        import_needles = (f"from {module} import", f"import {module}")
        direct_tests = [name for name, text in tests if any(needle in text for needle in import_needles)]
        capability = CRITICAL_PRIMARY_MODULE.get(module)
        module_token = file_path.stem.lower()
        relevant_tests = [
            name for name in direct_tests
            if module_token in Path(name).stem.lower().removeprefix("test_")
        ]
        if capability and capability in critical_detail:
            manually_selected = {
                name for name in critical_detail[capability]["maturity"].get("test_present", [])
                if (ROOT / name).is_file()
            }
            relevant_tests = sorted(set(relevant_tests) | (set(direct_tests) & manually_selected))
        excluded_tests = sorted(
            name for name in relevant_tests
            if "pytest.mark.computer_use" in dict(tests)[name]
        )
        relevant_tests = sorted(set(relevant_tests) - set(excluded_tests))
        maturity = "TESTED" if suite_passed and relevant_tests else "CODE_PRESENT"
        if module in LIVE_OVERRIDES:
            maturity = LIVE_OVERRIDES[module]
        transitions: list[dict[str, Any]] = [{
            "to": "CODE_PRESENT",
            "evidence_ids": ["EV-SEALED-TREE"],
            "locator": {
                "path": rel,
                "source_id": source_by_path[rel]["source_id"],
                "git_blob_sha": source_by_path[rel]["git_blob_sha"],
            },
        }]
        if suite_passed and relevant_tests:
            transitions.append({
                "to": "TESTED",
                "evidence_ids": ["EV-PYTEST-FULL"],
                "locator": relevant_tests,
                "scope_limit": "The named passing tests support only their asserted properties; import presence and suite success do not prove the entire module.",
            })
        if maturity in {"WIRED", "RUNTIME_CONFIGURED", "LIVE_VERIFIED"}:
            detail = critical_detail.get(capability or "", {})
            default_evidence = "EV-COMPONENT-STATIC" if maturity == "WIRED" else "EV-REALITY-CURRENT"
            higher_evidence, higher_locator = HIGHER_MATURITY_EVIDENCE.get(
                module, (default_evidence, listify(detail.get("real_callers", "bounded phase finding")))
            )
            transitions.append({
                "to": maturity,
                "evidence_ids": [higher_evidence],
                "locator": higher_locator,
                "scope_limit": "This promotion proves only the property stated in the cited observation; it does not imply product acceptance.",
            })
        rows.append({
            "component_id": stable_id("COMP", module),
            "component_kind": "PYTHON_MODULE",
            "name": module,
            "capability_group": capability,
            "purpose": purpose,
            "purpose_confidence": "HIGH" if has_doc else "LOW",
            "owner": apparent_owner(rel),
            "program": infer_program(rel),
            "source_paths": [rel],
            "public_contracts": contracts,
            "maturity": maturity,
            "maturity_transitions": transitions,
            "direct_test_locators": direct_tests,
            "tested_property_locators": relevant_tests,
            "excluded_test_locators": excluded_tests,
            "related_frontier_ids": CRITICAL_FRONTIERS.get(capability or "", []),
            "current": True,
            "confidence": "HIGH" if has_doc else "MEDIUM",
            "independence_key": f"component-module:{module}",
            "epistemic_limit": "Python-module unit in the explicitly defined current executable component population; capability behavior may span modules and is separately mapped in the authority overlay.",
        })
    for rel, kind, default_purpose, unrun_tests in extra_implementation_units():
        file_path = ROOT / rel
        if rel.startswith("src/atlas/") and file_path.suffix == ".py":
            name = module_name(rel)
            purpose, contracts, has_doc = module_contracts(file_path)
        else:
            name = f"{kind.lower()}:{rel}"
            contracts = source_surface_contracts([rel])
            text = read_text_if_possible(file_path)
            first_comment = next(
                (line.lstrip("#/").strip() for line in text.splitlines() if line.strip().startswith(("#", "//"))),
                "",
            )
            purpose = first_comment or default_purpose
            has_doc = bool(first_comment)
        source = source_by_path.get(rel)
        if source is None or source["category"] in {"TEST", "GENERATED", "HISTORICAL"} or source["lifecycle"] in {"ARCHIVED", "GENERATED"}:
            raise RuntimeError(f"invalid implementation-unit source: {rel}")
        capability = "Product/API bridge" if kind == "PRODUCT_IMPLEMENTATION_UNIT" else None
        rows.append({
            "component_id": stable_id("COMP", name),
            "component_kind": kind,
            "name": name,
            "capability_group": capability,
            "purpose": purpose,
            "purpose_confidence": "HIGH" if has_doc else "MEDIUM",
            "owner": apparent_owner(rel),
            "program": infer_program(rel),
            "source_paths": [rel],
            "public_contracts": contracts,
            "maturity": "CODE_PRESENT",
            "maturity_transitions": [{
                "to": "CODE_PRESENT",
                "evidence_ids": ["EV-SEALED-TREE"],
                "locator": {
                    "path": rel,
                    "source_id": source["source_id"],
                    "git_blob_sha": source["git_blob_sha"],
                },
                "scope_limit": "File-level implementation presence only; no wiring, runtime use, reliability, or product acceptance is inferred.",
            }],
            "direct_test_locators": unrun_tests,
            "tested_property_locators": [],
            "excluded_test_locators": unrun_tests,
            "related_frontier_ids": ["FR-P08-001"] if kind in {"PRODUCT_IMPLEMENTATION_UNIT", "PROTOTYPE_IMPLEMENTATION_UNIT"} else [],
            "current": True,
            "confidence": "HIGH",
            "independence_key": "implementation-unit:" + rel,
            "epistemic_limit": (
                "Flutter/native tests were not executed in FR-000/FR-001."
                if unrun_tests else
                "This current code-bearing file is one implementation unit, not an independent semantic capability claim."
            ),
        })
    if len(rows) != 471:
        raise RuntimeError(f"implementation-unit denominator changed: {len(rows)} != 471")
    return rows


def build_authority(component_findings: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in component_findings["component_inventory"]:
        callers = listify(item["real_callers"])
        writers = listify(item["writers_and_state_owner"])
        state_owner = listify(item["writers_and_state_owner"])
        if item["component"] == "Mission":
            callers = [
                "src/atlas/mcp/knowledge_trunk.py:131-150 KnowledgeTrunk._ingest calls run_mission",
                "src/atlas/knowledge/run.py:17-38 run_mission constructs MissionRunner and calls run_once",
            ]
            writers = ["MissionRunner via KnowledgeBase.add after verification"]
            state_owner = ["KnowledgeBase domain JSONL; MissionRunner owns no durable scheduler state"]
        elif item["component"] == "Product/API bridge":
            writers = [
                "src/atlas/api/server.py:create_app authenticated POST event writer",
                "src/atlas/events/core_bridge.py:CoreEventBridge.on_core_event direct EventStore append",
                "src/atlas/events/emit.py:emit_event direct EventStore append",
                "src/atlas/events/player.py:EventPlayer replay append",
                "src/atlas/business/core_engine.py business mutations through emit_event",
                "src/atlas/interfaces/exec_api.py nonce SQLite writer",
            ]
            state_owner = [
                "OsEventStore/EventStore JSONL for projected events",
                "exec_nonces.sqlite3 for exec API nonce state",
                "underlying Atlas domain stores remain separate authorities",
            ]
        rows.append({
            "record_kind": "COMPONENT_AUTHORITY",
            "authority_id": stable_id("AUTH", item["component"]),
            "component": item["component"],
            "owner": item["owner"],
            "program": item["program"],
            "callers": callers,
            "writers": writers,
            "state_owner": state_owner,
            "read_paths": listify(item["read_paths"]),
            "write_paths": listify(item["write_paths"]),
            "alternative_paths": listify(item["alternate_paths_bypasses"]),
            "bypasses": listify(item["alternate_paths_bypasses"]),
            "public_ports": listify(item["ports"]),
            "mutation_boundaries": listify(item["mutation_boundary"]),
            "failure_semantics": listify(item["failure_semantics"]),
            "source_paths": listify(item["source_paths"]),
            "public_contracts": listify(item["public_contracts"]),
            "observed_maturity_claim": item["maturity"],
            "related_frontier_ids": CRITICAL_FRONTIERS.get(item["component"], []),
            "confidence": "HIGH" if item["maturity"]["level"] in {"CODE", "WIRING"} else "MEDIUM",
            "epistemic_limit": "Static caller/writer reconstruction plus bounded live observations; absence of a bypass is not proven.",
        })
    for item in component_findings["authority_rows"]:
        writers = listify(item["writers"])
        canonical_owner = item["canonical_owner"]
        risk = item["risk"]
        if item["domain"] == "Product events":
            writers = [
                "src/atlas/api/server.py authenticated POST routes",
                "src/atlas/events/core_bridge.py CoreEventBridge.on_core_event",
                "src/atlas/events/emit.py emit_event",
                "src/atlas/events/player.py EventPlayer replay",
                "src/atlas/business/core_engine.py through emit_event",
            ]
            canonical_owner = "OsEventStore.append is the physical JSONL writer; several production-facing paths invoke it"
            risk = "Multiple logical writers converge on one physical append method, while CoreEventBridge itself has only test instantiation evidence."
        rows.append({
            "record_kind": "STATE_DOMAIN_AUTHORITY",
            "authority_id": stable_id("AUTH-DOMAIN", item["domain"]),
            "domain": item["domain"],
            "canonical_owner": canonical_owner,
            "writers": writers,
            "risk": risk,
            "multiple_writers": len(writers) > 1,
            "confidence": "HIGH",
        })
    return rows


def map_decision_status(row: dict[str, Any]) -> str:
    decision_id = str(row.get("id", ""))
    if row.get("type") == "atomic_decision":
        # ADR-076 section C is the explicit rejected auto-adoption branch;
        # the remaining atomic records are accepted decision atoms even when
        # their implementation field is partial or absent.
        return "REJECTED" if decision_id == "ADR-076-C" else "ACTIVE"
    if decision_id in {"ADR-057", "ADR-058", "ADR-069", "ADR-078"}:
        return "PROVISIONAL"
    if decision_id == "ADR-059":
        # ADR-071 supersedes final-product UX scope only; do not promote a
        # scoped relation into blanket supersession.
        return "PROVISIONAL"
    status = str(row.get("status") or "").upper()
    authority = str(row.get("authority") or "")
    if authority == "HISTORICAL_DECISION_RECORD":
        return "HISTORICAL"
    if "CONTRADICT" in status:
        return "CONTRADICTED"
    if "REJECT" in status:
        return "REJECTED"
    if "SUPERSED" in status or "RETIRED" in status:
        return "SUPERSEDED"
    if status in {"PROPOSED", "PARKED", "OBSERVED_OR_UNKNOWN"} or "PARTIAL" in status:
        return "PROVISIONAL" if status != "OBSERVED_OR_UNKNOWN" else "UNKNOWN"
    if status.startswith("ACCEPTED") or status in {
        "OPERATOR_EXPLICIT_FOR_COMPILER_RUN", "CURRENT_REPOSITORY_ACCEPTED",
    }:
        return "ACTIVE"
    return "UNKNOWN"


RELATION_ENDPOINTS: dict[str, tuple[list[str], list[str]]] = {
    "SUP-ADR-026-ADR-011-IDENTITY": (["ADR-026"], ["ADR-011"]),
    "SUP-ADR-028-ADR-026-TRANSPORT": (["ADR-028"], ["ADR-026"]),
    "SUP-ADR-040-ADR-032-033": (["ADR-040"], ["ADR-032", "ADR-033"]),
    "SUP-ADR-068-ADR-066": (["ADR-068"], ["ADR-066"]),
    "SUP-ADR-070-ADR-011": (["ADR-070"], ["ADR-011"]),
    "SUP-ADR-071-ADR-059": (["ADR-071"], ["ADR-059"]),
    "SUP-ADR-074-OSM-042-PHASE1": (["ADR-074"], ["OSM-042"]),
    "SUP-ADR-075-ADR-072": (["ADR-075"], ["ADR-072"]),
    "SUP-ADR-075-ADR-073": (["ADR-075"], ["ADR-073"]),
    "SUP-ADR-076-ADR-075": (["ADR-076-A", "ADR-076-B"], ["ADR-075"]),
    "SUP-ADR-077-ADR-076-C": (["ADR-077"], ["ADR-076-C"]),
    "SUP-ADR-077-CONSTITUTIONAL-RULE-4": (["ADR-077"], ["CONSTITUTIONAL-RULE-4"]),
    "SUP-ADR-078-ADR-071-DESKTOP-HOST": (["ADR-078"], ["ADR-071"]),
    "SUP-ADR-078-HISTORICAL-SHELL-QUESTION": (["ADR-078"], ["ATR-QUESTION-OPEN-6885DDD3AD62"]),
    "SUP-ADR-080-ADR-058-071-READONLY": (["ADR-080"], ["ADR-058", "ADR-071"]),
}

AUTHORITY_CHANGING_RELATIONS = {
    "REVISES", "PARTIALLY_SUPERSEDES", "SUPERSEDES_FRAMING", "RETIRES",
    "SUPERSEDES", "PROMOTES_SLICE", "REFINES", "RESOLVES_SCOPE",
}

AUDIT_RELATIONS = [
    {
        "edge_id": "CON-ADC-WO-107-ADR-058-071",
        "relation": "CONTRADICTS",
        "from_ids": ["ADC-WO-107"],
        "to_ids": ["ADR-058", "ADR-071"],
        "scope": "Mission approve/reject mutation outside the accepted Product OS exception",
        "source": "phase_records/decision_findings.json",
    },
    {
        "edge_id": "CON-ADC-WO-109-LINEAGE-STATE",
        "relation": "CONTRADICTS",
        "from_ids": ["ADC-WO-109"],
        "to_ids": ["LINEAGE-CODEOSS-1-129-1"],
        "scope": "current external checkout is pin-1.132.0 while tracked lineage/index still identify 1.129.1 branch/head and the work-order row contains mutually incompatible state claims",
        "source": "phase_records/codeoss_external_state.json",
    },
]

DECISION_SUBJECT_ALIASES = {
    "ATR-REPO-1A59D2E5A0E2": "ADR-073",
    "ATR-REPO-42F3E1DB786D": "ADR-076-B",
    "ATR-REPO-4E04454DE793": "ADR-072",
    "ATR-REPO-5F7C24C9C131": "ADR-074",
    "ATR-REPO-7752725D1CCC": "ADR-076-A",
    "ATR-REPO-B21C4C092504": "ADR-075",
    "ATR-REPO-BFD9B7930597": "ADR-076-C",
    "ATR-REPO-C2FFF62F4EA4": "ADR-077",
}


def load_explicit_relations() -> list[dict[str, Any]]:
    registry_path = ROOT / "docs/canon/supersession_registry.jsonl"
    registry = load_jsonl(registry_path)
    if len(registry) != 15 or {row["id"] for row in registry} != set(RELATION_ENDPOINTS):
        raise RuntimeError("supersession registry population/identity changed")
    rows: list[dict[str, Any]] = []
    for source in registry:
        from_ids, to_ids = RELATION_ENDPOINTS[source["id"]]
        rows.append({
            "edge_id": source["id"],
            "relation": source["relation"],
            "from_ids": from_ids,
            "to_ids": to_ids,
            "from": from_ids[0],
            "to": to_ids[0],
            "scope": source["scope"],
            "date": source.get("date"),
            "authority": source.get("authority"),
            "preserved": listify(source.get("preserved")),
            "annulled": listify(source.get("annulled")),
            "source_path": source.get("source_path"),
            "source_ref": source.get("source_ref"),
            "source": "docs/canon/supersession_registry.jsonl",
            "explicit": True,
            "chronology_inferred": False,
            "confidence": "HIGH",
            "independence_key": "decision-edge:" + source["id"],
        })
    for relation in AUDIT_RELATIONS:
        rows.append({
            **relation,
            "from": relation["from_ids"][0],
            "to": relation["to_ids"][0],
            "date": None,
            "authority": "CURRENT_AUDIT_OBSERVATION",
            "preserved": [],
            "annulled": [],
            "source_path": relation["source"],
            "source_ref": EXPECTED_COMMIT,
            "explicit": True,
            "chronology_inferred": False,
            "confidence": "HIGH",
            "independence_key": "decision-edge:" + relation["edge_id"],
        })
    return rows


def build_decisions(decision_findings: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = load_jsonl(ROOT / "docs/canon/decision_registry.jsonl")
    work_orders = yaml.safe_load((ROOT / "docs/canon/implementation_registry.yaml").read_text(encoding="utf-8"))["work_orders"]
    focused = {r["id"]: r for r in decision_findings["focused_revalidation"]}
    relations = load_explicit_relations()
    supersedes: dict[str, list[str]] = defaultdict(list)
    superseded_by: dict[str, list[str]] = defaultdict(list)
    contradicts: dict[str, list[str]] = defaultdict(list)
    depends_on: dict[str, list[str]] = defaultdict(list)
    non_supersession: dict[str, list[str]] = defaultdict(list)
    for edge in relations:
        if edge["relation"] in AUTHORITY_CHANGING_RELATIONS:
            for new_id in edge["from_ids"]:
                supersedes[new_id].extend(edge["to_ids"])
            for old_id in edge["to_ids"]:
                superseded_by[old_id].extend(edge["from_ids"])
        elif edge["relation"] in {"EXTENDS", "EXTENDS_PARTIALLY"}:
            for new_id in edge["from_ids"]:
                depends_on[new_id].extend(edge["to_ids"])
        elif edge["relation"].startswith("DOES_NOT"):
            for new_id in edge["from_ids"]:
                non_supersession[new_id].extend(edge["to_ids"])
        if edge["relation"] == "CONTRADICTS":
            for left in edge["from_ids"]:
                contradicts[left].extend(edge["to_ids"])
            for right in edge["to_ids"]:
                contradicts[right].extend(edge["from_ids"])
    rows: list[dict[str, Any]] = []
    for source in registry:
        did = source["id"]
        focus = focused.get(did, {})
        explicit = focus.get("explicit_relations", {})
        implemented = source.get("implementation", [])
        if isinstance(implemented, str):
            implemented = [implemented]
        sources = source.get("sources", [])
        locator = [
            s.get("member") or s.get("locator") for s in sources
            if isinstance(s, dict) and (s.get("member") or s.get("locator"))
        ]
        authority = str(source.get("authority") or "")
        current = authority.startswith("CURRENT_")
        rows.append({
            "decision_id": did,
            "record_kind": source.get("type", "decision"),
            "title": source.get("title", "UNKNOWN"),
            "date": source.get("date"),
            "status": map_decision_status(source),
            "source_status": source.get("status"),
            "authority": source.get("authority"),
            "authority_scope": "CURRENT" if current else "HISTORICAL_OR_EXTERNAL_DISPOSITION",
            "current": current,
            "program": source.get("program_primary", "UNKNOWN"),
            "programs_related": listify(source.get("programs_related")),
            "locators": locator or ["docs/canon/decision_registry.jsonl"],
            "supersedes": sorted(set(supersedes[did] + listify(explicit.get("supersedes")))),
            "superseded_by": sorted(set(superseded_by[did] + listify(explicit.get("superseded_by")))),
            "contradicts": sorted(set(contradicts[did] + listify(explicit.get("contradicts")))),
            "depends_on": sorted(set(depends_on[did] + listify(explicit.get("depends_on")))),
            "non_supersession_relations": sorted(set(non_supersession[did])),
            "implemented_by": listify(explicit.get("implemented_by", implemented)),
            "tested_by": listify(explicit.get("tested_by")),
            "runtime_evidence": listify(explicit.get("runtime_evidence")),
            "falsifier": explicit.get("falsifier", "UNKNOWN; no decision-specific falsifier in the canonical registry row"),
            "falsifier_status": "NOT_RUN" if focus else "UNKNOWN",
            "evidence_for_status": listify(focus.get("for_status")),
            "evidence_against_or_limiting": listify(focus.get("against_or_limiting_evidence")),
            "status_evidence_ids": [f"EV-{did}-FOR", f"EV-{did}-LIMIT"] if focus else [],
            "evidence_qualification": source.get("evidence_qualification"),
            "source_independence": source.get("source_independence", "UNKNOWN"),
            "source_occurrence_count": source.get("source_occurrence_count", 1),
            "unique_content_hash_count": source.get("unique_content_hash_count", 1),
            "semantic_duplicate_of": DECISION_SUBJECT_ALIASES.get(did),
            "decision_subject_key": DECISION_SUBJECT_ALIASES.get(did, did),
            "confidence": focus.get("confidence", source.get("epistemic_confidence", "MEDIUM")),
            "independence_key": "decision-subject:" + DECISION_SUBJECT_ALIASES.get(did, did),
        })
    for work in work_orders:
        did = work["id"]
        status = str(work.get("status", "UNKNOWN")).upper()
        if did in {"ADC-WO-107", "ADC-WO-109", "ADC-WO-124"}:
            mapped = "CONTRADICTED"
        elif status == "REJECTED":
            mapped = "REJECTED"
        elif status == "DONE":
            mapped = "ACTIVE"
        elif status in {"READY", "BLOCKED", "REQUIRES_OPERATOR"}:
            mapped = "PROVISIONAL"
        else:
            mapped = "UNKNOWN"
        focus = focused.get(did, {})
        explicit = focus.get("explicit_relations", {})
        rows.append({
            "decision_id": did,
            "record_kind": "ADC_WORK_ORDER",
            "title": work.get("title", "UNKNOWN"),
            "date": work.get("date"),
            "status": mapped,
            "source_status": work.get("status"),
            "authority": "IMPLEMENTATION_REGISTRY_CLAIM; NOT AUTOMATIC CANON OR RUNTIME PROOF",
            "authority_scope": "CURRENT_CANON_REGISTRY_CLAIM",
            "current": True,
            "program": work.get("program", "UNKNOWN"),
            "programs_related": [],
            "locators": ["docs/canon/implementation_registry.yaml:" + did],
            "supersedes": sorted(set(supersedes[did])),
            "superseded_by": sorted(set(superseded_by[did])),
            "contradicts": sorted(set(contradicts[did] + listify(explicit.get("contradicts")))),
            "depends_on": sorted(set(depends_on[did] + listify(work.get("dependencies")))),
            "non_supersession_relations": sorted(set(non_supersession[did])),
            "implemented_by": listify(explicit.get("implemented_by", work.get("files"))),
            "tested_by": listify(explicit.get("tested_by", work.get("tests"))),
            "runtime_evidence": listify(explicit.get("runtime_evidence", "HISTORICAL/DOCUMENT CLAIM ONLY unless separately registered")),
            "falsifier": explicit.get("falsifier", "Acceptance list fails under reproducible current execution"),
            "falsifier_status": "NOT_RUN_IN_FR000_FR001",
            "evidence_for_status": listify(focus.get("for_status")),
            "evidence_against_or_limiting": listify(focus.get("against_or_limiting_evidence")),
            "status_evidence_ids": [f"EV-{did}-FOR", f"EV-{did}-LIMIT"] if focus else [],
            "evidence_qualification": (
                "CONTRADICTED_DOCUMENTS_AND_EXTERNAL_STATE" if did == "ADC-WO-109"
                else "CONTRADICTED_DOCUMENTS" if did in {"ADC-WO-107", "ADC-WO-124"}
                else "DOCUMENT_CLAIM_NOT_LIVE_REVALIDATED"
            ),
            "source_independence": "PRIMARY_REGISTRY_ROW_WITH_EMBEDDED_CLAIMS",
            "source_occurrence_count": 1,
            "unique_content_hash_count": 1,
            "semantic_duplicate_of": None,
            "decision_subject_key": did,
            "confidence": focus.get("confidence", "MEDIUM"),
            "independence_key": "decision:" + did,
        })
    endpoint_metadata = {
        "ADR-011": ("HermesRestAdapter transport decision", "SUPERSEDED", "P10"),
        "OSM-042": ("Membrane active-defense research record; only Phase 1 was promoted", "PROVISIONAL", "P09"),
        "ATR-QUESTION-OPEN-6885DDD3AD62": ("Desktop-host selection question still marked OPEN despite ADR-078 resolution", "CONTRADICTED", "P08"),
        "CONSTITUTIONAL-RULE-4": ("High-sensitivity human-control constitutional rule", "ACTIVE", "P01"),
        "LINEAGE-CODEOSS-1-129-1": ("Tracked Code OSS 1.129.1 lineage record", "CONTRADICTED", "P08"),
    }
    known_ids = {row["decision_id"] for row in rows}
    relation_endpoint_ids = {
        endpoint for edge in relations for endpoint in edge["from_ids"] + edge["to_ids"]
    }
    for did in sorted(relation_endpoint_ids - known_ids):
        title, status, program = endpoint_metadata.get(did, ("Explicit graph endpoint", "UNKNOWN", "UNKNOWN"))
        rows.append({
            "decision_id": did,
            "record_kind": "GRAPH_ENDPOINT",
            "title": title,
            "date": None,
            "status": status,
            "source_status": "EXPLICIT_RELATION_ENDPOINT",
            "authority": "EXPLICIT_RELATION_OR_LINEAGE_REFERENCE",
            "authority_scope": "GRAPH_ENDPOINT_ONLY",
            "current": False,
            "program": program,
            "programs_related": [],
            "locators": ["docs/canon/supersession_registry.jsonl"],
            "supersedes": sorted(set(supersedes[did])),
            "superseded_by": sorted(set(superseded_by[did])),
            "contradicts": sorted(set(contradicts[did])),
            "depends_on": sorted(set(depends_on[did])),
            "non_supersession_relations": sorted(set(non_supersession[did])),
            "implemented_by": [],
            "tested_by": [],
            "runtime_evidence": [],
            "falsifier": "NOT_APPLICABLE; graph endpoint retained for referential totality.",
            "falsifier_status": "NOT_APPLICABLE",
            "evidence_for_status": [],
            "evidence_against_or_limiting": [],
            "status_evidence_ids": [],
            "evidence_qualification": "GRAPH_ENDPOINT_ONLY",
            "source_independence": "PRIMARY_EXPLICIT_RELATION_OR_LINEAGE_REFERENCE",
            "source_occurrence_count": 1,
            "unique_content_hash_count": 1,
            "semantic_duplicate_of": None,
            "decision_subject_key": did,
            "confidence": "HIGH" if did in endpoint_metadata else "MEDIUM",
            "independence_key": "decision:" + did,
        })
    for number in range(13):
        did = f"P{number:02d}"
        rows.append({
            "decision_id": did,
            "record_kind": "PROGRAM_DECISION",
            "title": f"Atlas program {did}",
            "date": None,
            "status": "ACTIVE",
            "source_status": "CURRENT_PROGRAM_STRUCTURE",
            "authority": "PROGRAMS.md",
            "authority_scope": "CURRENT",
            "current": True,
            "program": did,
            "programs_related": [],
            "locators": ["PROGRAMS.md"],
            "supersedes": [],
            "superseded_by": [],
            "contradicts": [],
            "depends_on": [],
            "non_supersession_relations": [],
            "implemented_by": [],
            "tested_by": [],
            "runtime_evidence": [],
            "falsifier": "UNKNOWN; program framing is not itself a capability claim",
            "falsifier_status": "NOT_APPLICABLE",
            "evidence_for_status": [],
            "evidence_against_or_limiting": [],
            "status_evidence_ids": [],
            "evidence_qualification": "CURRENT_ORGANIZATIONAL_AUTHORITY_ONLY",
            "source_independence": "PRIMARY",
            "source_occurrence_count": 1,
            "unique_content_hash_count": 1,
            "semantic_duplicate_of": None,
            "decision_subject_key": did,
            "confidence": "HIGH",
            "independence_key": "decision:" + did,
        })
    return rows, relations


def normalized_observation_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256_bytes(payload)


def evidence_record(
    evidence_id: str,
    kind: str,
    locator: str,
    source_hash: str | None,
    *,
    raw_preserved: bool,
    reproducible: bool | str,
    independently_verifiable: bool | str,
    freshness: str,
    measurement_validity: str,
    contamination: list[str] | None = None,
    independence_key: str,
    supports: list[str] | None = None,
    contradicts: list[str] | None = None,
    confidence: str = "HIGH",
    observation: str = "",
    derived_from_evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "type": kind,
        "locator": locator,
        "source_hash": source_hash,
        "raw_preserved": raw_preserved,
        "reproducible": reproducible,
        "independently_verifiable": independently_verifiable,
        "freshness": freshness,
        "measurement_validity": measurement_validity,
        "contamination": contamination or [],
        "independence_key": independence_key,
        "supports": supports or [],
        "contradicts": contradicts or [],
        "confidence": confidence,
        "observation": observation,
        "derived_from_evidence_ids": derived_from_evidence_ids or [],
    }


def build_evidence(pack_zip: Path) -> list[dict[str, Any]]:
    graph_path = PHASE / "graph_first_queries.json"
    preflight_path = PHASE / "phase_00_preflight.json"
    pack_phase = PHASE / "phase_01_pack_intake.json"
    source_phase = PHASE / "source_docs_findings.json"
    component_phase = PHASE / "component_authority_findings.json"
    decision_phase = PHASE / "decision_findings.json"
    test_phase = PHASE / "test_results.json"
    current_reality_path = PHASE / "reality_snapshot_20260821.json"
    codeoss_path = PHASE / "codeoss_external_state.json"
    cross_review_path = PHASE / "cross_model_review.json"
    self_review_path = PHASE / "adversarial_self_review.jsonl"
    f26_path = ROOT / "work/checkpoints/FINAL_CHECKPOINT_MANIFEST.json"
    docs_drift_path = ROOT / "work/checkpoints/CR-001_DOCS_INDEX_DRIFT.json"
    semgrep_path = ROOT / "work/checkpoints/CR-001_SEMGREP_MAJOR_FINDINGS.json"
    api_path = ROOT / "src/atlas/api/server.py"
    mcp_path = ROOT / "src/atlas/mcp/trunk_server.py"
    mcp_catalog_path = ROOT / "src/atlas/mcp/catalog.py"
    memory_path = ROOT / "src/atlas/memory/memory_system.py"
    secrets_path = ROOT / "src/atlas/fabric/auth_broker.py"
    dotenv_loader = ROOT / "scripts/safe_dotenv.py"
    cli_path = ROOT / "src/atlas/interfaces/cli.py"
    dashboard_path = ROOT / "src/atlas/interfaces/dashboard.py"
    coding_path = ROOT / "src/atlas/api/coding_server.py"
    orchestrator_path = ROOT / "src/atlas/core/orchestrator.py"
    checkpoint = load_json(f26_path)
    f26_execution = checkpoint.get("f26_execution_result", {})
    f26_validity = checkpoint.get("f26_measurement_validity", {})
    if (
        f26_execution.get("execution_outcome") != "FAIL"
        or f26_execution.get("automatic_grade") != "1/6"
        or f26_validity.get("status") != "INCONCLUSIVE"
    ):
        raise RuntimeError("CR-001 F2.6 preservation fields changed")
    semgrep_summary = load_json(semgrep_path)
    if sum(int(row.get("historical_finding_count", 0)) for row in semgrep_summary.get("findings", [])) != 16:
        raise RuntimeError("CR-001 Semgrep candidate summary count changed")
    rows = [
        evidence_record(
            "EV-SEALED-TAG", "GIT_REF", EXPECTED_TAG,
            "git-object:c5652f6317cc8ad71033edad876fe4da40d7a3ce",
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="git-ref:atlas-n-cr001-20260820",
            supports=["CLAIM-ATLAS-N-IDENTITY"],
            observation="The ref is an annotated tag object; peeling ^{commit} yields the expected commit.",
        ),
        evidence_record(
            "EV-SEALED-TREE", "GIT_TREE", f"{EXPECTED_TAG}^{{tree}}", f"git-tree:{EXPECTED_TREE}",
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key=f"git-tree:{EXPECTED_TREE}", supports=["CLAIM-ATLAS-N-IDENTITY", "CLAIM-SOURCE-UNIVERSE"],
            observation="The peeled commit and tree exactly match the immutable baseline.",
        ),
        evidence_record(
            "EV-PACK-ZIP", "OPERATOR_INPUT", str(pack_zip), "sha256:" + sha256_file(pack_zip),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="historical", measurement_validity="PARTIAL",
            contamination=["Frontier Pack is an operator-supplied hypothesis set and is authority rank 8."],
            independence_key="operator-pack:" + PACK_SHA256, supports=["CLAIM-R0-109-HYPOTHESES"],
            observation="ZIP contains the R0 working inventory; it is not part of the sealed tree and is not canon.",
        ),
        evidence_record(
            "EV-PACK-VALIDATION", "VALIDATOR_RESULT", str(pack_phase.relative_to(ROOT)), "sha256:" + sha256_file(pack_phase),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["Bundled validator checks only fixed count, frontier-ID uniqueness, and referenced research IDs."],
            independence_key="operator-pack:" + PACK_SHA256, supports=["CLAIM-R0-109-HYPOTHESES"],
            observation="All 24 manifest-listed payloads match; validator PASS does not validate truth or complete schema semantics.",
            derived_from_evidence_ids=["EV-PACK-ZIP"],
        ),
        evidence_record(
            "EV-GRAPH-QUERIES", "PROJECT_GRAPH_QUERY", str(graph_path.relative_to(ROOT)), "sha256:" + sha256_file(graph_path),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["Import edges are structural, not behavioral calls.", "Graph was rebuilt in shared Atlas workspace state."],
            independence_key=f"project-graph:{EXPECTED_COMMIT}",
            supports=["CLAIM-GRAPH-FRESH", "CLAIM-STRUCTURAL-IMPORTS"],
            observation="Graph is FRESH at the sealed commit; 329 current modules and critical import/blast queries are retained.",
        ),
        evidence_record(
            "EV-REALITY-SEALED", "RUNTIME_OBSERVATION", str(preflight_path.relative_to(ROOT)), "sha256:" + sha256_file(preflight_path),
            raw_preserved=False, reproducible=True, independently_verifiable="unknown",
            freshness="current", measurement_validity="PARTIAL",
            contamination=["Only normalized preflight fields were retained.", "Runtime is environment-bound and outside the Git tree."],
            independence_key="reality:operator-checkout-preflight:2026-08-21",
            supports=["CLAIM-RUNTIME-ENVIRONMENT-BOUND", "CLAIM-F26-DUE"],
            observation="Original-checkout preflight reported graph STALE and F2.6 due; it retained no current Hermes/provider liveness result.",
        ),
        evidence_record(
            "EV-PYTEST-FULL", "TEST_RESULT", str(test_phase.relative_to(ROOT)), "sha256:" + sha256_file(test_phase),
            raw_preserved=False, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["27 computer_use tests deselected.", "Mocks/fixtures inside passing tests do not prove real integration."],
            independence_key=f"pytest-default:{EXPECTED_COMMIT}", supports=["CLAIM-DEFAULT-SUITE-PASSES"],
            observation="6016 passed, 13 skipped, 27 deselected, one FastEmbed warning; exit 0.",
        ),
        evidence_record(
            "EV-SOURCE-CENSUS", "TREE_CENSUS", str(source_phase.relative_to(ROOT)), "sha256:" + sha256_file(source_phase),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key=f"git-tree:{EXPECTED_TREE}", supports=["CLAIM-SOURCE-UNIVERSE", "CLAIM-DOCS-AUDITOR-MIXED"],
            observation="The sealed tree contains 2,344 tracked blobs; docs-index current missing population is classified exhaustively.",
            derived_from_evidence_ids=["EV-SEALED-TREE"],
        ),
        evidence_record(
            "EV-DOCS-CR001", "PRESERVED_HISTORICAL_RESULT", str(docs_drift_path.relative_to(ROOT)), "sha256:" + sha256_file(docs_drift_path),
            raw_preserved=True, reproducible=False, independently_verifiable=True,
            freshness="historical", measurement_validity="PARTIAL",
            contamination=["The historical auditor scanned a physical filesystem population containing ignored/untracked material."],
            independence_key="cr001-docs-index-drift", supports=["CLAIM-CR001-334-PRESERVED"],
            observation="CR-001 records 334 missing paths = 246 graveyard + 88 non-graveyard.",
        ),
        evidence_record(
            "EV-DOCS-AUDITOR-CURRENT", "AUDITOR_RESULT", "scripts/docs_index_audit.py + phase_records/source_docs_findings.json",
            "sha256:" + sha256_file(ROOT / "scripts/docs_index_audit.py"),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["Auditor scans physical docs/ and includes fixtures/schemas/archive artifacts by suffix."],
            independence_key="docs-index-auditor:" + sha256_file(ROOT / "scripts/docs_index_audit.py"),
            supports=["CLAIM-DOCS-AUDITOR-MIXED"],
            observation="Current result is 97 missing: 20 ordinary documents, 3 schemas, 65 fixtures, 9 archive artifacts; verdict MIXED.",
        ),
        evidence_record(
            "EV-SEMGREP-CR001-CANDIDATES", "PRESERVED_HISTORICAL_SUMMARY", str(semgrep_path.relative_to(ROOT)), "sha256:" + sha256_file(semgrep_path),
            raw_preserved=True, reproducible=False, independently_verifiable=True,
            freshness="historical", measurement_validity="INCONCLUSIVE",
            contamination=["rule_id, path, line, fingerprint, and raw scanner output were not retained."],
            independence_key="cr001-semgrep-candidate-summary", supports=["CLAIM-SEMGREP-RETENTION-GAP"],
            observation="Four candidate summaries preserve 16 historical MAJOR events but cannot be individually triaged.",
        ),
        evidence_record(
            "EV-F26-CR001", "PRESERVED_HISTORICAL_SUMMARY", str(f26_path.relative_to(ROOT)), "sha256:" + sha256_file(f26_path),
            raw_preserved=True, reproducible=False, independently_verifiable=True,
            freshness="historical", measurement_validity="INCONCLUSIVE",
            contamination=["Execution began with graph STALE.", "No independent semantic review was linked."],
            independence_key="f26:cr001:last-run", supports=["CLAIM-F26-FAIL-1-OF-6"],
            contradicts=["CLAIM-F26-AS-CAPABILITY-SCORE"],
            observation="execution_outcome FAIL; automatic_grade 1/6; measurement_validity INCONCLUSIVE. F2.6 was not rerun.",
        ),
        evidence_record(
            "EV-COMPONENT-STATIC", "STATIC_RECONSTRUCTION", str(component_phase.relative_to(ROOT)), "sha256:" + sha256_file(component_phase),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["Bounded static inspection cannot prove absence of dynamic callers or live use."],
            independence_key=f"component-static:{EXPECTED_TREE}", supports=["CLAIM-CRITICAL-COMPONENT-MAP"],
            observation="Twenty critical capability overlays, 11 state authorities, and 12 anomalies were reconstructed.",
        ),
        evidence_record(
            "EV-DECISION-STATIC", "DECISION_RECONSTRUCTION", str(decision_phase.relative_to(ROOT)), "sha256:" + sha256_file(decision_phase),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["No decision falsifier or live mutating route was executed."],
            independence_key=f"decision-static:{EXPECTED_TREE}", supports=["CLAIM-DECISION-REALITY"],
            observation="Canonical decisions, work orders, program decisions, explicit supersession, and focused provisional records were classified.",
        ),
        evidence_record(
            "EV-DECISION-REGISTRY", "CANON_RECORD", "docs/canon/decision_registry.jsonl", "sha256:" + sha256_file(ROOT / "docs/canon/decision_registry.jsonl"),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            contamination=["151 rows are recovered historical decisions; accepted historical claims require source revalidation."],
            independence_key="decision-registry:" + sha256_file(ROOT / "docs/canon/decision_registry.jsonl"),
            supports=["CLAIM-DECISION-INVENTORY"], observation="222 unique canonical registry rows.",
        ),
        evidence_record(
            "EV-SUPERSESSION-REGISTRY", "CANON_RECORD", "docs/canon/supersession_registry.jsonl", "sha256:" + sha256_file(ROOT / "docs/canon/supersession_registry.jsonl"),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="supersession-registry:" + sha256_file(ROOT / "docs/canon/supersession_registry.jsonl"),
            supports=["CLAIM-EXPLICIT-SUPERSESSION"], observation="Fifteen explicit relation records expand to 18 canonical endpoint pairs; no chronological supersession inference was used.",
        ),
        evidence_record(
            "EV-API-MUTATION-CODE", "CODE_LOCATOR", "src/atlas/api/server.py:609-621,769-785", "sha256:" + sha256_file(api_path),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="source:" + sha256_file(api_path),
            supports=["CLAIM-ADC-WO-107-CONTRADICTED", "CLAIM-API-ORCHESTRATOR-BYPASS"],
            observation="Mission approve/reject POST handlers invoke ColdUpdate CLI actions; authenticated request identity is not passed to those commands.",
        ),
        evidence_record(
            "EV-MCP-DUAL-AUTHORITY", "CODE_LOCATOR", "src/atlas/mcp/catalog.py + src/atlas/mcp/trunk_server.py",
            normalized_observation_hash([sha256_file(mcp_catalog_path), sha256_file(mcp_path)]),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            independence_key="source-pair:" + sha256_file(mcp_catalog_path)[:16] + sha256_file(mcp_path)[:16],
            supports=["CLAIM-MCP-DUAL-AUTHORITY"],
            observation="Curated catalog and user-adopted mcp_servers.json are distinct admitted configuration planes.",
        ),
        evidence_record(
            "EV-MEMORY-AUTHORITY-CODE", "CODE_LOCATOR", "src/atlas/memory/memory_system.py", "sha256:" + sha256_file(memory_path),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="PARTIAL",
            independence_key="source:" + sha256_file(memory_path),
            supports=["CLAIM-MEMORY-RAW-JSON-AUTHORITY", "CLAIM-OPTIONAL-MERKLE-GAP"],
            observation="Raw JSON registries are canonical; optional vector replication and optional Merkle logging create bounded alternate behavior.",
        ),
        evidence_record(
            "EV-SECRETS-BOUNDARY-CODE", "CODE_LOCATOR", "src/atlas/fabric/auth_broker.py + scripts/safe_dotenv.py",
            normalized_observation_hash([sha256_file(secrets_path), sha256_file(dotenv_loader)]),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="secret-boundary-code-pair:" + sha256_file(secrets_path)[:16] + sha256_file(dotenv_loader)[:16],
            supports=["CLAIM-AUTHBROKER-REFERENCE-ONLY-SCOPE"],
            observation="AuthBroker forbids plaintext persistence, while process bootstrap still parses plaintext .env values into process memory.",
        ),
        evidence_record(
            "EV-WIRING-API-SERVER", "CODE_CALLER_LOCATOR",
            "src/atlas/interfaces/cli.py:1804-1812 -> src/atlas/api/server.py:serve",
            normalized_observation_hash([sha256_file(cli_path), sha256_file(api_path)]),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="source-call-chain:cli-os-bridge-to-api-server",
            supports=["CLAIM-API-SERVER-WIRED"],
            observation="The concrete atlas os-bridge command imports api.server.serve and calls it with the selected host/port.",
        ),
        evidence_record(
            "EV-WIRING-INFERENCE-HUB", "CODE_CALLER_LOCATOR",
            "src/atlas/api/coding_server.py:94-98,196-206 -> src/atlas/core/inference_hub.py",
            normalized_observation_hash([sha256_file(coding_path), sha256_file(ROOT / "src/atlas/core/inference_hub.py")]),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="source-call-chain:coding-server-to-inference-hub",
            supports=["CLAIM-INFERENCE-HUB-WIRED"],
            observation="The coding server constructs InferenceHub in its real singleton path and invokes infer_for_role for chat completions.",
        ),
        evidence_record(
            "EV-WIRING-ORCHESTRATOR", "CODE_CALLER_LOCATOR",
            "src/atlas/interfaces/cli.py:32-38 + src/atlas/interfaces/dashboard.py:136-144 -> src/atlas/core/orchestrator.py",
            normalized_observation_hash([sha256_file(cli_path), sha256_file(dashboard_path), sha256_file(orchestrator_path)]),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="source-call-chain:cli-dashboard-to-orchestrator",
            supports=["CLAIM-ORCHESTRATOR-WIRED"],
            observation="Both the real CLI accessor and standalone dashboard accessor instantiate Orchestrator and retain it for subsequent calls.",
        ),
        evidence_record(
            "EV-WIRING-MCP-CATALOG", "CODE_CALLER_LOCATOR",
            "src/atlas/mcp/trunk_server.py:519-536 -> src/atlas/mcp/catalog.py:load_catalog/load_taxonomy",
            normalized_observation_hash([sha256_file(mcp_path), sha256_file(mcp_catalog_path)]),
            raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="source-call-chain:trunk-server-to-mcp-catalog",
            supports=["CLAIM-MCP-CATALOG-WIRED"],
            observation="create_trunk imports and calls load_catalog/load_taxonomy, then passes the resulting catalog to trunk_children.",
        ),
        evidence_record(
            "EV-REALITY-CURRENT", "RUNTIME_OBSERVATION", str(current_reality_path.relative_to(ROOT)),
            "sha256:" + sha256_file(current_reality_path), raw_preserved=False,
            reproducible=True, independently_verifiable="unknown", freshness="current",
            measurement_validity="PARTIAL",
            contamination=[
                "Only normalized fields were retained, not full stdout.",
                "The runtime workspace is external to the sealed tree.",
                "The isolated worktree intentionally did not inherit the operator .env.",
            ],
            independence_key="reality:isolated-audit-worktree:2026-08-21",
            supports=["CLAIM-REALITY-COMMAND-EXECUTED", "CLAIM-GRAPH-FRESH", "CLAIM-BROWSER-CONFIGURED", "CLAIM-BWRAP-AVAILABLE"],
            contradicts=["CLAIM-HERMES-LIVE-IN-AUDIT-WORKTREE"],
            observation="Reality completed at the sealed commit: graph FRESH, daemon inactive, Merkle verify ok, browser ready, bwrap present, Hermes mock/unconfigured, F2.6 unknown.",
        ),
        evidence_record(
            "EV-SEMGREP-CR001-RAW-ABSENT", "MISSING_RAW_EVIDENCE",
            "CR-001 per-event Semgrep scanner output", None, raw_preserved=False,
            reproducible=False, independently_verifiable=False, freshness="historical",
            measurement_validity="INCONCLUSIVE",
            contamination=["A future scan would be a new observation and cannot reconstruct the lost historical events."],
            independence_key="cr001-semgrep-raw-events", supports=["CLAIM-SEMGREP-RETENTION-GAP"],
            contradicts=["CLAIM-INDIVIDUAL-SEMGREP-TRIAGE"],
            confidence="HIGH", observation="rule_id, path, line, fingerprint and raw scanner events were not retained.",
            derived_from_evidence_ids=["EV-SEMGREP-CR001-CANDIDATES"],
        ),
        evidence_record(
            "EV-F26-CR001-RAW-ABSENT", "MISSING_RAW_EVIDENCE",
            str(f26_execution.get("transcript")), None, raw_preserved=False,
            reproducible=False, independently_verifiable=False, freshness="historical",
            measurement_validity="INCONCLUSIVE",
            contamination=["The checkpoint points to a transcript path that is absent from both the sealed tree and current runtime workspace."],
            independence_key="f26:cr001:missing-transcript", supports=["CLAIM-F26-RAW-RETENTION-GAP"],
            contradicts=["CLAIM-F26-INDEPENDENTLY-REVIEWABLE"],
            observation="The summary fields are retained, but the named raw transcript and independent semantic review are unavailable.",
            derived_from_evidence_ids=["EV-F26-CR001"],
        ),
        evidence_record(
            "EV-MISSION-CALLER", "CODE_LOCATOR",
            "src/atlas/mcp/knowledge_trunk.py:131-150 -> src/atlas/knowledge/run.py:17-38 -> src/atlas/knowledge/mission.py:40-52",
            normalized_observation_hash([
                sha256_file(ROOT / "src/atlas/mcp/knowledge_trunk.py"),
                sha256_file(ROOT / "src/atlas/knowledge/run.py"),
                sha256_file(ROOT / "src/atlas/knowledge/mission.py"),
            ]), raw_preserved=True, reproducible=True, independently_verifiable=True,
            freshness="current", measurement_validity="VALID",
            independence_key="source-path:mission-interactive-call-chain",
            supports=["CLAIM-MISSION-WIRED-INTERACTIVE"],
            observation="KnowledgeTrunk._ingest calls run_mission, which constructs MissionRunner and executes run_once; no recurring scheduler is implied.",
        ),
        evidence_record(
            "EV-CODEOSS-CURRENT", "EXTERNAL_STATE_OBSERVATION", str(codeoss_path.relative_to(ROOT)),
            "sha256:" + sha256_file(codeoss_path), raw_preserved=True, reproducible=True,
            independently_verifiable=True, freshness="current", measurement_validity="VALID",
            contamination=["Valid only for the separately located external checkout; it is not part of Atlas N."],
            independence_key="external-codeoss-checkout:f7c27192aa938d42ac186bc2ca0e9a83cc06a29c",
            supports=["CLAIM-ADC-WO-109-CONTRADICTED", "CLAIM-CODEOSS-CURRENT-1-132-0"],
            contradicts=["CLAIM-CODEOSS-TRACKED-LINEAGE-CURRENT"],
            observation="The clean external checkout is spike/pin-1.132.0 at f7c27192 with package 1.132.0, while tracked Atlas lineage identifies 1.129.1/8a7abeba.",
        ),
        evidence_record(
            "EV-CROSS-MODEL-REVIEW", "ADVERSARIAL_REVIEW", str(cross_review_path.relative_to(ROOT)),
            "sha256:" + sha256_file(cross_review_path), raw_preserved=False, reproducible=True,
            independently_verifiable=True, freshness="current", measurement_validity="PARTIAL",
            contamination=["Only the final response is retained; the full tool transcript is not.", "Some findings were contract misreads and require reconciliation."],
            independence_key="cross-model:gpt-5.5:01a0230e",
            supports=["CLAIM-ADVERSARIAL-REVIEW-PERFORMED"],
            observation="A separate read-only GPT-5.5 review produced six findings; actionable findings and contract misreads are reconciled in self-review records.",
        ),
        evidence_record(
            "EV-SELF-REVIEW", "ADVERSARIAL_SELF_REVIEW", str(self_review_path.relative_to(ROOT)),
            "sha256:" + sha256_file(self_review_path), raw_preserved=True, reproducible=True,
            independently_verifiable=True, freshness="current", measurement_validity="VALID",
            contamination=["Review corrections are audit-produced evidence and do not independently prove the underlying Atlas properties."],
            independence_key="audit-self-review:fr000-fr001:2026-08-21",
            supports=["CLAIM-ADVERSARIAL-SELF-REVIEW-PERFORMED"],
            observation="Sixteen audit defects or overclaims were retained with original locators and explicit correction/supersession dispositions.",
        ),
    ]

    focused = load_json(decision_phase).get("focused_revalidation", [])
    for item in focused:
        did = item["id"]
        classification_claim = f"CLAIM-{did}-CLASSIFICATION"
        for suffix, field, role in (
            ("FOR", "for_status", "supporting"),
            ("LIMIT", "against_or_limiting_evidence", "counter-or-limiting"),
        ):
            observations = listify(item.get(field))
            locators = [str(entry.get("locator", "")) for entry in observations if isinstance(entry, dict)]
            source_paths: set[str] = set()
            for locator in locators:
                for match in re.findall(r"(?:docs|src|tests|schemas|work|config)/[A-Za-z0-9_./-]+", locator):
                    candidate = match.rstrip(".,")
                    if (ROOT / candidate).is_file():
                        source_paths.add(candidate)
            source_hashes = [sha256_file(ROOT / path) for path in sorted(source_paths)]
            rows.append(evidence_record(
                f"EV-{did}-{suffix}", "FOCUSED_DECISION_EVIDENCE", " | ".join(locators) or str(decision_phase.relative_to(ROOT)),
                normalized_observation_hash(source_hashes or observations), raw_preserved=True,
                reproducible=True, independently_verifiable=True, freshness="current",
                measurement_validity="PARTIAL",
                contamination=["Document/code evidence establishes the bounded classification, not implementation, live runtime, or product acceptance."],
                independence_key=("focused-decision-source-set:" + normalized_observation_hash(source_hashes or observations)),
                supports=[classification_claim],
                contradicts=[f"CLAIM-{did}-HIGHER-MATURITY"] if role != "supporting" else [],
                observation=f"{role.capitalize()} evidence for {did}: " + " ".join(str(entry.get("evidence", "")) for entry in observations if isinstance(entry, dict)),
            ))
    return rows


def build_unknowns(
    pack_unknowns: list[dict[str, Any]],
    source_findings: dict[str, Any],
    component_findings: dict[str, Any],
    decision_findings: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str, str, str]] = []
    for item in pack_unknowns:
        candidates.append((item["question"], "FRONTIER_PACK_HYPOTHESIS", item.get("closure", "UNKNOWN"), item.get("id", "")))
    for question in source_findings["NEW_UNKNOWNS"]:
        candidates.append((question, "SOURCE_CENSUS", "Requires explicit scope policy or preserved external state.", "EV-SOURCE-CENSUS"))
    for question in component_findings["NEW_UNKNOWNS"]:
        candidates.append((question, "COMPONENT_AUTHORITY_AUDIT", "Requires live entrypoint tracing or end-to-end evidence.", "EV-COMPONENT-STATIC"))
    for question in decision_findings["NEW_UNKNOWNS"]:
        candidates.append((question, "DECISION_AUDIT", "Requires operator decision, falsifier, or fresh runtime evidence.", "EV-DECISION-STATIC"))
    candidates.extend([
        ("Which sealed-code paths are actually executing in the active daemon?", "RUNTIME_RECONCILIATION", "Restart/deploy the sealed commit, then obtain fresh process and effect evidence; prohibited in FR-000/001.", "EV-REALITY-SEALED"),
        ("Do configured LLM providers perform a successful current real inference?", "RUNTIME_RECONCILIATION", "Run an authorized provider smoke with raw response/usage retention in a later phase.", "EV-REALITY-SEALED"),
        ("Why does F2.6 resolve as due in the original checkout but unknown in the isolated worktree against the same shared Merkle history?", "RUNTIME_RECONCILIATION", "Define and test the state-path scope contract without rewriting the CR-001 result.", "EV-F26-CR001"),
        ("Are the 27 deselected computer_use tests green against the admitted real dependency and isolated display?", "TEST_REPRODUCTION", "Run the explicitly authorized computer_use lane with raw receipts in a later phase.", "EV-PYTEST-FULL"),
    ])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for question, origin, closure, evidence in candidates:
        key = re.sub(r"\s+", " ", question.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        if origin == "FRONTIER_PACK_HYPOTHESIS":
            evidence_ids = ["EV-PACK-ZIP"]
            locators = [f"operator-pack:inventory/unknowns.jsonl#{evidence}"]
            source_hash = "sha256:" + PACK_SHA256
        else:
            evidence_ids = [evidence] if evidence else []
            locators = []
            source_hash = None
        rows.append({
            "unknown_id": stable_id("UNK", key),
            "question": question,
            "status": "OPEN",
            "origin": origin,
            "closure_condition": closure,
            "evidence_ids": evidence_ids,
            "locators": locators,
            "evidence_ids_or_locators": evidence_ids + locators,
            "source_hash": source_hash,
            "classification": "UNKNOWN",
            "confidence_that_unknown_is_real": "HIGH" if origin != "FRONTIER_PACK_HYPOTHESIS" else "MEDIUM",
            "independence_key": "unknown:" + sha256_bytes(key.encode()),
        })
    return rows


def build_contradictions(
    pack_contradictions: list[dict[str, Any]],
    source_findings: dict[str, Any],
    component_findings: dict[str, Any],
    decision_findings: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in pack_contradictions:
        revalidated = item["id"] in {"CON-006", "CON-007", "CON-008"}
        rows.append({
            "contradiction_id": "PACK-" + item["id"],
            "claim": item["claim"],
            "counterevidence": item["evidence"],
            "status": "CURRENTLY_REVALIDATED" if revalidated else "PACK_HYPOTHESIS_UNVERIFIED",
            "origin": "FRONTIER_PACK",
            "frontier_ids": item.get("frontiers", []),
            "evidence_ids": ["EV-F26-CR001"] if item["id"] == "CON-006" else (["EV-COMPONENT-STATIC"] if revalidated else ["EV-PACK-ZIP"]),
            "resolution": item.get("action"),
            "resolution_status": "OPEN",
            "confidence": "HIGH" if revalidated else "LOW",
            "independence_key": "operator-pack:" + PACK_SHA256,
            "superseded_by_self_review": None,
        })
    current = [
        {
            "id": "CUR-CON-DOCS-POPULATION",
            "claim": "CR-001 observed 334 missing docs-index paths (246 graveyard, 88 non-graveyard).",
            "counter": "The unchanged auditor now observes 97 (9 graveyard, 88 non-graveyard) because 237 physical-tree graveyard artifacts are absent from the sealed tracked tree.",
            "status": "TEMPORAL_SCOPE_CONTRADICTION",
            "evidence": ["EV-DOCS-CR001", "EV-DOCS-AUDITOR-CURRENT"],
            "frontiers": ["FR-P00-001"],
        },
        {
            "id": "CUR-CON-DOCS-CONTRACT",
            "claim": "The auditor prose says it gates every document.",
            "counter": "Its suffix predicate also gates fixtures, schemas, and archived source/build metadata.",
            "status": "ACTIVE_SCOPE_CONTRADICTION",
            "evidence": ["EV-DOCS-AUDITOR-CURRENT"],
            "frontiers": ["FR-P00-001"],
        },
        {
            "id": "CUR-CON-F26",
            "claim": "The F2.6 automatic grade can be read as a capability score.",
            "counter": "The preserved execution is FAIL 1/6 while measurement validity is independently INCONCLUSIVE due to a stale graph and missing semantic review.",
            "status": "ACTIVE_MEASUREMENT_CONTRADICTION",
            "evidence": ["EV-F26-CR001"],
            "frontiers": ["FR-P00-002", "FR-P06-010"],
        },
        {
            "id": "CUR-CON-ADC-WO-107",
            "claim": "The 7341 Core bridge is read-only except for ADR-080's scoped Product OS routes.",
            "counter": "Sealed server code exposes Mission approve/reject POST handlers that mutate ColdUpdate through the CLI outside that scope.",
            "status": "CONTRADICTED_REQUIRES_OPERATOR",
            "evidence": ["EV-API-MUTATION-CODE", "EV-DECISION-STATIC"],
            "frontiers": ["FR-P01-001", "FR-P01-003", "FR-P01-005", "FR-P08-001"],
        },
        {
            "id": "CUR-CON-ADC-WO-124",
            "claim": "Implementation registry says desktop-control admission is DONE with real E2E evidence.",
            "counter": "The current ecosystem map calls it contradicted/quarantined; no external executable or computer_use lane was run here.",
            "status": "DOCUMENTARY_STATE_CONFLICT",
            "evidence": ["EV-DECISION-STATIC", "EV-PYTEST-FULL"],
            "frontiers": ["FR-P02-005", "FR-P08-002", "FR-P09-007"],
        },
        {
            "id": "CUR-CON-ADC-WO-109",
            "claim": "ADC-WO-109 and tracked lineage consistently describe the current Code OSS baseline and implementation state.",
            "counter": "The clean external checkout is 1.132.0/f7c27192 while tracked lineage identifies 1.129.1/8a7abeba; the work-order row also contains mutually incompatible current-state, compiled/running, pin-bump and retracted tsgo claims.",
            "status": "CURRENT_EXTERNAL_STATE_AND_INTERNAL_RECORD_CONTRADICTION",
            "evidence": ["EV-CODEOSS-CURRENT", "EV-DECISION-STATIC"],
            "frontiers": ["FR-P02-005", "FR-P08-002", "FR-P09-007"],
        },
        {
            "id": "CUR-CON-REALITY-SCOPE",
            "claim": "F2.6 state and provider/Hermes reality are checkout-invariant at one commit.",
            "counter": "The original checkout reported F2.6 due and env-backed Hermes; the isolated worktree without local state resolved different statuses against the same code/shared workspace.",
            "status": "ACTIVE_ENVIRONMENT_SCOPE_CONTRADICTION",
            "evidence": ["EV-REALITY-SEALED", "EV-F26-CR001"],
            "frontiers": ["FR-P02-005", "FR-P09-011"],
        },
    ]
    for item in current:
        rows.append({
            "contradiction_id": item["id"],
            "claim": item["claim"],
            "counterevidence": item["counter"],
            "status": item["status"],
            "origin": "CURRENT_AUDIT",
            "frontier_ids": item["frontiers"],
            "evidence_ids": item["evidence"],
            "resolution": "PRESERVED; not resolved in FR-000/FR-001",
            "resolution_status": "OPEN",
            "confidence": "HIGH" if item["id"] != "CUR-CON-ADC-WO-124" else "MEDIUM",
            "independence_key": "current-contradiction:" + item["id"],
            "superseded_by_self_review": None,
        })
    for index, item in enumerate(component_findings["NEW_CONTRADICTIONS"], 1):
        topic_frontiers = {
            "single audit authority": ["FR-P08-001", "FR-P09-005", "FR-P09-006"],
            "single MCP authority": ["FR-P07-008"],
            "security/secret boundary": ["FR-P07-007", "FR-P12-002"],
        }
        rows.append({
            "contradiction_id": f"CUR-CON-AUTH-{index:03d}",
            "claim": item["side_a"],
            "counterevidence": item["side_b"],
            "status": "ACTIVE_SCOPE_CONTRADICTION",
            "origin": "CURRENT_COMPONENT_AUTHORITY_AUDIT",
            "frontier_ids": topic_frontiers.get(item["topic"], []),
            "evidence_ids": ["EV-COMPONENT-STATIC"],
            "resolution": item["resolution"],
            "resolution_status": "OPEN",
            "confidence": "HIGH",
            "independence_key": "authority-contradiction:" + item["topic"],
            "superseded_by_self_review": None,
        })
    return rows


ANOMALY_FRONTIER_FITS: dict[str, list[str]] = {
    "A-001": ["FR-P01-001", "FR-P08-001", "FR-P09-005"],
    "A-002": ["FR-P01-001", "FR-P07-008"],
    "A-003": ["FR-P01-004", "FR-P01-005"],
    "A-004": ["FR-P05-001"],
    "A-005": ["FR-P04-001", "FR-P09-005", "FR-P09-006"],
    "A-006": ["FR-P03-002", "FR-P10-001"],
    "A-007": ["FR-P03-002", "FR-P06-004", "FR-P06-005"],
    "A-008": ["FR-P01-005"],
    "A-008-R": ["FR-P01-005"],
    "A-009": ["FR-P02-001"],
    "A-010": ["FR-P06-002", "FR-P09-009"],
    "A-011": ["FR-P07-007", "FR-P12-002"],
    "A-012": ["FR-P03-003", "FR-P12-007"],
}


def build_anomalies(component_findings: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for original in component_findings["anomaly_rows"]:
        source = dict(original)
        anomaly_id = source.pop("id")
        status = "SUPERSEDED_BY_SELF_REVIEW" if anomaly_id == "A-008" else "OPEN"
        resolution = "SUPERSEDED_BY:A-008-R" if anomaly_id == "A-008" else "REGISTER_ONLY_NO_FIX_IN_FR000_FR001"
        rows.append({
            **source,
            "anomaly_id": anomaly_id,
            "status": status,
            "resolution": resolution,
            "frontier_ids": ANOMALY_FRONTIER_FITS[anomaly_id],
            "independence_key": "caller-writer-anomaly:" + source.get("finding", ""),
        })
    rows.append({
        "anomaly_id": "A-008-R",
        "severity": "medium",
        "kind": "runtime-gap",
        "finding": "Mission is wired to an interactive KnowledgeTrunk caller, but no recurring scheduler, daemon or retry caller was established.",
        "evidence": [
            "src/atlas/mcp/knowledge_trunk.py:131-150",
            "src/atlas/knowledge/run.py:17-38",
            "src/atlas/knowledge/mission.py:40-52",
        ],
        "status": "OPEN",
        "resolution": "REGISTER_ONLY_NO_FIX_IN_FR000_FR001",
        "frontier_ids": ANOMALY_FRONTIER_FITS["A-008-R"],
        "independence_key": "caller-writer-anomaly:mission-recurring-scheduler-gap",
    })
    return rows


def build_candidate_frontier_fit(
    anomalies: list[dict[str, Any]], contradictions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Assess every current unmatched problem before allowing a zero-new-frontier result."""
    assessments: list[dict[str, Any]] = []
    for anomaly in anomalies:
        frontier_ids = listify(anomaly.get("frontier_ids"))
        assessments.append({
            "assessment_id": stable_id("FIT", "anomaly:" + anomaly["anomaly_id"]),
            "subject_kind": "CALLER_WRITER_ANOMALY",
            "subject_id": anomaly["anomaly_id"],
            "problem": anomaly["finding"],
            "fit_result": "MAPPED_EXISTING_FRONTIER" if frontier_ids else "CANDIDATE_NEW_FRONTIER",
            "existing_frontier_ids": frontier_ids,
            "why_distinct_or_not": "The anomaly is an evidence/maturity/authority gap already represented by the listed R0 hypotheses; mapping does not resolve it." if frontier_ids else "No existing frontier fit was established.",
            "confidence": "HIGH" if frontier_ids else "LOW",
        })
    for contradiction in contradictions:
        if contradiction["origin"] == "FRONTIER_PACK":
            continue
        frontier_ids = listify(contradiction.get("frontier_ids"))
        assessments.append({
            "assessment_id": stable_id("FIT", "contradiction:" + contradiction["contradiction_id"]),
            "subject_kind": "CURRENT_CONTRADICTION",
            "subject_id": contradiction["contradiction_id"],
            "problem": contradiction["claim"] + " <> " + contradiction["counterevidence"],
            "fit_result": "MAPPED_EXISTING_FRONTIER" if frontier_ids else "CANDIDATE_NEW_FRONTIER",
            "existing_frontier_ids": frontier_ids,
            "why_distinct_or_not": "The contradiction falls within the authority, evidence, runtime or program boundary of the listed R0 hypotheses; mapping does not resolve it." if frontier_ids else "No existing frontier fit was established.",
            "confidence": "HIGH" if frontier_ids else "LOW",
        })
    candidates = [
        {
            "candidate_frontier_id": stable_id("CANDIDATE-FRONTIER", row["subject_id"]),
            "problem": row["problem"],
            "why_distinct": row["why_distinct_or_not"],
            "evidence": [row["subject_id"]],
            "affected_components": [],
            "dependencies": [],
            "proposed_program": "UNKNOWN",
            "confidence": row["confidence"],
            "derived_from_fit_assessment_id": row["assessment_id"],
        }
        for row in assessments if row["fit_result"] == "CANDIDATE_NEW_FRONTIER"
    ]
    return assessments, candidates


def write_self_review_records() -> None:
    corrections = [
        ("SR-001", "Component denominator counted only 329 ordinary Python modules.", "03_CURRENT_COMPONENT_MAP.jsonl (pre-self-review)", "CORRECTED", "03_CURRENT_COMPONENT_MAP.jsonl now contains the exact 471-unit implementation population."),
        ("SR-002", "MissionRunner had no real caller.", "05_CALLER_WRITER_ANOMALIES.jsonl:A-008", "SUPERSEDED_BY_SELF_REVIEW", "A-008 is preserved as superseded; A-008-R and EV-MISSION-CALLER retain the interactive call chain and the narrower scheduler unknown."),
        ("SR-003", "BrowserTool could inherit TESTED from the default suite.", "03_CURRENT_COMPONENT_MAP.jsonl:atlas.tools.browser (pre-self-review)", "CORRECTED", "computer_use tests are explicitly excluded; BrowserTool is only RUNTIME_CONFIGURED from bounded reality evidence."),
        ("SR-004", "Supersession graph captured only a hand-selected subset.", "06_SUPERSESSION_GRAPH.jsonl (pre-self-review)", "CORRECTED", "All 15 canonical registry records/18 atomic endpoint pairs plus audit contradictions are preserved; chronology remains uninferred."),
        ("SR-005", "Current decision denominator was every non-HISTORICAL status.", "20_COVERAGE_REPORT.json (pre-self-review)", "CORRECTED", "Current authority is explicit current=true: 85 canonical + 36 work orders + 13 programs = 134; graph endpoints are excluded."),
        ("SR-006", "ADC-WO-109 and Code OSS lineage were omitted from current contradictions.", "10_CONTRADICTIONS.jsonl (pre-self-review)", "CORRECTED", "Read-only external identity evidence and the tracked-lineage/work-order contradiction are registered."),
        ("SR-007", "Generated Flutter and archived script files could inflate current conceptual sources.", "01_SOURCE_COVERAGE_REGISTRY.jsonl (pre-self-review)", "CORRECTED", "Fifteen Flutter-generated files are GENERATED/non-conceptual and scripts/archive is ARCHIVED."),
        ("SR-008", "Derivative validators/censuses used independent evidence keys.", "12_EVIDENCE_REGISTRY.jsonl (pre-self-review)", "CORRECTED", "Pack validation shares the pack independence key; tree census derives from EV-SEALED-TREE; raw-absent records are separate."),
        ("SR-009", "F2.6 and Semgrep summary artifacts were labeled as though raw evidence were retained.", "12_EVIDENCE_REGISTRY.jsonl (pre-self-review)", "CORRECTED", "Summary and missing-raw records are separated without rerun or backfill."),
        ("SR-010", "Merge/split hypotheses had high confidence from pack-internal comparison.", "08_FRONTIER_MAPPING.jsonl (pre-self-review)", "CORRECTED", "Both remain LOW-confidence PACK_INTERNAL_ONLY candidates requiring independent reconciliation."),
        ("SR-011", "Zero candidate-new-frontiers was initialized rather than derived.", "09_CANDIDATE_NEW_FRONTIERS.jsonl (pre-self-review)", "CORRECTED", "candidate_new_frontier_fit_assessment.jsonl now covers every anomaly and current contradiction; 09 is derived only from unmatched rows."),
        ("SR-012", "Coverage counted only the curated unknown registry.", "20_COVERAGE_REPORT.json (pre-self-review)", "CORRECTED", "Coverage exposes semantic unknown records and all explicit UNKNOWN dimensions with separate resolution ratios."),
        ("SR-013", "A broad Merkle LIVE_VERIFIED promotion could imply universal effect coverage.", "03_CURRENT_COMPONENT_MAP.jsonl (pre-self-review)", "CORRECTED", "No Merkle module live override remains; bounded verification is evidence, while universal coverage stays contradicted/unknown."),
        ("SR-014", "Original-checkout runtime prose implied current Hermes live use.", "12_EVIDENCE_REGISTRY.jsonl:EV-REALITY-SEALED (pre-self-review)", "CORRECTED", "The retained preflight says only graph STALE/F2.6 due; isolated reality explicitly says Hermes mock/unconfigured."),
        ("SR-015", "Current decision coverage counted eight semantic companion records as independent subjects.", "20_COVERAGE_REPORT.json (pre-final-review)", "CORRECTED", "Coverage now reports 134 current records but deduplicates them to 126 independent decision subjects through decision_subject_key/independence_key."),
        ("SR-016", "Four WIRED promotions cited generic caller labels instead of exact executable call sites.", "03_CURRENT_COMPONENT_MAP.jsonl (pre-final-review)", "CORRECTED", "API server, InferenceHub, Orchestrator, and MCP catalog now cite dedicated code-call evidence with exact caller line locators."),
    ]
    rows = [
        {
            "review_id": review_id,
            "phase": "ADVERSARIAL_SELF_REVIEW",
            "original_finding_or_claim": original,
            "original_locator": locator,
            "status": status,
            "correction": correction,
            "functional_code_changed": False,
        }
        for review_id, original, locator, status, correction in corrections
    ]
    write_jsonl(PHASE / "adversarial_self_review.jsonl", rows)

    reconciliation = [
        ("XMR-001", "Installing the explicitly requested external skill set violated Atlas dependency rules.", "CONTRACT_MISREAD", "The installation was separately authorized, outside Atlas, and no Atlas dependency/hook/plugin was adopted."),
        ("XMR-002", "Readiness was claimed while TODO/self-review remained open.", "ACTIONABLE_CORRECTED", "Readiness now derives from explicit stop-condition booleans after self-review and validation."),
        ("XMR-003", "Literal provenance/authority fields were absent from every source row.", "PARTIAL_CONTRACT_MISREAD_AND_HARDENED", "The contract requires authority/runtime/evidence relevance and source identity, all retained; static schemas now harden the actual fields."),
        ("XMR-004", "Focused ADR evidence for and against was not materialized.", "ACTIONABLE_CORRECTED", "Decision rows and ten focused evidence records preserve both sides for ADC-WO-107 and ADR-057/058/069/078."),
        ("XMR-005", "Merkle LIVE_VERIFIED was too broad.", "ACTIONABLE_CORRECTED", "The broad maturity override was removed; bounded verify evidence does not become universal coverage."),
        ("XMR-006", "Trunk LIVE evidence used a structural locator rather than actual call receipts.", "ACTIONABLE_CORRECTED", "The locator now states that actual trunk_invoke_readonly calls completed, while graph structure remains a separate limitation."),
    ]
    write_jsonl(PHASE / "review_reconciliation.jsonl", [
        {
            "review_id": review_id,
            "phase": "CROSS_MODEL_REVIEW_RECONCILIATION",
            "external_finding": finding,
            "disposition": disposition,
            "basis_or_correction": correction,
        }
        for review_id, finding, disposition, correction in reconciliation
    ])
    write_json(PHASE / "adversarial_self_review_summary.json", {
        "phase": "ADVERSARIAL_SELF_REVIEW",
        "PRESERVED_CONSTRAINTS": [
            "Sealed tag/commit/tree remain unchanged.",
            "No functional code, tests, canon, docs index, F2.6, or Semgrep behavior was changed.",
            "Original erroneous audit findings remain locatable and are marked superseded rather than erased.",
        ],
        "NEW_EVIDENCE": [
            "Independent 471-unit denominator reconstruction.",
            "Read-only Code OSS checkout identity.",
            "Separate cross-model review and reconciliation.",
            "Static schemas and non-tautological population checks.",
        ],
        "INVALIDATED_CLAIMS": [
            "329 Python modules were an exhaustive component denominator.",
            "Mission had no real caller.",
            "Pack-internal merge/split similarity warranted high confidence.",
            "Summary retention implied raw F2.6 or Semgrep evidence retention.",
            "Semantic companion decision records were independent decisions.",
            "Generic caller labels were sufficient evidence for WIRED maturity.",
        ],
        "NEW_UNKNOWNS": [
            "Thousands of source/component/decision/frontier mapping dimensions remain explicitly UNKNOWN even though all records are classified.",
            "No fresh Code OSS build/runtime receipt is attributable to the current external checkout.",
        ],
        "NEW_CONTRADICTIONS": [
            "ADC-WO-109 and tracked lineage conflict with the current external Code OSS checkout and with their own embedded state claims.",
        ],
        "UNCLASSIFIED_COUNT": 0,
    })


def build_negative_evidence(
    component_findings: dict[str, Any], decision_findings: dict[str, Any]
) -> list[dict[str, Any]]:
    items = [
        ("No retained rule/path/line/fingerprint/raw scanner output exists for the 16 historical Semgrep MAJOR events.", "CR-001 candidate artifacts", "EV-SEMGREP-CR001-CANDIDATES", "CLAIM-INDIVIDUAL-SEMGREP-TRIAGE"),
        ("No independent semantic review is linked to the preserved F2.6 run.", "CR-001 checkpoint evidence", "EV-F26-CR001", "CLAIM-F26-VALID-MEASUREMENT"),
        ("No fresh provider inference was executed; keys/configuration are not reachability or usefulness evidence.", "atlas reality without --run-checks", "EV-REALITY-CURRENT", "CLAIM-LLM-LIVE"),
        ("No current daemon process was shown executing the sealed commit; the isolated audit observation reports the daemon inactive.", "current process metadata", "EV-REALITY-CURRENT", "CLAIM-SEALED-CODE-LIVE"),
        ("Mission has an interactive KnowledgeTrunk caller, but no recurring MissionRunner scheduler/daemon/retry caller was established.", "graph plus bounded code inspection", "EV-MISSION-CALLER", "CLAIM-MISSION-SCHEDULED"),
        ("No automatic governed memory promoter is implemented or authorized by ADR-057 evidence.", "ADR-057 dossier and authority map", "EV-DECISION-STATIC", "CLAIM-MEMORY-AUTO-PROMOTION"),
        ("No selective Mission→Task→command→approval→effect journal falsifier was run.", "ADR-069 dossier", "EV-DECISION-STATIC", "CLAIM-DURABLE-MISSION-JOURNAL"),
        ("No complete Atlas Workbench host/product is asserted or live-verified.", "ADR-078 dossier", "EV-DECISION-STATIC", "CLAIM-WORKBENCH-PRODUCT"),
        ("No current external desktop executable or computer_use lane was run.", "default pytest selection", "EV-PYTEST-FULL", "CLAIM-DESKTOP-CONTROL-LIVE"),
        ("No evidence proves every external effect reaches the Merkle logger.", "optional/best-effort loggers and API/EventStore paths", "EV-COMPONENT-STATIC", "CLAIM-UNIVERSAL-MERKLE-COVERAGE"),
        ("No evidence proves every production Hermes delegation selects the real adapter rather than mock/offline paths.", "Hermes static and health inspection", "EV-COMPONENT-STATIC", "CLAIM-HERMES-PRODUCTION-SELECTION"),
        ("No product-acceptance criterion was found for the 471 current implementation units.", "source/test/graph/runtime audit", "EV-COMPONENT-STATIC", "CLAIM-PRODUCT-ACCEPTED"),
        ("No fresh Code OSS build/runtime receipt was produced for the currently observed f7c27192/1.132.0 checkout.", "read-only external checkout identity inspection", "EV-CODEOSS-CURRENT", "CLAIM-CODEOSS-CURRENT-BUILD-RUNTIME"),
    ]
    for finding in decision_findings["accepted_but_unimplemented_claims"]:
        sentence = f"No implementation proving '{finding['claim']}' was found for {finding['id']}."
        if not any(finding["id"] in row[0] for row in items):
            items.append((sentence, finding["evidence"], "EV-DECISION-STATIC", f"CLAIM-{finding['id']}-FULLY-IMPLEMENTED"))
    rows = []
    for sentence, scope, evidence, claim in items:
        rows.append({
            "negative_evidence_id": stable_id("NEG", sentence),
            "claim_examined": claim,
            "observed_absence": sentence,
            "search_scope": scope,
            "locator": evidence,
            "caveat": "Absence is bounded by the stated search scope; it is not universal proof of nonexistence.",
            "effect_on_claim": "PRESERVES_UNKNOWN_OR_CAPS_MATURITY; does not prove universal absence",
            "confidence": "HIGH" if evidence in {"EV-SEMGREP-CR001-CANDIDATES", "EV-F26-CR001", "EV-DECISION-STATIC"} else "MEDIUM",
            "independence_key": "negative:" + sha256_bytes(sentence.encode()),
        })
    return rows


CLAIM_DESCRIPTIONS = {
    "CLAIM-ATLAS-N-IDENTITY": "The named annotated tag peels to the expected immutable commit and tree.",
    "CLAIM-SOURCE-UNIVERSE": "The sealed Git tree is exhaustively censused at tracked-blob level.",
    "CLAIM-R0-109-HYPOTHESES": "The operator pack contains 109 R0 frontier hypotheses; this is a count, not truth or canon.",
    "CLAIM-GRAPH-FRESH": "The queried project graph identified the sealed commit as fresh at observation time.",
    "CLAIM-STRUCTURAL-IMPORTS": "The retained graph queries support structural import relations only.",
    "CLAIM-DEFAULT-SUITE-PASSES": "The configured default pytest selection completed with the retained summary.",
    "CLAIM-DOCS-AUDITOR-MIXED": "The docs-index gate combines real document drift with out-of-contract artifact scope.",
    "CLAIM-CR001-334-PRESERVED": "The historical CR-001 docs-index result remains preserved as 334 paths.",
    "CLAIM-SEMGREP-RETENTION-GAP": "Historical Semgrep summaries exist but event-level raw evidence is missing.",
    "CLAIM-F26-FAIL-1-OF-6": "The preserved F2.6 execution result is FAIL with automatic grade 1/6.",
    "CLAIM-F26-AS-CAPABILITY-SCORE": "The invalid inference that F2.6 1/6 is a valid Atlas capability score.",
    "CLAIM-CRITICAL-COMPONENT-MAP": "Critical capability authority overlays were statically reconstructed.",
    "CLAIM-DECISION-REALITY": "Current, historical, work-order, program and graph-endpoint decision records were classified.",
    "CLAIM-DECISION-INVENTORY": "The canonical decision registry contains 222 unique rows.",
    "CLAIM-EXPLICIT-SUPERSESSION": "The canonical supersession registry contains 15 explicit records/18 endpoint pairs.",
}


def build_claim_registry(
    evidence: list[dict[str, Any]], negative: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    referenced: set[str] = set()
    supported_by: dict[str, list[str]] = defaultdict(list)
    contradicted_by: dict[str, list[str]] = defaultdict(list)
    for row in evidence:
        for claim in row["supports"]:
            referenced.add(claim)
            supported_by[claim].append(row["evidence_id"])
        for claim in row["contradicts"]:
            referenced.add(claim)
            contradicted_by[claim].append(row["evidence_id"])
    for row in negative:
        referenced.add(row["claim_examined"])
    for row in decisions:
        referenced.update(row.get("status_evidence_ids", []))
    # status_evidence_ids are evidence locators, not claim identifiers.
    referenced = {value for value in referenced if value.startswith("CLAIM-")}
    return [
        {
            "claim_id": claim,
            "statement": CLAIM_DESCRIPTIONS.get(claim, claim.removeprefix("CLAIM-").replace("-", " ").title()),
            "status": (
                "CONTRADICTED_OR_CAPPED" if contradicted_by[claim]
                else "SUPPORTED_WITH_STATED_SCOPE" if supported_by[claim]
                else "EXAMINED_WITH_NEGATIVE_EVIDENCE_ONLY"
            ),
            "supported_by_evidence_ids": sorted(set(supported_by[claim])),
            "contradicted_by_evidence_ids": sorted(set(contradicted_by[claim])),
            "scope_limit": "Claim semantics are bounded by the cited evidence records and their contamination; identifier existence is not proof.",
        }
        for claim in sorted(referenced)
    ]


FRONTIER_CURRENT_EVIDENCE: dict[str, list[str]] = {
    "FR-P00-001": ["EV-SOURCE-CENSUS"],
    "FR-P00-003": ["EV-DECISION-STATIC", "EV-SUPERSESSION-REGISTRY"],
    "FR-P00-004": ["EV-DECISION-STATIC", "EV-F26-CR001"],
    "FR-P00-005": ["EV-DECISION-STATIC"],
    "FR-P00-006": ["EV-REALITY-SEALED", "EV-DOCS-AUDITOR-CURRENT"],
    "FR-P01-001": ["EV-COMPONENT-STATIC", "EV-MCP-DUAL-AUTHORITY"],
    "FR-P01-003": ["EV-API-MUTATION-CODE"],
    "FR-P01-005": ["EV-COMPONENT-STATIC", "EV-DECISION-STATIC"],
    "FR-P02-001": ["EV-GRAPH-QUERIES"],
    "FR-P02-004": ["EV-GRAPH-QUERIES"],
    "FR-P03-001": ["EV-COMPONENT-STATIC", "EV-GRAPH-QUERIES"],
    "FR-P03-002": ["EV-COMPONENT-STATIC"],
    "FR-P03-003": ["EV-REALITY-SEALED"],
    "FR-P03-005": ["EV-COMPONENT-STATIC", "EV-GRAPH-QUERIES"],
    "FR-P03-006": ["EV-COMPONENT-STATIC"],
    "FR-P04-001": ["EV-MEMORY-AUTHORITY-CODE", "EV-COMPONENT-STATIC"],
    "FR-P04-002": ["EV-MEMORY-AUTHORITY-CODE"],
    "FR-P04-011": ["EV-DECISION-STATIC", "EV-MEMORY-AUTHORITY-CODE"],
    "FR-P05-001": ["EV-COMPONENT-STATIC"],
    "FR-P06-001": ["EV-COMPONENT-STATIC", "EV-REALITY-SEALED"],
    "FR-P06-002": ["EV-COMPONENT-STATIC", "EV-REALITY-SEALED"],
    "FR-P06-005": ["EV-F26-CR001"],
    "FR-P07-007": ["EV-SECRETS-BOUNDARY-CODE"],
    "FR-P07-008": ["EV-MCP-DUAL-AUTHORITY", "EV-SEMGREP-CR001-CANDIDATES"],
    "FR-P07-009": ["EV-MCP-DUAL-AUTHORITY"],
    "FR-P08-001": ["EV-API-MUTATION-CODE", "EV-DECISION-STATIC"],
    "FR-P08-002": ["EV-DECISION-STATIC"],
    "FR-P09-001": ["EV-REALITY-SEALED", "EV-COMPONENT-STATIC"],
    "FR-P09-005": ["EV-COMPONENT-STATIC", "EV-F26-CR001"],
    "FR-P09-006": ["EV-SEMGREP-CR001-CANDIDATES", "EV-F26-CR001"],
    "FR-P09-011": ["EV-REALITY-SEALED", "EV-GRAPH-QUERIES"],
    "FR-P10-001": ["EV-REALITY-SEALED", "EV-COMPONENT-STATIC"],
    "FR-P10-006": ["EV-COMPONENT-STATIC"],
    "FR-P12-002": ["EV-SECRETS-BOUNDARY-CODE"],
    "FR-P12-006": ["EV-COMPONENT-STATIC"],
    "FR-P12-007": ["EV-REALITY-SEALED"],
}


def extract_repo_locator(ref: str) -> str | None:
    for marker in (":docs/", ":src/", ":tests/", ":scripts/", ":work/", ":config/"):
        if marker in ref:
            return marker[1:] + ref.rsplit(marker, 1)[1]
    if ref.startswith("GH:"):
        tail = ref[3:]
        if ":" in tail:
            tail = tail.rsplit(":", 1)[1]
        if (ROOT / tail).exists():
            return tail
    return None


def build_frontier_mapping(
    pack_frontiers: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    components: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    component_findings: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    rows: list[dict[str, Any]] = []
    path_frontiers: dict[str, set[str]] = defaultdict(set)
    for frontier in pack_frontiers:
        for ref in frontier.get("primary_internal_sources", []):
            path = extract_repo_locator(ref)
            if path and (ROOT / path).exists():
                path_frontiers[path].add(frontier["frontier_id"])
    for item in component_findings["component_inventory"]:
        for source_path in item["source_paths"]:
            if "*" in source_path:
                for match in ROOT.glob(source_path):
                    if match.is_file():
                        path_frontiers[str(match.relative_to(ROOT))].update(CRITICAL_FRONTIERS.get(item["component"], []))
            elif (ROOT / source_path).exists():
                path_frontiers[source_path].update(CRITICAL_FRONTIERS.get(item["component"], []))

    merge_group = ["FR-P06-010", "FR-P10-005"]
    split_frontier = "FR-P00-007"
    for frontier in pack_frontiers:
        fid = frontier["frontier_id"]
        evidence = FRONTIER_CURRENT_EVIDENCE.get(fid, [])
        if fid in merge_group:
            assessment = "MERGE_CANDIDATE"
            note = "Both hypotheses require the same shadow-history, calibration, regression-prevention, and unnecessary-change competence gate; only the maintainer scope differs. Preserve scope as a dimension unless reconciliation finds distinct owners/falsifiers."
        elif fid == split_frontier:
            assessment = "SPLIT_CANDIDATE"
            note = "This row combines context selection/compiler behavior with typed ContextPacket semantics already separated by FR-P02-002 and FR-P02-003."
        elif fid == "FR-P00-001":
            assessment = "REFORMULATE"
            note = "The current audit distinguishes sealed tracked blobs, external operator input, generated audit output, and runtime state; a single undifferentiated corpus count would be misleading."
        elif evidence:
            assessment = "NEW_EVIDENCE"
            note = "Current Atlas N evidence bears on the hypothesis but does not by itself confirm the pack's maturity, disposition, or minimum guarantee."
        else:
            assessment = "UNKNOWN"
            note = "Examined against the reconstructed registries; no sufficiently direct current evidence was found to promote or delete this pack hypothesis."
        present_refs = []
        for ref in frontier.get("primary_internal_sources", []):
            path = extract_repo_locator(ref)
            if path and (ROOT / path).exists():
                present_refs.append(path)
        rows.append({
            "record_kind": "FRONTIER_R0",
            "frontier_id": fid,
            "name": frontier["name"],
            "program": frontier["program"],
            "pack_assessment": frontier["current_assessment"],
            "pack_disposition": frontier["disposition"],
            "pack_epistemic_status": frontier["epistemic_status"],
            "assessment": assessment,
            "examined": True,
            "evidence_ids": evidence or ["EV-PACK-ZIP"],
            "referenced_current_sources_present": sorted(set(present_refs)),
            "mapping_note": note,
            "case_for": "The row remains a useful problem hypothesis; current evidence is listed explicitly where found.",
            "case_against": "The pack is not canon, repeated WORK_LEDGER/component-matrix references are not independent evidence, and no missing live reproduction was silently inferred.",
            "merge_group": "MG-001" if fid in merge_group else None,
            "split_group": "SG-001" if fid == split_frontier else None,
            "assessment_basis": "PACK_INTERNAL_ONLY_REQUIRES_INDEPENDENT_RECONCILIATION" if assessment in {"MERGE_CANDIDATE", "SPLIT_CANDIDATE"} else "CURRENT_AUDIT_AND_PACK_CROSS_MAPPING",
            "confidence": "LOW" if assessment in {"MERGE_CANDIDATE", "SPLIT_CANDIDATE", "UNKNOWN"} else ("MEDIUM" if evidence else "LOW"),
            "independence_key": "frontier-r0:" + fid,
        })

    first_copy: dict[str, str] = {}
    for source in sources:
        explicit = sorted(set(source["related_frontier_ids"]) | path_frontiers.get(source["path"], set()))
        canonical = first_copy.setdefault(source["sha256"], source["source_id"])
        if source["lifecycle"] == "SUPERSEDED":
            status, reason = "SUPERSEDED", "Source lifecycle is explicitly superseded."
        elif source["lifecycle"] in {"HISTORICAL", "ARCHIVED"}:
            status, reason = "HISTORICAL", "Historical/archive source is preserved but not current authority."
        elif not source["conceptual_entity"]:
            status, reason = "IRRELEVANT", "Fixture/generated/vendor file is covered but is not an independent frontier concept."
        elif source["content_duplicate_count"] > 1 and canonical != source["source_id"]:
            status, reason = "DUPLICATE", "Exact content duplicate; independence_key prevents corroboration inflation."
        elif explicit:
            status, reason = "MAPPED", "Direct pack source locator, explicit frontier ID, or critical-capability source mapping."
        else:
            status, reason = "UNKNOWN", "No defensible one-to-one frontier mapping; program inference alone is insufficient."
        rows.append({
            "record_kind": "SOURCE",
            "artifact_id": source["source_id"],
            "artifact_locator": source["path"],
            "mapping_status": status,
            "frontier_ids": explicit,
            "candidate_program": source["program"],
            "reason": reason,
            "confidence": "HIGH" if status != "UNKNOWN" else "LOW",
            "independence_key": source["independence_key"],
        })

    for component in components:
        frontier_ids = component["related_frontier_ids"]
        rows.append({
            "record_kind": "COMPONENT",
            "artifact_id": component["component_id"],
            "artifact_locator": component["name"],
            "mapping_status": "MAPPED" if frontier_ids else "UNKNOWN",
            "frontier_ids": frontier_ids,
            "candidate_program": component["program"],
            "reason": "Critical-capability mapping with current source evidence." if frontier_ids else "Module classified, but program proximity alone does not justify an exact R0 frontier.",
            "confidence": "HIGH" if frontier_ids else "LOW",
            "independence_key": component["independence_key"],
        })

    pack_text = {f["frontier_id"]: json.dumps(f, ensure_ascii=False) for f in pack_frontiers}
    for decision in decisions:
        did = decision["decision_id"]
        matches = sorted(fid for fid, text in pack_text.items() if did in text)
        if decision.get("semantic_duplicate_of"):
            status, reason = "DUPLICATE", "Semantic companion/alias of the same decision subject; it does not add independent decision evidence."
        elif decision["status"] == "HISTORICAL":
            status, reason = "HISTORICAL", "Recovered historical decision; preserved without current promotion."
        elif decision["status"] == "SUPERSEDED":
            status, reason = "SUPERSEDED", "Decision has explicit supersession status."
        elif matches:
            status, reason = "MAPPED", "Decision ID occurs in the R0 frontier hypothesis record."
        else:
            status, reason = "UNKNOWN", "No direct frontier reference; program association alone is insufficient."
        rows.append({
            "record_kind": "DECISION",
            "artifact_id": did,
            "artifact_locator": decision["locators"],
            "mapping_status": status,
            "frontier_ids": matches,
            "candidate_program": decision["program"],
            "reason": reason,
            "confidence": "HIGH" if status in {"HISTORICAL", "SUPERSEDED"} else ("MEDIUM" if matches else "LOW"),
            "independence_key": decision["independence_key"],
        })
    return rows, path_frontiers


def source_summary_markdown(sources: list[dict[str, Any]]) -> str:
    categories = Counter(r["category"] for r in sources)
    lifecycles = Counter(r["lifecycle"] for r in sources)
    programs = Counter(r["program"] for r in sources)
    duplicate_files = sum(1 for r in sources if r["content_duplicate_count"] > 1)
    nonconceptual = sum(1 for r in sources if not r["conceptual_entity"])
    third_party = sum(1 for r in sources if r["third_party_or_vendor"])
    lines = [
        "# FR-000 source classification summary",
        "",
        f"Sealed denominator: **{len(sources):,} tracked Git blobs** at `{EXPECTED_TREE}`. Every blob has a path identity, SHA-256, Git blob SHA, category, lifecycle, relevance, ownership inference, and independence key.",
        "",
        "The registry is exhaustive at file level, while `conceptual_entity=false` prevents fixtures, generated files, and third-party payloads from becoming thousands of independent capability claims.",
        "",
        "## Categories",
        "",
        "| Category | Files |",
        "| --- | ---: |",
        *[f"| {key} | {categories[key]} |" for key in sorted(categories)],
        "",
        "## Lifecycle",
        "",
        "| Lifecycle | Files |",
        "| --- | ---: |",
        *[f"| {key} | {lifecycles[key]} |" for key in sorted(lifecycles)],
        "",
        "## Deduplication and ownership",
        "",
        f"- Files participating in an exact-content duplicate group: {duplicate_files}.",
        f"- Non-conceptual fixture/generated/vendor rows: {nonconceptual}.",
        f"- Explicit third-party/vendor rows: {third_party} (the graveyard contains no tracked node_modules/vendor subtree; the Gradle wrapper JAR is the known third-party binary).",
        "- `independence_key` is content-addressed. Repeated copies never increase evidence independence.",
        "",
        "## Program inference",
        "",
        "Program is a path/subsystem inference, not decision authority. `UNKNOWN` is retained instead of forcing a frontier.",
        "",
        "| Program | Files |",
        "| --- | ---: |",
        *[f"| {key} | {programs[key]} |" for key in sorted(programs)],
        "",
        "`UNCLASSIFIED_CURRENT = 0`: UNKNOWN program or frontier mapping is an explicit classification; no current source is silently absent.",
    ]
    return "\n".join(lines) + "\n"


def docs_audit_markdown(source_findings: dict[str, Any]) -> str:
    audit = source_findings["docs_index_auditor"]
    historical = load_json(ROOT / "work/checkpoints/CR-001_DOCS_INDEX_DRIFT.json")
    return f"""# Docs-index auditor audit

Verdict: **{audit['verdict']}**.

## Historical result preserved

CR-001 observed **334 missing paths = 246 graveyard + 88 non-graveyard**. That result remains historical evidence and is not rewritten. Its source artifact is `work/checkpoints/CR-001_DOCS_INDEX_DRIFT.json`.

## Current read-only reproduction

The unchanged script (`sha256:{audit['implementation_sha256']}`) returned exit 1 with **97 missing, 0 orphan, 0 expired**. Classification is exhaustive:

| Finding class | Count |
| --- | ---: |
| Ordinary current documents (`TRUE_DOCUMENT_DRIFT`) | 20 |
| Canon schema contracts | 3 |
| Fixture payloads | 65 |
| Archived code/build metadata | 9 |
| Total | 97 |

The 88 non-graveyard paths are unchanged between observations. The graveyard population changed from 246 physical-tree paths to 9 currently emitted tracked artifacts; the sealed Git tree has only 48 graveyard blobs and no tracked `node_modules` or `vendor` subtree.

## Auditor-of-auditor finding

The explicit prose contract says every document under `docs/` is indexed. The implementation instead performs a physical `rglob`, filters a small exception list, and accepts generic document-like suffixes. It has no scope contract for fixtures, schemas, archive source trees, `node_modules`, vendor, build/dist, ignored, or untracked files. Tests do not cover those families.

Therefore the gate contains both real drift (20 ordinary documents) and a scope defect (77 non-ordinary artifacts): **MIXED**, not a pure documentation failure and not a pure false positive.

`docs/INDEX.yaml` was not changed. The current result does not replace the CR-001 result because the populations differ.
"""


def semgrep_retention_markdown() -> str:
    data = load_json(ROOT / "work/checkpoints/CR-001_SEMGREP_MAJOR_FINDINGS.json")
    # The preserved artifact uses candidate rows under a versioned key; locate them defensively.
    candidates = data.get("candidates") or data.get("candidate_findings") or data.get("findings") or []
    if isinstance(candidates, dict):
        candidates = list(candidates.values())
    known = [
        ("ai.adeu/adeu", 7, "adeu.server"),
        ("com.arcself/arc-security", 4, "./bin/arc-security-mcp.js"),
        ("com.atagon/kogiqa-mcp", 4, "index.js"),
        ("com.gitkraken/gk-cli", 1, "run-gk.js"),
    ]
    lines = [
        "# Evidence-retention gaps",
        "",
        "No Semgrep scan was run in FR-000/FR-001.",
        "",
        "CR-001 preserves four candidate-level summaries covering 16 historical MAJOR finding events, but not the raw events needed for individual triage:",
        "",
        "| Candidate | Historical MAJOR count | Entrypoint | Classification |",
        "| --- | ---: | --- | --- |",
    ]
    for candidate, count, entrypoint in known:
        lines.append(f"| `{candidate}` | {count} | `{entrypoint}` | `HISTORICAL_FINDING_PRESENT`; `RAW_EVIDENCE_NOT_RETAINED`; `NOT_INDIVIDUALLY_TRIAGEABLE`; `REQUIRES_RESCAN_WITH_RAW_RETENTION` |")
    lines.extend([
        "",
        "Missing per-event fields are `rule_id`, `path`, `line`, `fingerprint`, and raw scanner output. The candidate summary itself is retained and hashable; the original scanner evidence is not.",
        "",
        "A future scan cannot silently substitute for the lost historical result. It must be recorded as a new observation with raw retention, while these CR-001 gaps remain historical.",
    ])
    return "\n".join(lines) + "\n"


def build_coverage(
    sources: list[dict[str, Any]],
    components: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    mapping: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    unknowns: list[dict[str, Any]],
    new_frontiers: list[dict[str, Any]],
    authority: list[dict[str, Any]],
    decision_graph: list[dict[str, Any]],
    fit_assessments: list[dict[str, Any]],
) -> dict[str, Any]:
    current_sources = [r for r in sources if r["lifecycle"] == "CURRENT"]
    current_components = [r for r in components if r["current"]]
    current_decision_records = [r for r in decisions if r["current"]]
    decision_subjects: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decisions:
        decision_subjects[row["decision_subject_key"]].append(row)
    for subject_key, subject_rows in decision_subjects.items():
        statuses = {row["status"] for row in subject_rows}
        if len(statuses) != 1:
            raise RuntimeError(f"semantic decision subject has conflicting statuses: {subject_key}: {sorted(statuses)}")
    unique_decisions = [subject_rows[0] for subject_rows in decision_subjects.values()]
    current_decisions = [
        subject_rows[0] for subject_rows in decision_subjects.values()
        if any(row["current"] for row in subject_rows)
    ]
    frontier_rows = [r for r in mapping if r["record_kind"] == "FRONTIER_R0"]
    merge_groups = {r["merge_group"] for r in frontier_rows if r.get("merge_group")}
    split_groups = {r["split_group"] for r in frontier_rows if r.get("split_group")}
    current_sources_classified = sum(r["category"] in CATEGORIES and r["lifecycle"] in LIFECYCLES for r in current_sources)
    components_classified = sum(r["maturity"] in MATURITIES for r in current_components)
    current_decisions_classified = sum(r["status"] in DECISION_STATUSES for r in current_decisions)
    examined = sum(bool(r["examined"]) and r["assessment"] in FRONTIER_ASSESSMENTS for r in frontier_rows)
    unclassified = (
        len(current_sources) - current_sources_classified
        + len(current_components) - components_classified
        + len(current_decisions) - current_decisions_classified
        + len(frontier_rows) - examined
    )

    def ratio(numerator: int, denominator: int) -> dict[str, Any]:
        value = numerator / denominator if denominator else 1.0
        return {"numerator": numerator, "denominator": denominator, "ratio": round(value, 8), "percent": round(value * 100, 4)}

    mapping_rows = {
        kind: [row for row in mapping if row["record_kind"] == kind]
        for kind in ("SOURCE", "COMPONENT", "DECISION", "FRONTIER_R0")
    }
    unknown_dimensions = {
        "semantic_unknown_registry": len(unknowns),
        "source_lifecycle_unknown": sum(row["lifecycle"] == "UNKNOWN" for row in sources),
        "source_program_unknown": sum(row["program"] == "UNKNOWN" for row in sources),
        "source_frontier_mapping_unknown": sum(row.get("mapping_status") == "UNKNOWN" for row in mapping_rows["SOURCE"]),
        "component_maturity_unknown": sum(row["maturity"] == "UNKNOWN" for row in components),
        "component_program_unknown": sum(row["program"] == "UNKNOWN" for row in components),
        "component_frontier_mapping_unknown": sum(row.get("mapping_status") == "UNKNOWN" for row in mapping_rows["COMPONENT"]),
        "decision_status_unknown": sum(row["status"] == "UNKNOWN" for row in decisions),
        "decision_program_unknown": sum(row["program"] == "UNKNOWN" for row in decisions),
        "decision_frontier_mapping_unknown": sum(row.get("mapping_status") == "UNKNOWN" for row in mapping_rows["DECISION"]),
        "frontier_assessment_unknown": sum(row["assessment"] == "UNKNOWN" for row in frontier_rows),
    }
    mapping_resolution = {
        key: ratio(sum(row.get("mapping_status", row.get("assessment")) != "UNKNOWN" for row in rows), len(rows))
        for key, rows in mapping_rows.items()
    }
    current_contradictions = [row for row in contradictions if row["origin"] != "FRONTIER_PACK"]
    expected_fit_subjects = {
        *("CALLER_WRITER_ANOMALY:" + row["anomaly_id"] for row in build_anomalies(load_json(PHASE / "component_authority_findings.json"))),
        *("CURRENT_CONTRADICTION:" + row["contradiction_id"] for row in current_contradictions),
    }
    observed_fit_subjects = {row["subject_kind"] + ":" + row["subject_id"] for row in fit_assessments}
    relation_pair_count = sum(len(row["from_ids"]) * len(row["to_ids"]) for row in decision_graph if row["source"] == "docs/canon/supersession_registry.jsonl")
    stop_conditions = {
        "source_universe_censused": bool(sources) and current_sources_classified == len(current_sources),
        "current_components_classified": len(components) == 471 and components_classified == len(components),
        "current_decisions_classified": (
            len(current_decision_records) == 134
            and len(current_decisions) == 126
            and current_decisions_classified == len(current_decisions)
            and sum(row["status"] in DECISION_STATUSES for row in current_decision_records) == len(current_decision_records)
        ),
        "supersession_graph_exists": len(decision_graph) >= 15 and relation_pair_count == 18,
        "critical_authority_callers_mapped": Counter(row["record_kind"] for row in authority) == {"COMPONENT_AUTHORITY": 20, "STATE_DOMAIN_AUTHORITY": 11},
        "frontier_r0_cross_mapped": len(frontier_rows) == 109 and examined == 109,
        "contradictions_preserved": bool(contradictions),
        "unknowns_preserved": bool(unknowns),
        "coverage_calculated": True,
        "all_current_classified_or_explicit_unknown": unclassified == 0,
        "candidate_frontier_fit_assessed": expected_fit_subjects == observed_fit_subjects,
    }
    result = {
        "baseline": {"tag": EXPECTED_TAG, "commit": EXPECTED_COMMIT, "tree": EXPECTED_TREE},
        "denominator_definitions": {
            "source_universe": "Every tracked blob in the sealed Git tree; current_sources is the subset with lifecycle CURRENT.",
            "components": "471 reproducible current code-bearing implementation units: 329 ordinary Python modules, 16 substantive package initializers, 8 Jinja templates, 93 current tooling programs/hooks, 11 Mission Console product units, and 14 prototype units. Semantic capabilities remain separate authority overlays.",
            "decisions": "276 classified records collapse to 268 independent decision subjects through decision_subject_key. Current authority contains 134 records, of which 8 are semantic companion aliases, yielding 126 independent current subjects: 77 canonical + 36 work orders + 13 programs. Graph endpoints are excluded from current authority.",
            "frontiers": "All 109 R0 working hypotheses from the external Frontier Pack; examined does not mean confirmed.",
        },
        "all_tracked_sources_total": len(sources),
        "all_tracked_sources_classified": sum(r["category"] in CATEGORIES and r["lifecycle"] in LIFECYCLES for r in sources),
        "current_sources_total": len(current_sources),
        "current_sources_classified": current_sources_classified,
        "current_components_total": len(current_components),
        "current_components_mapped": components_classified,
        "all_decision_records_total": len(decisions),
        "all_decision_records_classified": sum(r["status"] in DECISION_STATUSES for r in decisions),
        "all_decisions_total": len(unique_decisions),
        "all_decisions_classified": sum(r["status"] in DECISION_STATUSES for r in unique_decisions),
        "historical_decisions_total": sum(r["status"] == "HISTORICAL" for r in decisions),
        "non_current_decisions_total": sum(not r["current"] for r in decisions),
        "current_decision_denominator_partition": {
            "canonical_current_authority": sum(r["record_kind"] not in {"ADC_WORK_ORDER", "PROGRAM_DECISION", "GRAPH_ENDPOINT"} for r in current_decisions),
            "adc_work_orders": sum(r["record_kind"] == "ADC_WORK_ORDER" for r in current_decisions),
            "program_decisions": sum(r["record_kind"] == "PROGRAM_DECISION" for r in current_decisions),
            "graph_endpoints_excluded": sum(r["record_kind"] == "GRAPH_ENDPOINT" for r in decisions),
            "semantic_duplicate_records_excluded": len(current_decision_records) - len(current_decisions),
        },
        "current_decision_record_partition": {
            "canonical_current_authority_records": sum(r["record_kind"] not in {"ADC_WORK_ORDER", "PROGRAM_DECISION", "GRAPH_ENDPOINT"} for r in current_decision_records),
            "adc_work_order_records": sum(r["record_kind"] == "ADC_WORK_ORDER" for r in current_decision_records),
            "program_decision_records": sum(r["record_kind"] == "PROGRAM_DECISION" for r in current_decision_records),
        },
        "current_decision_records_total": len(current_decision_records),
        "current_decision_records_classified": sum(r["status"] in DECISION_STATUSES for r in current_decision_records),
        "current_decision_semantic_duplicates": len(current_decision_records) - len(current_decisions),
        "current_decisions_total": len(current_decisions),
        "current_decisions_classified": current_decisions_classified,
        "frontier_r0_total": len(frontier_rows),
        "frontier_r0_examined": examined,
        "candidate_new_frontiers": len(new_frontiers),
        "merge_candidate_groups": len(merge_groups),
        "merge_candidate_frontier_rows": sum(r["assessment"] == "MERGE_CANDIDATE" for r in frontier_rows),
        "split_candidate_groups": len(split_groups),
        "split_candidate_frontier_rows": sum(r["assessment"] == "SPLIT_CANDIDATE" for r in frontier_rows),
        "contradictions": len(contradictions),
        "unknowns": len(unknowns),
        "unknown_registry_records": len(unknowns),
        "unknown_classifications_by_dimension": unknown_dimensions,
        "unknown_classifications_total": sum(unknown_dimensions.values()),
        "unclassified_current": unclassified,
        "CURRENT_SOURCE_COVERAGE": ratio(current_sources_classified, len(current_sources)),
        "CURRENT_COMPONENT_COVERAGE": ratio(components_classified, len(current_components)),
        "CURRENT_DECISION_COVERAGE": ratio(current_decisions_classified, len(current_decisions)),
        "CURRENT_FRONTIER_MAPPING_COVERAGE": ratio(examined, len(frontier_rows)),
        "CRITICAL_CAPABILITY_AUTHORITY_COVERAGE": ratio(sum(row["record_kind"] == "COMPONENT_AUTHORITY" for row in authority), 20),
        "MAPPING_RESOLUTION_EXCLUDING_EXPLICIT_UNKNOWN": mapping_resolution,
        "resolution_ratios_by_dimension": mapping_resolution,
        "supersession_relation_records": len(decision_graph),
        "canonical_supersession_source_records": sum(row["source"] == "docs/canon/supersession_registry.jsonl" for row in decision_graph),
        "canonical_supersession_atomic_pairs": relation_pair_count,
        "candidate_frontier_fit_assessments": len(fit_assessments),
        "stop_conditions": stop_conditions,
        "ready_for_external_adversarial_review": all(stop_conditions.values()),
        "mapping_status_counts": dict(sorted(Counter(r.get("mapping_status", r.get("assessment")) for r in mapping).items())),
        "classification_note": "UNKNOWN is an explicit classification. Absence is not. Frontier/artifact mapping UNKNOWN does not increase unclassified_current.",
    }
    return result


def phase_footer(name: str, constraints: list[str], evidence: list[str], invalidated: list[str], unknowns: list[str], contradictions: list[str], unclassified: int) -> str:
    def block(title: str, values: list[str]) -> list[str]:
        return [f"## {title}", "", *([f"- {value}" for value in values] if values else ["- None recorded."]), ""]
    lines = [f"# {name}", ""]
    lines += block("PRESERVED_CONSTRAINTS", constraints)
    lines += block("NEW_EVIDENCE", evidence)
    lines += block("INVALIDATED_CLAIMS", invalidated)
    lines += block("NEW_UNKNOWNS", unknowns)
    lines += block("NEW_CONTRADICTIONS", contradictions)
    lines += ["## UNCLASSIFIED_COUNT", "", str(unclassified), ""]
    return "\n".join(lines)


def fr000_report(
    coverage: dict[str, Any],
    source_findings: dict[str, Any],
    component_findings: dict[str, Any],
    negative: list[dict[str, Any]],
) -> str:
    current = coverage["CURRENT_SOURCE_COVERAGE"]
    components = coverage["CURRENT_COMPONENT_COVERAGE"]
    return f"""# FR-000 report — Source universe and current reality

Status: **{'COMPLETE FOR EXTERNAL ADVERSARIAL REVIEW' if coverage['ready_for_external_adversarial_review'] else 'INCOMPLETE'}**, subject to the explicitly retained unknowns and contradictions.

## Coverage

- Sealed tracked blobs: {coverage['all_tracked_sources_total']} / {coverage['all_tracked_sources_classified']} classified.
- Current sources: {current['numerator']} / {current['denominator']} ({current['percent']}%).
- Current component units: {components['numerator']} / {components['denominator']} ({components['percent']}%).
- Critical authority overlays: {len(component_findings['component_inventory'])}; state-domain authority rows: {len(component_findings['authority_rows'])}; anomaly records: {len(build_anomalies(component_findings))} (including one original finding preserved as superseded by self-review).
- Negative-evidence records: {len(negative)}.
- Semantic unknown registry records: {coverage['unknown_registry_records']}; explicit UNKNOWN dimensions: {coverage['unknown_classifications_total']}.
- Unclassified current: {coverage['unclassified_current']}.

## Source-universe finding

The exhaustive denominator is the 2,344 blobs in the sealed Git tree. External ZIP input, the shared Atlas runtime workspace, local `.env`, installed skills, and generated audit output are separately classified and never inserted into the historical tree census.

The implementation-unit denominator is 471: 329 ordinary Python modules, 16 substantive package initializers, 8 Jinja templates, 93 current tooling programs/hooks, 11 Mission Console product units, and 14 prototype units. The graph's 329-module count is a narrower structural Python view. Critical semantic capabilities are separately overlaid in `04_AUTHORITY_MAP.jsonl`.

## Current-test result

The default configured suite passed: 6,016 passed, 13 skipped, 27 deselected. This promotes only directly located tested properties. It does not prove wiring, real providers, runtime use, reliability, or product acceptance.

## Docs-index auditor

Verdict: **MIXED**. Current missing = 97: 20 ordinary documents, 3 schemas, 65 fixtures, 9 archived artifacts. CR-001's historical 334 = 246 + 88 is preserved, not rewritten. `docs/INDEX.yaml` was not changed.

## Evidence retention

Four historical Semgrep candidates represent 16 MAJOR events, but event-level rule/path/line/fingerprint/raw output was not retained. They are not individually triageable. No scan was run.

## Maturity boundary

No component was promoted to `PRODUCT_ACCEPTED`. Live observations are explicitly scope-limited and contaminated by environment-bound runtime state where applicable.

## Phase state

PRESERVED_CONSTRAINTS: sealed identity, authority order, pack non-canonicity, F2.6 non-execution, Semgrep non-execution, no implementation.

NEW_EVIDENCE: exhaustive hashes and classifications, fresh structural graph, passing default suite, current docs-auditor decomposition, 471-unit implementation census, and critical caller/writer reconstruction.

INVALIDATED_CLAIMS: the historical 246 graveyard count is not a current sealed-tree population; universal Merkle coverage, global secret non-observability, and test-to-live promotion are not demonstrated.

NEW_UNKNOWNS: live provider inference, current daemon code identity, Mission scheduling, real Hermes adapter selection, deselected computer-use behavior.

NEW_CONTRADICTIONS: docs-auditor scope, split audit authorities, dual MCP authority, scoped secrets claim, environment-bound reality, and Code OSS lineage/work-order drift.

UNCLASSIFIED_COUNT: {coverage['unclassified_current']}.
"""


def fr001_report(
    coverage: dict[str, Any], decision_findings: dict[str, Any], mapping: list[dict[str, Any]]
) -> str:
    decisions = coverage["CURRENT_DECISION_COVERAGE"]
    frontier = coverage["CURRENT_FRONTIER_MAPPING_COVERAGE"]
    fr_rows = [r for r in mapping if r["record_kind"] == "FRONTIER_R0"]
    statuses = Counter(r["assessment"] for r in fr_rows)
    status_text = ", ".join(f"{key}={value}" for key, value in sorted(statuses.items()))
    return f"""# FR-001 report — Decisions, supersession and R0 mapping

Status: **{'COMPLETE FOR EXTERNAL ADVERSARIAL REVIEW' if coverage['ready_for_external_adversarial_review'] else 'INCOMPLETE'}**, not operator approval of any decision or frontier taxonomy.

## Decision coverage

- All decision records: {coverage['all_decision_records_classified']} / {coverage['all_decision_records_total']} classified; independent decision subjects: {coverage['all_decisions_classified']} / {coverage['all_decisions_total']}.
- Current decision records: {coverage['current_decision_records_classified']} / {coverage['current_decision_records_total']} classified; 8 semantic companion records are deduplicated.
- Independent current decision subjects: {decisions['numerator']} / {decisions['denominator']} ({decisions['percent']}%).
- Historical decision records: {coverage['historical_decisions_total']}.
- Explicit graph records: {coverage['supersession_relation_records']}; canonical source records: {coverage['canonical_supersession_source_records']}; canonical atomic endpoint pairs: {coverage['canonical_supersession_atomic_pairs']}; chronology-derived edges: 0.

The current-authority record population is 134: 85 canonical rows, 36 ADC work orders, and 13 program rows. Eight canonical companion rows share an independence key with their atomic ADR subject, so coverage uses 126 independent subjects: 77 canonical + 36 work orders + 13 programs. Referential graph endpoints are excluded. Historical recovered decisions remain `HISTORICAL`.

## Required focused revalidation

- `ADC-WO-107`: **CONTRADICTED / REQUIRES_OPERATOR** remains supported. Mission approve/reject POST handlers mutate ColdUpdate outside ADR-080's scoped Product OS exception.
- `ADR-057`: **PROVISIONAL** evidence qualification; no automatic promoter is established.
- `ADR-058`: **PROVISIONAL** with an active scope breach; ADR-080 supersedes only the named Product OS scope.
- `ADR-069`: **PROVISIONAL**; v0 code/tests do not establish the proposed durable effect journal.
- `ADR-078`: **PROVISIONAL** accepted design, not a completed Workbench product.

`ADC-WO-124` is additionally `CONTRADICTED` at document-reality level. `ADC-WO-109` is also `CONTRADICTED`: the clean external checkout is 1.132.0/f7c27192 while tracked lineage remains 1.129.1/8a7abeba, and the work-order row contains mutually incompatible state claims. No build/runtime receipt was rerun.

## R0 cross-mapping

- Examined: {frontier['numerator']} / {frontier['denominator']} ({frontier['percent']}%).
- Assessment counts: {status_text}.
- Merge candidate group: `FR-P06-010` + `FR-P10-005` (one group, two frontier rows).
- Split candidate: `FR-P00-007`, because it combines the compiler/selection concern and typed ContextPacket concern already separated in `FR-P02-002`/`FR-P02-003`.
- Candidate new frontiers: {coverage['candidate_new_frontiers']}. Every anomaly and current contradiction has a durable fit assessment; zero is derived, not initialized. Existing mappings do not resolve the problems.

## F2.6 preservation

`execution_outcome=FAIL`, `automatic_grade=1/6`, `measurement_validity=INCONCLUSIVE`. Execution result and measurement validity remain separate. F2.6 was not run.

## Phase state

PRESERVED_CONSTRAINTS: no decision resolution, no date-only supersession, pack remains non-canon, historical claims retain their source qualification.

NEW_EVIDENCE: explicit decision edges, code/decision mismatch at port 7341, documentary conflict at ADC-WO-124, current Code OSS identity conflict at ADC-WO-109, exhaustive R0 examination.

INVALIDATED_CLAIMS: DONE/ACCEPTED is not automatically implementation, wiring, runtime, or product evidence; port 7341 is not uniformly read-only in sealed code.

NEW_UNKNOWNS: current production clients of mutating routes, route identity/idempotency/recovery, live desktop admission, unrun provisional falsifiers.

NEW_CONTRADICTIONS: ADC-WO-107, ADC-WO-109, ADC-WO-124, F2.6 execution versus measurement interpretation.

UNCLASSIFIED_COUNT: {coverage['unclassified_current']}.
"""


def handoff_markdown(coverage: dict[str, Any], required_files: list[str]) -> str:
    return f"""# Handoff to frontier reconciliation

Atlas N identity is verified at `{EXPECTED_COMMIT}` / `{EXPECTED_TREE}`. The output is an audit layer only; the checkpoint and Atlas functional code are unchanged.

## Start here

1. Read `20_COVERAGE_REPORT.json` for denominators.
2. Read `10_CONTRADICTIONS.jsonl`, `11_NEGATIVE_EVIDENCE.jsonl`, and `13_UNKNOWNS.jsonl` before interpreting positive claims.
3. Use `12_EVIDENCE_REGISTRY.jsonl` to inspect source quality and contamination.
4. Use `03_CURRENT_COMPONENT_MAP.jsonl` for the exhaustive 471-unit implementation census and `04_AUTHORITY_MAP.jsonl` for critical semantic capability boundaries.
5. Use `06_SUPERSESSION_GRAPH.jsonl` and `07_DECISION_REALITY_MAP.jsonl` together; an edge never implies implementation.
6. Treat `08_FRONTIER_MAPPING.jsonl` R0 rows as cross-mapping of hypotheses, not approved taxonomy.

## Counts

- Current sources classified: {coverage['current_sources_classified']} / {coverage['current_sources_total']}.
- Current component units classified: {coverage['current_components_mapped']} / {coverage['current_components_total']}.
- Independent current decision subjects classified: {coverage['current_decisions_classified']} / {coverage['current_decisions_total']} ({coverage['current_decision_records_classified']} / {coverage['current_decision_records_total']} records before semantic deduplication).
- R0 frontiers examined: {coverage['frontier_r0_examined']} / {coverage['frontier_r0_total']}.
- Contradictions: {coverage['contradictions']}; semantic unknown registry records: {coverage['unknown_registry_records']}; explicit UNKNOWN dimensions: {coverage['unknown_classifications_total']}; unclassified current: {coverage['unclassified_current']}.

## Non-actions

No feature, bug fix, refactor, migration, dependency adoption inside Atlas, docs-index repair, Semgrep rescan, F2.6 run, PR, or tag was performed. At artifact generation time nothing was staged or committed; the operator later explicitly authorized publication of this audit-only directory.

## Commit candidates

Only files beneath `work/frontier_reconciliation/fr000_fr001/` are candidates, after external review. Use explicit paths if authorization is later given; never `git add .`, `git add -A`, or `git add --all`.

Required artifact set ({len(required_files)} files): {', '.join(required_files)}.
"""


def write_schema() -> None:
    from schema_contracts import SCHEMA_CONTRACTS

    schema_dir = OUT / "schemas"
    schema_dir.mkdir(exist_ok=True)
    catalog: dict[str, str] = {}
    for artifact_name, schema in sorted(SCHEMA_CONTRACTS.items()):
        schema_name = artifact_name.replace(".jsonl", "").replace(".json", "") + ".schema.json"
        write_json(schema_dir / schema_name, schema)
        catalog[artifact_name] = schema_name
    envelope = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Atlas FR-000/FR-001 schema catalog",
        "description": "Artifact-to-static-schema routing. Contracts are authored independently in schema_contracts.py.",
        "type": "object",
        "properties": {name: {"const": target} for name, target in catalog.items()},
        "required": sorted(catalog),
        "additionalProperties": True,
    }
    write_json(schema_dir / "audit_record.schema.json", envelope)
    write_json(schema_dir / "schema_catalog.json", catalog)


REQUIRED_FILES = [
    "00_EXECUTION_MANIFEST.json",
    "01_SOURCE_COVERAGE_REGISTRY.jsonl",
    "02_SOURCE_CLASSIFICATION_SUMMARY.md",
    "03_CURRENT_COMPONENT_MAP.jsonl",
    "04_AUTHORITY_MAP.jsonl",
    "05_CALLER_WRITER_ANOMALIES.jsonl",
    "06_SUPERSESSION_GRAPH.jsonl",
    "07_DECISION_REALITY_MAP.jsonl",
    "08_FRONTIER_MAPPING.jsonl",
    "09_CANDIDATE_NEW_FRONTIERS.jsonl",
    "10_CONTRADICTIONS.jsonl",
    "11_NEGATIVE_EVIDENCE.jsonl",
    "12_EVIDENCE_REGISTRY.jsonl",
    "13_UNKNOWNS.jsonl",
    "14_UNCLASSIFIED.jsonl",
    "15_DOCS_INDEX_AUDITOR_AUDIT.md",
    "16_EVIDENCE_RETENTION_GAPS.md",
    "17_FR000_REPORT.md",
    "18_FR001_REPORT.md",
    "19_HANDOFF_TO_RECONCILIATION.md",
    "20_COVERAGE_REPORT.json",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--pack-zip", type=Path, required=True)
    args = parser.parse_args()
    pack_root = args.pack_root.resolve()
    pack_zip = args.pack_zip.resolve()
    if run("git", "rev-parse", "HEAD") != EXPECTED_COMMIT:
        raise SystemExit("CHECKPOINT_IDENTITY_MISMATCH: HEAD")
    if run("git", "rev-parse", "HEAD^{tree}") != EXPECTED_TREE:
        raise SystemExit("CHECKPOINT_IDENTITY_MISMATCH: TREE")
    if sha256_file(pack_zip) != PACK_SHA256:
        raise SystemExit("operator pack SHA-256 mismatch")

    source_findings = load_json(PHASE / "source_docs_findings.json")
    component_findings = load_json(PHASE / "component_authority_findings.json")
    decision_findings = load_json(PHASE / "decision_findings.json")
    test_result = load_json(PHASE / "test_results.json")
    pack_frontiers = load_jsonl(pack_root / "inventory/frontier_inventory.jsonl")
    pack_contradictions = load_jsonl(pack_root / "inventory/contradictions.jsonl")
    pack_unknowns = load_jsonl(pack_root / "inventory/unknowns.jsonl")

    write_self_review_records()
    sources = git_tree_rows()
    components = build_components(sources, component_findings, test_result)
    authority = build_authority(component_findings)
    anomalies = build_anomalies(component_findings)
    decisions, decision_graph = build_decisions(decision_findings)
    evidence = build_evidence(pack_zip)
    unknowns = build_unknowns(pack_unknowns, source_findings, component_findings, decision_findings)
    contradictions = build_contradictions(pack_contradictions, source_findings, component_findings, decision_findings)
    negative = build_negative_evidence(component_findings, decision_findings)
    claims = build_claim_registry(evidence, negative, decisions)
    mapping, _ = build_frontier_mapping(pack_frontiers, sources, components, decisions, component_findings)
    fit_assessments, candidate_new_frontiers = build_candidate_frontier_fit(anomalies, contradictions)
    unclassified: list[dict[str, Any]] = []
    coverage = build_coverage(
        sources, components, decisions, mapping, contradictions, unknowns,
        candidate_new_frontiers, authority, decision_graph, fit_assessments,
    )

    write_jsonl(OUT / "01_SOURCE_COVERAGE_REGISTRY.jsonl", sources)
    (OUT / "02_SOURCE_CLASSIFICATION_SUMMARY.md").write_text(source_summary_markdown(sources), encoding="utf-8")
    write_jsonl(OUT / "03_CURRENT_COMPONENT_MAP.jsonl", components)
    write_jsonl(OUT / "04_AUTHORITY_MAP.jsonl", authority)
    write_jsonl(OUT / "05_CALLER_WRITER_ANOMALIES.jsonl", anomalies)
    write_jsonl(OUT / "06_SUPERSESSION_GRAPH.jsonl", decision_graph)
    write_jsonl(OUT / "07_DECISION_REALITY_MAP.jsonl", decisions)
    write_jsonl(OUT / "08_FRONTIER_MAPPING.jsonl", mapping)
    write_jsonl(OUT / "09_CANDIDATE_NEW_FRONTIERS.jsonl", candidate_new_frontiers)
    write_jsonl(PHASE / "candidate_new_frontier_fit_assessment.jsonl", fit_assessments)
    write_jsonl(OUT / "10_CONTRADICTIONS.jsonl", contradictions)
    write_jsonl(OUT / "11_NEGATIVE_EVIDENCE.jsonl", negative)
    write_jsonl(OUT / "12_EVIDENCE_REGISTRY.jsonl", evidence)
    write_jsonl(OUT / "13_UNKNOWNS.jsonl", unknowns)
    write_jsonl(OUT / "14_UNCLASSIFIED.jsonl", unclassified)
    write_jsonl(PHASE / "claim_registry.jsonl", claims)
    (OUT / "15_DOCS_INDEX_AUDITOR_AUDIT.md").write_text(docs_audit_markdown(source_findings), encoding="utf-8")
    (OUT / "16_EVIDENCE_RETENTION_GAPS.md").write_text(semgrep_retention_markdown(), encoding="utf-8")
    (OUT / "17_FR000_REPORT.md").write_text(fr000_report(coverage, source_findings, component_findings, negative), encoding="utf-8")
    (OUT / "18_FR001_REPORT.md").write_text(fr001_report(coverage, decision_findings, mapping), encoding="utf-8")
    (OUT / "19_HANDOFF_TO_RECONCILIATION.md").write_text(handoff_markdown(coverage, REQUIRED_FILES), encoding="utf-8")
    write_json(OUT / "20_COVERAGE_REPORT.json", coverage)
    write_schema()

    current_time = datetime.now(timezone.utc).isoformat()
    manifest = {
        "execution_id": "FR-000-FR-001-ATLAS-N-20260821",
        "generated_at": current_time,
        "status": "READY_FOR_EXTERNAL_ADVERSARIAL_REVIEW" if coverage["ready_for_external_adversarial_review"] else "INCOMPLETE",
        "baseline": {
            "version": EXPECTED_VERSION,
            "checkpoint": "CR-001",
            "tag": EXPECTED_TAG,
            "tag_object": "c5652f6317cc8ad71033edad876fe4da40d7a3ce",
            "peeled_commit": EXPECTED_COMMIT,
            "tree": EXPECTED_TREE,
            "identity_verified": True,
            "tag_semantics_note": "git rev-parse <tag> returns the annotated tag object; <tag>^{commit} is the required baseline commit.",
        },
        "state_categories": {
            "TRACKED_ATLAS_N": {"tree": EXPECTED_TREE, "tracked_blob_count": len(sources)},
            "OPERATOR_INPUT": {"path": str(pack_zip), "sha256": PACK_SHA256, "committed": False, "canon": False},
            "GENERATED_AUDIT_OUTPUT": {"path": str(OUT.relative_to(ROOT)), "tracked_at_generation": False, "authorized_scope_only": True, "later_publication_authorized": True},
            "UNRELATED_LOCAL_STATE": {
                "original_checkout": "/home/ronin/proyectos/atlas-core",
                "shared_runtime_workspace": "/home/ronin/atlas",
                "local_env_file": "/home/ronin/proyectos/atlas-core/.env",
                "classification": "outside sealed Git tree; used only for scope-labelled runtime observation",
            },
        },
        "skill_installation": {
            "source": "https://github.com/addyosmani/agent-skills",
            "source_commit": "df1edb2e05487d0aa6d93c747141e0aed1187f25",
            "installed_count": 24,
            "destination": "/home/ronin/.codex/skills",
            "atlas_dependency_adopted": False,
            "hooks_or_plugins_installed": False,
        },
        "graph": {
            "status": "FRESH",
            "commit": EXPECTED_COMMIT,
            "modules_latest": 329,
            "bitemporal_nodes": 3290,
            "import_edges": 8855,
            "raw_queries": "phase_records/graph_first_queries.json",
            "limit": "structural edges are not behavioral calls",
        },
        "tests": test_result,
        "f26": {
            "execution_outcome": "FAIL",
            "automatic_grade": "1/6",
            "measurement_validity": "INCONCLUSIVE",
            "rerun_in_this_audit": False,
            "notification_surface": "required spawn_task capability was not exposed; trunk invocation rejected unknown tool",
        },
        "semgrep": {
            "rescanned": False,
            "classification": [
                "HISTORICAL_FINDING_PRESENT",
                "RAW_EVIDENCE_NOT_RETAINED",
                "NOT_INDIVIDUALLY_TRIAGEABLE",
                "REQUIRES_RESCAN_WITH_RAW_RETENTION",
            ],
        },
        "required_files": REQUIRED_FILES,
        "phase_records": sorted(str(path.relative_to(OUT)) for path in PHASE.iterdir() if path.is_file()),
        "coverage_report": coverage,
        "functional_code_modified": False,
        "docs_index_modified": False,
        "commit_created": False,
        "staged": False,
        "prohibited_actions_performed": [],
        "PRESERVED_CONSTRAINTS": [
            "Checkpoint identity and history remain immutable.",
            "Evidence authority order applied; pack remains hypothesis input.",
            "F2.6 and Semgrep were not rerun.",
            "UNKNOWN classifications were not narratively promoted.",
        ],
        "NEW_EVIDENCE": [
            "Exhaustive 2,344-blob source census and 471-unit implementation census.",
            "Fresh sealed-commit graph and 6,016-passing default test selection.",
            "Explicit decision/supersession and critical authority reconstructions.",
        ],
        "INVALIDATED_CLAIMS": source_findings["INVALIDATED_CLAIMS"] + decision_findings["INVALIDATED_CLAIMS"],
        "NEW_UNKNOWNS": len(unknowns),
        "NEW_CONTRADICTIONS": len(contradictions),
        "UNCLASSIFIED_COUNT": coverage["unclassified_current"],
    }
    write_json(OUT / "00_EXECUTION_MANIFEST.json", manifest)


if __name__ == "__main__":
    main()
