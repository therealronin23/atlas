#!/usr/bin/env python3
"""Triage de docs/inbox/ — dedupe → clasificar → proponer (REPO_STANDARD §1).

Diseñado para que lo ejecute un humano O el propio lazo de Atlas: determinista
donde se puede (hash, reglas por nombre/contenido), LLM barato solo como
escalada, y NUNCA acuña verdad — con `--apply` mueve el doc a su directorio
canónico y lo alta en `docs/INDEX.yaml` con `status: propuesto`; subirlo a
`vigente` es del revisor humano.

    python3 scripts/docs_triage.py            # dry-run: imprime el plan YAML
    python3 scripts/docs_triage.py --apply    # ejecuta el plan (mueve + indexa)
    python3 scripts/docs_triage.py --no-llm   # solo reglas deterministas

Acciones del plan: move (destino claro) · duplicate (hash ya indexado →
inbox/_rejected/) · hold (nadie supo clasificarlo; se queda en inbox/).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Reglas deterministas (gratis) ANTES de gastar LLM: (regex sobre nombre,
# regex sobre primeras líneas, destino, type). Primera que matchea gana.
_RULES: list[tuple[str, str, str, str]] = [
    (r"^adr[_-]", "", "docs/decisions/adr", "decision"),
    (r"^gate[_-]", "", "docs/decisions/gates", "decision"),
    (r"^OSM-", "", "docs/membrana", "compliance"),
    # Informes del ciclo de investigación (maintenance_research_tick) — conocimiento
    # externo curado, ANTES de las reglas de contenido (un hallazgo puede citar
    # 'audit'/'design' sin ser eso).
    (r"^research[_-]", "", "docs/knowledge", "conocimiento"),
    (r"", r"EU AI Act|compliance gateway|Annex IV", "docs/compliance", "compliance"),
    (r"audit|postmortem", "", "docs/audits", "evidencia"),
    (r"", r"# Auditoría|## Postmortem", "docs/audits", "evidencia"),
    (r"runbook|usage|setup|deploy", "", "docs/operations", "operacion"),
    (r"paper|outreach|post|carta", "", "docs/outreach", "difusion"),
    (r"design|plan|roadmap|arquitectura|architecture", "", "docs/design", "design"),
]

_LLM_INSTRUCTION = (
    "Clasifica este documento del repo Atlas en UNO de estos destinos: "
    "docs/decisions/adr (decisión arquitectónica), docs/design (diseño vivo), "
    "docs/operations (cómo operar), docs/compliance (regulación/legal), "
    "docs/audits (auditoría/evidencia puntual), docs/outreach (difusión/paper), "
    "docs/knowledge (conocimiento externo curado). Responde SOLO un objeto JSON "
    '{"target": "docs/...", "type": "decision|design|operacion|compliance|'
    'evidencia|difusion|conocimiento", "reason": "..."}.'
)

_VALID_TARGETS = {
    "docs/decisions/adr", "docs/decisions/gates", "docs/design",
    "docs/operations", "docs/compliance", "docs/membrana", "docs/audits",
    "docs/outreach", "docs/knowledge",
}


def _index_mod() -> Any:
    spec = importlib.util.spec_from_file_location(
        "docs_index_audit", ROOT / "scripts" / "docs_index_audit.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_hashes(docs_dir: Path) -> set[str]:
    m = _index_mod()
    return {
        _sha256(docs_dir.parent / rel)
        for rel in m.scan_tree(docs_dir)
        if (docs_dir.parent / rel).is_file()
    }


def _classify_by_rules(path: Path) -> tuple[str, str, str] | None:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except OSError:
        head = ""
    for name_re, content_re, target, doc_type in _RULES:
        if name_re and not re.search(name_re, path.name, re.IGNORECASE):
            continue
        if content_re and not re.search(content_re, head, re.IGNORECASE):
            continue
        if not name_re and not content_re:
            continue
        return target, doc_type, f"regla determinista ({name_re or content_re})"
    return None


def _classify_by_llm(path: Path) -> tuple[str, str, str] | None:
    """Escalada LLM barata (L1). Fail-open: cualquier fallo → None (hold)."""
    try:
        from atlas.core.inference_hub import (  # noqa: PLC0415
            InferenceHub, InferenceLevel, InferenceRequest,
        )

        head = path.read_text(encoding="utf-8", errors="ignore")[:3000]
        resp = InferenceHub(mode="auto").infer(InferenceRequest(
            prompt=f"{_LLM_INSTRUCTION}\n\nNombre: {path.name}\n\n{head}",
            level=InferenceLevel.L1,
            temperature=0.0,
            task_id="docs_triage",
        ))
        if not resp.success:
            return None
        text = resp.text
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        target = str(data.get("target", ""))
        if target not in _VALID_TARGETS:
            return None
        return target, str(data.get("type", "conocimiento")), (
            f"LLM: {str(data.get('reason', ''))[:120]}"
        )
    except Exception:  # noqa: BLE001 — escalada opcional, nunca rompe el triage
        return None


def build_plan(
    docs_dir: Path | None = None,
    *,
    llm_classify: Callable[[Path], tuple[str, str, str] | None] | None = _classify_by_llm,
) -> list[dict[str, Any]]:
    docs_dir = docs_dir or (ROOT / "docs")
    inbox = docs_dir / "inbox"
    if not inbox.is_dir():
        return []
    known = _existing_hashes(docs_dir)
    plan: list[dict[str, Any]] = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.name == "README.md":
            continue
        if _sha256(path) in known:
            plan.append({
                "file": path.name, "action": "duplicate",
                "target": "docs/inbox/_rejected", "reason": "hash ya indexado",
            })
            continue
        verdict = _classify_by_rules(path)
        if verdict is None and llm_classify is not None:
            verdict = llm_classify(path)
        if verdict is None:
            plan.append({
                "file": path.name, "action": "hold", "target": None,
                "reason": "sin clasificar (reglas y LLM no decidieron)",
            })
            continue
        target, doc_type, reason = verdict
        plan.append({
            "file": path.name, "action": "move", "target": target,
            "type": doc_type, "reason": reason,
        })
    return plan


def apply_plan(plan: list[dict[str, Any]], docs_dir: Path | None = None) -> int:
    """Ejecuta el plan: mueve ficheros y alta las entradas nuevas en INDEX.yaml
    con status 'propuesto' (la promoción a 'vigente' es humana)."""
    docs_dir = docs_dir or (ROOT / "docs")
    repo_root = docs_dir.parent
    index_path = docs_dir / "INDEX.yaml"
    original = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""
    raw = (yaml.safe_load(original) if original else {}) or {}
    # Cabecera de comentarios del índice: yaml.safe_dump la destruiría (lossy).
    header = "".join(
        line for line in original.splitlines(keepends=True)[:10] if line.startswith("#")
    )
    entries = raw.setdefault("entries", [])
    applied = 0
    for step in plan:
        src = docs_dir / "inbox" / step["file"]
        if not src.is_file():
            continue
        if step["action"] == "hold":
            continue
        dest_dir = repo_root / step["target"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / step["file"]
        if dest.exists():
            dest = dest_dir / f"{src.stem}_inbox{src.suffix}"
        src.rename(dest)
        applied += 1
        if step["action"] == "move":
            entries.append({
                "path": str(dest.relative_to(repo_root)),
                "type": step.get("type", "conocimiento"),
                "status": "propuesto",
                "verified": None,
                "notes": f"triage: {step['reason']}",
            })
    index_path.write_text(
        # width alto: no re-flowear las notas largas curadas a mano.
        header + yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=4096),
        encoding="utf-8",
    )
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="ejecuta el plan")
    parser.add_argument("--no-llm", action="store_true", help="solo reglas deterministas")
    args = parser.parse_args()

    plan = build_plan(llm_classify=None if args.no_llm else _classify_by_llm)
    print(yaml.safe_dump({"plan": plan}, allow_unicode=True, sort_keys=False))
    if args.apply and plan:
        n = apply_plan(plan)
        print(f"# aplicado: {n} fichero(s) movido(s); entradas 'propuesto' en INDEX.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
