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
  Honesto: procedencia, no verdad (KnowledgeVerifier filtra grounding). 2ª API AÑADIDA: World Bank
  (datos abiertos, indicador por país) — mismo pipeline verificado. F3 PLENO.
- ✅ **F4 — Agregación + catálogo + instalador** — `TrunkManifest` (las 3 raíces nativas → config de
  cliente MCP unificada = "una conexión"; overhead 6 tools, anti-kitchen-sink) + `installer` (parsea
  `mcp_catalog.md`, instala SOLO `verificado` — hoy 0; wire-before-claim) + `scripts/mcp_install.py`
  (reporte read-only). PROBADO: cada raíz de la config unificada arranca y expone sus tools
  (`tests/test_mcp_trunk_manifest.py`, 7 tests). Commodity (filesystem/git) = off-the-shelf vía
  instalador cuando se verifique, no reinventadas.
- ✅ **LÍNEA MCP TRUNK F1–F4 CERRADA.** 3 raíces nativas portables + agregación + instalador honesto,
  suite verde, mergeada y pusheada a origin/main. 2ª API (World Bank) ya añadida → F3 pleno.
  ⚠️ MATIZ (corrección del usuario 2026-06-21): F1–F4 construyó las RAÍCES + un `trunk_manifest` que
  EMITE config (bundle: cliente→N raíces por separado). NO construyó el TRONCO-AGREGADOR real (un MCP
  único que frontea varias MCP, CLASIFICADAS por sector/necesidad, con enrutado por objetivo). Esa
  visión está en el design (arquitectura "tronco+raíces", agregadores magg/1mcp como candidatos) pero
  SIN implementar. → es la línea B.

## Línea: TRONCO-AGREGADOR + catálogo (la visión real del usuario) — NUEVA, no empezada

- ⬜ **A — Desplegar** las 3 raíces Python al cliente (`claude mcp add`, save en /home/ronin/atlas).
  Quick win reversible; aún es bundle (N conexiones), no tronco único. ← EN CURSO.
- 🔄 **B — TRONCO-AGREGADOR**:
  - ✅ Prove-it de agregadores → NO adoptar ninguno (magg=AGPL, 1mcp=Node, metamcp=enterprise,
    mcgravity=load-balancer, StormMCP=SaaS). Construir sobre `McpRegistry` (ADR-035, vivo: agrega +
    namespacing + Merkle + SentinelGate, diferencial que ninguno tiene). Auditoría de asimilación en
    design doc. Catálogo se siembra de registros ABIERTOS, no StormMCP.
  - ✅ `TrunkAggregator` + shell FastMCP (`atlas.mcp.trunk_server`): fachada META PEQUEÑA
    (trunk_sectors/trunk_tools/trunk_invoke) con descubrimiento LAZY por sector (anti-kitchen-sink) +
    purpose para routing + dispatcher inyectable. 6 tests (`tests/test_mcp_trunk_aggregator.py`).
  - ✅ Dispatcher REAL: `root_configs` + `serve()` montan McpRegistry (Merkle+SentinelGate) sobre las
    3 raíces y el tronco las frontea. Prove-it E2E: cliente→tronco→add/recall a memoria (score 0.93).
    DESPLEGADO: `atlas-trunk` ✔ Connected reemplaza el bundle de 3 (UNA conexión). 7 tests.
  - ✅ **B CERRADO.** Pendiente menor: filtro/middleware ligero (asimilable de metamcp).
- 🔄 **C — Catálogo verificado + instalador real**:
  - ✅ Triaje del grok dump → **catálogo estructurado YAML** (`docs/design/mcp_catalog.yaml`, 43
    entradas en 14 SECTORES) = el eje de clasificación del tronco. Loader `atlas.mcp.catalog`
    (sector/kind/status) + instalador (`scripts/mcp_install.py`) que reporta por sector. md = narrativa,
    YAML = fuente máquina. Viejo parser markdown (`installer.py`) retirado. 5+ tests.
  - ✅ Auditoría + premortem (`docs/design/mcp_sector_architecture_audit.md`): arquitectura =
    sectores LÓGICOS + spawn perezoso (NO proceso-por-sector); skills vía `get_skill`+prompt+resource.
  - ✅ Paso 0 SPIKE: FastMCP sirve tool+prompt+resource (listables/recuperables) → mecanismo de skills OK.
  - ✅ Paso 1 catálogo v2: tags multi-sector, mode (served/connected/installed), version/license/trust/
    transport + `in_sector` (sector = vista). Retrocompatible. 7 tests.
  - ✅ Paso 2 tronco dirigido por catálogo: `trunk_children()` deriva los hijos del catálogo (mcp +
    connected + instalado/verificado); nuestras raíces resuelven cmd con path arg, externos vía
    `install`. `serve()` ya no usa lista fija. Verificado E2E. 8 tests. (Spawn perezoso = follow-up
    cuando haya externos; hoy eager con 3 raíces es correcto, anti-vapor.)
  - ⬜ SIGUIENTE: 3 skills servidos E2E (`get_skill`+prompt) · 4 sembrar registro oficial ·
    5 prove-it→verificado · 6 instalador por mode.
- ⏸ **F5 Rust por-raíz** — GATILLO NO DISPARADO: el design pide Rust solo cuando una raíz concreta lo
  justifique por performance; hoy ninguna es caliente (coseno sobre conjuntos pequeños, I/O). No se
  arranca por arrancar (anti-vapor). Reabrir cuando haya un cuello de botella MEDIDO.

- ✅ Demo CLI `atlas completeness-demo [--json]` cableada (9 escenarios; `tests/test_cli_completeness_demo.py`).
  cli.py mypy limpio (eran 13 errores del módulo dinámico). Complementa el paper.
- ⏸ Paper `subject_enforced_completeness` — listo; subida a arXiv = acción del usuario.
- ⏸ Deuda diferida del sustrato: multihilo (sin consumidor), IC/corpus mayor en 1c.
