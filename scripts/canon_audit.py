#!/usr/bin/env python3
"""Validate Atlas canonical governance without deciding semantic truth."""
from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parent.parent
CANON = ROOT / "docs" / "canon"
REQUIRED = (
    "ATLAS_CANON.yaml", "ATLAS_CLAIMS.yaml", "ATLAS_PRECEDENCE.yaml",
    "ATLAS_AUTHORITY_LEDGER.yaml", "ATLAS_COMPONENT_REGISTRY.yaml",
    "ATLAS_SOURCE_LEDGER.yaml", "ATLAS_CONFLICT_REGISTER.yaml",
    "ATLAS_DECISION_QUEUE.yaml", "ATLAS_ROADMAP.yaml",
    "ATLAS_TRACEABILITY.yaml", "ATLAS_GLOSSARY.yaml", "ATLAS_COVERAGE.yaml",
)


def load(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return raw


def duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set(); dup: set[str] = set()
    for value in values:
        if value in seen: dup.add(value)
        seen.add(value)
    return sorted(dup)


def dependency_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set(); visited: set[str] = set(); stack: list[str] = []
    def visit(node: str) -> list[str] | None:
        if node in visited: return None
        if node in visiting:
            i = stack.index(node); return stack[i:] + [node]
        visiting.add(node); stack.append(node)
        for dep in graph.get(node, []):
            result = visit(dep)
            if result: return result
        stack.pop(); visiting.remove(node); visited.add(node)
        return None
    for node in graph:
        result = visit(node)
        if result: return result
    return None


def path_matches(root: Path, locator: str) -> bool:
    if locator.startswith("external:"):
        return True
    return any(p.is_file() for p in root.glob(locator))


def validate(root: Path | None = None) -> dict[str, list[str]]:
    root = root or ROOT
    canon_dir = root / "docs" / "canon"
    errors: list[str] = []; warnings: list[str] = []
    if not (root / "ATLAS.md").is_file(): errors.append("missing ATLAS.md")
    for name in REQUIRED:
        if not (canon_dir / name).is_file(): errors.append(f"missing docs/canon/{name}")
    if errors: return {"errors": errors, "warnings": warnings}

    docs = {name: load(canon_dir / name) for name in REQUIRED}
    claims = docs["ATLAS_CLAIMS.yaml"].get("claims") or []
    sources = docs["ATLAS_SOURCE_LEDGER.yaml"].get("sources") or []
    states = docs["ATLAS_AUTHORITY_LEDGER.yaml"].get("states") or []
    components = docs["ATLAS_COMPONENT_REGISTRY.yaml"].get("components") or []
    phases = docs["ATLAS_ROADMAP.yaml"].get("phases") or []
    traces = docs["ATLAS_TRACEABILITY.yaml"].get("items") or []
    conflicts = docs["ATLAS_CONFLICT_REGISTER.yaml"].get("conflicts") or []
    glossary = docs["ATLAS_GLOSSARY.yaml"].get("terms") or []

    claim_ids = [str(x.get("id")) for x in claims if isinstance(x, dict)]
    source_ids = [str(x.get("id")) for x in sources if isinstance(x, dict)]
    state_ids = [str(x.get("id")) for x in states if isinstance(x, dict)]
    component_ids = [str(x.get("id")) for x in components if isinstance(x, dict)]
    phase_ids = [str(x.get("id")) for x in phases if isinstance(x, dict)]
    for label, values in (("claim",claim_ids),("source",source_ids),("authority state",state_ids),("component",component_ids),("phase",phase_ids)):
        for duplicate in duplicates(values): errors.append(f"duplicate {label} id: {duplicate}")

    allowed_claim_statuses = set(docs["ATLAS_CLAIMS.yaml"].get("allowed_statuses") or [])
    source_set = set(source_ids); claim_set = set(claim_ids); component_set = set(component_ids); phase_set = set(phase_ids)
    for index, item in enumerate(claims):
        if not isinstance(item, dict): errors.append(f"claim[{index}] is not a mapping"); continue
        cid = str(item.get("id") or "")
        if item.get("status") not in allowed_claim_statuses: errors.append(f"{cid}: invalid claim status {item.get('status')!r}")
        if not str(item.get("statement") or "").strip(): errors.append(f"{cid}: empty statement")
        for sid in item.get("sources") or []:
            if sid not in source_set: errors.append(f"{cid}: unknown source {sid}")

    for item in sources:
        sid = str(item.get("id") or "")
        absorption = item.get("semantic_absorption")
        unclassified = item.get("unclassified_claims") or []
        if absorption == "complete" and unclassified:
            errors.append(f"{sid}: complete source has unclassified claims")
        if absorption != "complete": warnings.append(f"{sid}: semantic absorption {absorption}")
        for locator in item.get("locator") or []:
            if not path_matches(root, str(locator)):
                errors.append(f"{sid}: locator matches no file: {locator}")

    targets: dict[str, str] = {}
    for item in states:
        sid = str(item.get("id") or "")
        target = str(item.get("target_authority") or "").strip()
        if not target: errors.append(f"{sid}: empty target authority")
        if sid in targets: errors.append(f"duplicate authority state id: {sid}")
        targets[sid] = target
        phase = item.get("migration_phase")
        if phase and phase not in phase_set: errors.append(f"{sid}: unknown migration phase {phase}")

    for item in components:
        cid = str(item.get("id") or "")
        phase = item.get("migration_phase")
        if phase and phase not in phase_set: errors.append(f"{cid}: unknown migration phase {phase}")
        for pattern in item.get("current_paths") or []:
            if not any(p.exists() for p in root.glob(pattern)):
                errors.append(f"{cid}: current path matches nothing: {pattern}")

    graph: dict[str, list[str]] = {}
    for item in phases:
        pid = str(item.get("id") or "")
        deps = [str(x) for x in (item.get("depends_on") or [])]
        graph[pid] = deps
        for dep in deps:
            if dep not in phase_set: errors.append(f"{pid}: unknown dependency {dep}")
    cycle = dependency_cycle(graph)
    if cycle: errors.append("roadmap dependency cycle: " + " -> ".join(cycle))

    traced = set()
    for item in traces:
        cid = str(item.get("claim") or "")
        if cid not in claim_set: errors.append(f"traceability: unknown claim {cid}")
        traced.add(cid)
        if item.get("phase") not in phase_set: errors.append(f"{cid}: unknown trace phase {item.get('phase')}")
        for comp in item.get("components") or []:
            if comp not in component_set: errors.append(f"{cid}: unknown trace component {comp}")
    for item in claims:
        if item.get("status") in {"accepted","accepted_with_changes","proposed"} and item.get("id") not in traced:
            errors.append(f"{item.get('id')}: active claim lacks traceability")

    for item in conflicts:
        for cid in item.get("claims") or []:
            if cid not in claim_set: errors.append(f"conflict {item.get('id')}: unknown claim {cid}")

    terms = [str(x.get("term")) for x in glossary if isinstance(x, dict)]
    for duplicate in duplicates([x.casefold() for x in terms]): errors.append(f"duplicate glossary term: {duplicate}")
    return {"errors": sorted(set(errors)), "warnings": sorted(set(warnings))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = validate(args.root)
    print("# Atlas canon audit")
    for error in report["errors"]: print(f"ERROR: {error}")
    for warning in report["warnings"]: print(f"WARN: {warning}")
    if not report["errors"]: print(f"PASS ({len(report['warnings'])} warnings)")
    return 1 if args.strict and report["errors"] else 0

if __name__ == "__main__": raise SystemExit(main())
