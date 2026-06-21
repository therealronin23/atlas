# WORK LEDGER — estado vivo de la matrioska

Fuente única del "¿dónde estamos?" (autoridad del ESTADO; el design doc NO duplica estado).
Una línea por nodo activo. Se actualiza EN EL MISMO COMMIT que el trabajo (parte de "done").
Sobrevive a compactaciones: leer esto al retomar y se está orientado.
Detalle por feature en su design doc; el porqué/lecciones en memoria (`MEMORY.md`).
Higiene: ≤ ~40 líneas; podar nodos cerrados a la sección de archivo cuando crezca.

Formato: `[estado] nodo — próxima acción / bloqueado-por`. Estados: ✅ hecho · 🔄 en curso ·
⬜ pendiente · 🧱 muro (tipo-3) · ⏸ diferido.

## Línea activa: sustrato de memoria verificable (Fase 1 + Fase 2)

Design doc: `docs/design/design_verifiable_memory.md` · rama: trabajo mergeado a `main`.

- ✅ **Fase 1 — Sustrato (1a–1d)** — completa, auditada, deudas tipo-1 cerradas.
  - ✅ 1a índice persistente + Merkle + cableado · ✅ 1b PatternAbstractor · ✅ refactor motor/inquilino
  - ✅ 1c-seguridad (Garak real) · ✅ 1c-motor · ✅ 1d-a temporal/supersesión · ✅ 1d-b tiers
  - ✅ auditoría pre-merge (3 fixes) · ✅ deudas tipo-1 (ciclo de vida)
- 🧱 **Muro 1c — intención-vs-tema** — atacado (contrastive): separación ×2-3, FP fronterizo ~33%,
  no es detector usable. Acotado. `docs/reference/reports/immune_intent_vs_topic_contrastive.md`.
- 🔄 **Fase 2 — Huecos abiertos** (checklist en design doc):
  - ⬜ **2.1 multi-hop** ← SIGUIENTE
  - ⬜ 2.2 PII/crypto-shredding (fundacional + GAP-1 EU AI Act)
  - ⬜ 2.3 evaluación honesta (diseñada, falta construir) · ⬜ 2.4 envenenamiento (parcial)
  - ⬜ 2.5 fuga entre usuarios/tenancy · 🧱 2.6 personalización-vs-contaminación · ✅ 2.7 cold-start (conceptual)

## Gate de gobernanza (tipo-2 — orden = base de todo)

Estándar: `docs/governance/REPO_STANDARD.md` · honestidad: `docs/governance/CAPABILITIES.md`.

- ✅ **F0** estándar + CAPABILITIES + manía `wire-before-claim` (anti-vapor) cableada en AGENTS.md
- ✅ **F1** limpieza riesgo-bajo: 5 artefactos LaTeX a .gitignore, 7 scratch de raíz a graveyard,
  `.atlas-audit-home` vacío borrado
- ✅ **Huérfanos cerrados** (0 importadores no-test) → cuarentena: witness_server, log_behavioral,
  kyc_binding (+ tests). Registrados en CAPABILITIES + graveyard MANIFEST. Suite 2041 verde.
- ✅ **F2** docs/ reorganizado a la taxonomía (refs actualizadas, 0 stale)
- ✅ **F3** código muerto cerrado.
  - ✅ cuarentena F3 (reversible, `_graveyard/2026-06-21-f3/WHY.md`): affinity_maturation, scorers,
    llm_scorer, security_worker, fuzzing, red_team, gossip, witness (+tests).
  - ✅ lazo auditable CABLEADO + probado (`tests/test_live_loop_integration.py`, vía autobuild)
  - ✅ mission CABLEADO funcional (`knowledge/run.py` + `tests/test_knowledge_mission_integration.py`)
  - suite 1875 verde. (FYI: `cli.py` WIP del usuario tiene 13 errores mypy — no nuestros)
- ✅ **F4** Gates A–I cerrados con roll-up (`gates/CLOSURE.md`); cierre del Gate de gobernanza
  (`CLOSURE_governance_2026-06-21.md`)
- ✅ **Ciclo de saneamiento** establecido: `scripts/sanitation_audit.py` (read-only) cada Gate/~mensual
- ✅ **GATE DE GOBERNANZA CERRADO** (tipo-2). Próximo ciclo: revisar `_graveyard/2026-06-21*` al vencer grace (~2026-07-21)

## Línea activa secundaria: MCP trunk portable

Design doc: `docs/design/mcp_trunk_portable.md` · principio rector: cross-play.

- ✅ **F1 — Tronco Python + raíz memoria** — `MemoryTrunk` (núcleo neutro: add/recall/supersede sobre
  `SqliteMemoryIndex`) + shell FastMCP (`atlas.mcp.memory_server`, dep opcional `[mcp]`). Roundtrip
  cross-cwd/cross-proceso/cross-cliente por stdio PROBADO (`tests/test_mcp_memory_trunk.py`, 8 tests;
  guardados con importorskip → suite verde sin la dep). Portabilidad cross-INSTALL (instalar en otro
  proyecto) diferida a F4/empaquetado. `text_of` añadido al índice.
- ✅ **F2 — Raíz operating** — `OperatingTrunk` (núcleo neutro) + shell FastMCP
  (`atlas.mcp.operating_server`): AGENTS.md y WORK_LEDGER.md como RECURSOS MCP (vía enforcement
  portable, advisory) + `sanitation_audit` como TOOL read-only. 5 tests
  (`tests/test_mcp_operating_trunk.py`). DIFERIDO: franken-prompt por canal real (muro — MCP no
  impone system prompt; exige wrapper/CLI, no la primitiva MCP). ← SIGUIENTE: F3 knowledge-src.
- ✅ **F3 — Raíz knowledge-src** — `KnowledgeTrunk` (núcleo neutro) + shell FastMCP
  (`atlas.mcp.knowledge_server`): `WikipediaSource` (REST summary, gate SSRF, fetcher inyectable) →
  tools `wikipedia_lookup` / `ingest_wikipedia` cableados a `run_mission` → sustrato. PROBADO: el
  conocimiento entra con PROCEDENCIA (url+fecha+hash) (`tests/test_mcp_knowledge_trunk.py`, 4 tests).
  Honesto: procedencia, no verdad (KnowledgeVerifier filtra grounding). Falta 2ª API (dataset).
- ⬜ F4 commodity+catálogo+instalador · ⏸ F5 Rust por-raíz.

- ⏸ Paper `subject_enforced_completeness` — listo; subida a arXiv = acción del usuario.
- ⏸ Deuda diferida del sustrato: multihilo (sin consumidor), IC/corpus mayor en 1c.
