#!/usr/bin/env python3
"""Sincronizador del catálogo MCP — un comando = descarga + ordena TODAS las líneas.

Re-siembra desde las fuentes vivas (registro MCP oficial, apis.guru, y repos
awesome-* por línea) y re-clasifica a dominios. Idempotente (sobrescribe los
seeded). Pensado para correr "cada X" (cron / scheduled task).

    python3 scripts/mcp_sync.py            # refresh completo
    python3 scripts/mcp_sync.py --offline  # solo re-clasifica lo ya sembrado

Honesto: todo lo descargado entra `candidato`/`uncategorized` con procedencia; el
prove-it/verificación/consent siguen siendo decisión aparte. No instala nada.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.catalog import classify, classify_subsector, load_catalog, load_taxonomy  # noqa: E402
from atlas.mcp.line_seed import (  # noqa: E402
    ApisGuruSource, GithubLineSource, apis_to_candidates,
    dirs_to_candidates, files_to_candidates, nested_dir_candidates,
)
from atlas.mcp.registry_seed import RegistrySource, registry_to_candidates  # noqa: E402

SEEDED = ROOT / "docs" / "design" / "seeded"
CURATED = ROOT / "docs" / "design" / "mcp_catalog.yaml"
CLASSIFIED = ROOT / "docs" / "design" / "mcp_catalog_classified.yaml"

# Fuentes por LÍNEA (repos awesome-* verificados). item: dir|file.
_NPX = "npx skills add {repo} --skill {name}"
_CURL = "curl -O https://raw.githubusercontent.com/{repo}/main/{subdir}/{file}"
LINES: list[dict[str, Any]] = [
    {"line": "skills", "repo": "vercel-labs/agent-skills", "subdir": "skills", "kind": "skill", "item": "dir", "install": _NPX, "cap": 80},
    {"line": "commands", "repo": "hesreallyhim/awesome-claude-code", "subdir": "resources/slash-commands", "kind": "command", "item": "dir", "install": "git clone https://github.com/{repo}", "cap": 80},
    {"line": "rules", "repo": "PatrickJS/awesome-cursorrules", "subdir": "rules", "kind": "rule", "item": "file", "install": _CURL, "cap": 80},
    {"line": "prompts", "repo": "ai-boost/awesome-prompts", "subdir": "prompts", "kind": "prompt", "item": "file", "install": _CURL, "cap": 80},
    {"line": "plugins", "repo": "rohitg00/awesome-claude-code-toolkit", "subdir": "plugins", "kind": "plugin", "item": "dir", "install": "git clone https://github.com/{repo}", "cap": 80},
    {"line": "workflows", "repo": "Zie619/n8n-workflows", "subdir": "workflows", "kind": "workflow", "item": "dir", "install": "git clone https://github.com/{repo}", "cap": 80},
    {"line": "hooks", "repo": "disler/claude-code-hooks-mastery", "subdir": ".claude/hooks", "kind": "hook", "item": "file", "install": _CURL, "cap": 40},
    {"line": "subagents", "repo": "VoltAgent/awesome-claude-code-subagents", "subdir": "categories", "kind": "subagent", "item": "nested", "install": "curl -O https://raw.githubusercontent.com/{repo}/main/{subdir}/{file}", "cap": 80},
]
# Política de fallback de clasificación por línea (sin señal de alias).
KIND_DEFAULT = {"workflow": "productividad", "plugin": "ia-agentes", "subagent": "ia-agentes",
                "hook": "infraestructura", "command": "programacion", "rule": "programacion",
                "tool": "infraestructura", "api": "datos"}


def _write(path: Path, entries: list[dict[str, Any]], label: str, source: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"_generated": {"by": "scripts/mcp_sync.py", "at": datetime.now(timezone.utc).isoformat(),
                          "source": source, "note": "MÁQUINA-GENERADO. candidato/uncategorized."},
           "sectors": {"uncategorized": {"label": label, "entries": entries}}}
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return len(entries)


def _download() -> None:
    print("== descarga ==")
    # MCP registry
    try:
        rec = RegistrySource(limit=100).fetch(None)[0]
        if rec.status == 200:
            n = _write(ROOT / "docs/design/mcp_catalog_seeded.yaml",
                       registry_to_candidates(json.loads(rec.payload), source_url="https://registry.modelcontextprotocol.io/v0/servers"),
                       "MCP servers (registro oficial)", "registry.modelcontextprotocol.io")
            print(f"  mcp: {n}")
    except Exception as e:  # noqa: BLE001 — una fuente caída no tumba el resto
        print(f"  mcp: ERROR {e}")
    # APIs
    try:
        rec = ApisGuruSource().fetch(None)[0]
        if rec.status == 200:
            n = _write(SEEDED / "apis_seeded.yaml", apis_to_candidates(json.loads(rec.payload))[:150],
                       "APIs (apis.guru)", "apis.guru")
            print(f"  api: {n}")
    except Exception as e:  # noqa: BLE001
        print(f"  api: ERROR {e}")
    # Líneas GitHub
    for s in LINES:
        try:
            if s["item"] == "nested":
                cands = nested_dir_candidates(
                    repo=str(s["repo"]), parent_subdir=str(s["subdir"]),
                    kind=str(s["kind"]), install_template=str(s["install"]),
                    fetcher=None,
                )[: int(s["cap"])]
                n = _write(SEEDED / f"{s['line']}_seeded.yaml", cands, f"{s['line']} (sembrado)", f"github.com/{s['repo']}")
                print(f"  {s['line']}: {n}")
                continue
            rec = GithubLineSource(s["repo"], s["subdir"]).fetch(None)[0]
            if rec.status != 200:
                print(f"  {s['line']}: status {rec.status}"); continue
            payload = json.loads(rec.payload)
            fn = dirs_to_candidates if s["item"] == "dir" else files_to_candidates
            kwargs = {"repo": s["repo"], "kind": s["kind"], "install_template": s["install"]}
            if s["item"] == "file":
                kwargs["subdir"] = s["subdir"]
            cands = fn(payload, **kwargs)[: s["cap"]]
            n = _write(SEEDED / f"{s['line']}_seeded.yaml", cands, f"{s['line']} (sembrado)", f"github.com/{s['repo']}")
            print(f"  {s['line']}: {n}")
        except Exception as e:  # noqa: BLE001
            print(f"  {s['line']}: ERROR {e}")


def _classify() -> None:
    print("== clasificación ==")
    tax = load_taxonomy(CURATED)
    seeded = sorted(set((ROOT / "docs/design").glob("*seeded*.yaml")) | set(SEEDED.glob("*.yaml")))
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for f in seeded:
        for e in load_catalog(f):
            sec = classify(e.name, e.purpose, e.tags, tax, kind=e.kind, kind_default=KIND_DEFAULT)
            sub = classify_subsector(e.name, e.purpose, e.tags, sec, tax)
            by_sector.setdefault(sec, []).append({
                "name": e.name, "kind": e.kind, "subsector": sub, "mode": e.mode,
                "source": e.source, "install": e.install, "status": e.status, "tags": e.tags})
    doc = {"_generated": {"by": "scripts/mcp_sync.py", "at": datetime.now(timezone.utc).isoformat(),
                          "note": "Clasificación automática; todo candidato."},
           "sectors": {sid: {"label": tax.get(sid, {}).get("label", sid), "entries": v}
                       for sid, v in sorted(by_sector.items())}}
    CLASSIFIED.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cov = Counter({s: len(v) for s, v in by_sector.items()})
    print(f"  total {sum(cov.values())} → {dict(cov)}")


def main(argv: list[str]) -> int:
    if "--offline" not in argv:
        _download()
    _classify()
    print("sync OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
