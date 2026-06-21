#!/usr/bin/env python3
"""Siembra candidatos de SKILLS desde repos abiertos → mcp_catalog_skills_seeded.yaml.

Paralelo a mcp_seed_registry (MCP) pero para "saber" (skills). Fuente estructurada:
GitHub contents API del subdir `skills/` de un repo. Máquina-generado: todo
candidato/uncategorized con su comando `npx skills add` + procedencia. Instalar =
consentimiento + prove-it.

    python3 scripts/mcp_seed_skills.py [repo ...]   # default: vercel-labs/agent-skills
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.skills_seed import SkillsSource, skills_to_candidates  # noqa: E402

_OUT = ROOT / "docs" / "design" / "mcp_catalog_skills_seeded.yaml"
_DEFAULT_REPOS = ["vercel-labs/agent-skills"]


def main(repos: list[str]) -> int:
    src = SkillsSource()
    cands: list[dict] = []
    for repo in repos:
        rec = src.fetch(repo)[0]
        if rec.status != 200:
            print(f"{repo}: no accesible (status={rec.status})")
            continue
        c = skills_to_candidates(json.loads(rec.payload), repo=repo)
        print(f"{repo}: {len(c)} skills")
        cands.extend(c)
    doc = {
        "_generated": {
            "by": "scripts/mcp_seed_skills.py",
            "at": datetime.now(timezone.utc).isoformat(),
            "repos": repos,
            "note": "MÁQUINA-GENERADO. Todo candidato/uncategorized. Triar + consentir antes de instalar.",
        },
        "sectors": {
            "uncategorized": {
                "label": "Skills sin clasificar (sembrado de repos abiertos)",
                "entries": cands,
            }
        },
    }
    _OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"sembrados {len(cands)} skills → {_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or _DEFAULT_REPOS))
