#!/usr/bin/env python3
"""Trial-en-jaula de entradas del catálogo (Pieza 2).

Uso:
  python scripts/mcp_trial.py --catalog docs/design/mcp_catalog.yaml
  python scripts/mcp_trial.py --catalog docs/design/mcp_catalog.yaml --kind skill
  python scripts/mcp_trial.py --catalog docs/design/mcp_catalog.yaml --apply

Por defecto solo reporta. ``--apply`` reescribe el YAML promoviendo candidato→probado-en-jaula
solo para entradas que pasaron el trial (consent explícito).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from atlas.mcp.catalog import StatusPromotion, apply_status_promotions, load_catalog
from atlas.mcp.spawn_trial import SpawnTrial, graduated_quarantine
from atlas.mcp.trial_gate import TrialGate


def main() -> int:
    parser = argparse.ArgumentParser(description="Trial-en-jaula del catálogo MCP (Pieza 2)")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--skills-dir", type=Path, default=Path("docs/skills"))
    parser.add_argument(
        "--agents-skills-dir",
        type=Path,
        default=Path(".claude/skills"),
        help="Skills instalados vía npx skills (SKILL.md por carpeta)",
    )
    parser.add_argument("--kind", default="", help="Filtrar por kind (skill, prompt, …)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Promover candidato→probado-en-jaula en el YAML (consent explícito)",
    )
    parser.add_argument(
        "--spawn",
        action="store_true",
        help="Probe MCP spawn (initialize+tools/list); jaula bwrap para atlas.mcp.*",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Raíz del repo (PYTHONPATH src para spawn jaula)",
    )
    args = parser.parse_args()

    spawn: SpawnTrial | None = None
    if args.spawn:
        work = args.repo_root / ".atlas-trial-work"
        spawn = SpawnTrial(repo_root=args.repo_root.resolve(), work_dir=work, use_jail=True)

    entries = load_catalog(args.catalog)
    if args.kind:
        entries = [e for e in entries if e.kind == args.kind]

    gate = TrialGate(
        skill_root=args.skills_dir,
        agents_skill_root=args.agents_skills_dir if args.agents_skills_dir.is_dir() else None,
        spawn_trial=spawn,
    )
    passed = skipped = failed = 0
    promotions: list[StatusPromotion] = []
    quarantine: list[str] = []

    for entry in entries:
        if entry.status not in {"candidato", "probado-en-jaula"}:
            continue
        result = gate.trial(entry)
        if result.skipped:
            skipped += 1
            print(f"SKIP  {entry.kind}/{entry.name}: {result.reason}")
        elif result.passed:
            passed += 1
            print(f"PASS  {entry.kind}/{entry.name} → {result.suggested_status}: {result.reason}")
            if args.apply and result.suggested_status:
                promotions.append(
                    StatusPromotion(
                        name=entry.name,
                        kind=entry.kind,
                        to_status=result.suggested_status,
                    )
                )
        else:
            failed += 1
            print(f"FAIL  {entry.kind}/{entry.name}: {result.reason}")
            qc = graduated_quarantine(
                name=entry.name, kind=entry.kind, reason=result.reason
            )
            if qc and qc.action == "quarantine":
                quarantine.append(f"{entry.kind}/{entry.name}")
                print(f"      ↳ saneamiento graduado: QUARANTINE ({qc.reason[:80]})")

    updated = 0
    if args.apply and promotions:
        updated = apply_status_promotions(args.catalog, promotions)
        print(f"\nPromovidas {updated} entradas en {args.catalog}")

    print(f"\nResumen: pass={passed} fail={failed} skip={skipped} apply={args.apply} spawn={args.spawn}")
    if quarantine:
        print(f"Cuarentena sugerida ({len(quarantine)}): " + ", ".join(quarantine[:10]))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
