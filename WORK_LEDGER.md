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
  - ✅ 2.3 evaluación honesta (autobuild 2026-06-24: benchmark anti-leak + 10 tests) · ⬜ 2.4 envenenamiento (parcial)
  - ⬜ 2.5 fuga entre usuarios/tenancy · ✅ 2.6 (mitad tratable; clasificador automático = muro 1c registrado) · ✅ 2.7 cold-start (conceptual)

## Línea activa: Cónclave (`deliberation_council`) — deliberación verificable multi-voz

Design doc: `docs/design/design_deliberation_council.md` · alias narrativo: Cónclave.

- ✅ **v1 — skill de deliberación** — CONSTRUIDO y probado.
  - Fase A (prosa): skill servido + espejo `.claude/skills` + catálogo (planning/served) + portable
    degradada. Vivo en AMBOS canales (Claude Code + tronco MCP).
  - Fase B (código): `LlmReviewer`+`build_trio_reviewers`+`convene_for_decision`+`record_synthesis`
    sobre `adversarial_panel` (ADR-047). 8 tests verdes, mypy strict.
  - Smoke en vivo 2026-06-24: 3 proveedores `mode=live`; Mistral revisión hostil real, Kimi vivo
    (detalle a veces vacío), Gemini 503 transitorio. Honestidad en CAPABILITIES. Juez-único validado
    en decisión real del usuario (f2-3).
  - Deuda menor: parseo detalle Kimi · reintento 503 · cablear `record_synthesis` al recorder real.
- 🔄 **v2 — reordenado por el Cónclave en vivo (council:full sobre sí mismo, 2026-06-24)**:
  - ✅ **v2.0 fiabilidad del trío** — HECHO. Tres fixes (rama `feat/council-v2.0-trio-reliability`):
    Fix 0 config `gemini_free`→`gemini-2.5-flash` (3.5-flash daba 503 crónico, no transitorio —
    diagnóstico de raíz en vivo); Fix 1 reintento ante transitorios en `inference_hub`
    (allowlist 503/500/timeout/conn, 2 reintentos, sleep inyectable); Fix 2 parseo anclado a 1ª
    línea en `LlmReviewer.review` (conserva detalle, antes tiraba lines[0]). Suite 2186 verde,
    mypy strict limpio (nuestros archivos). **Smoke vivo: 3/3 voces útiles** (antes ~1/3).
    Spec/plan en `docs/superpowers/{specs,plans}/2026-06-24-council-v2.0-*`. ← SIGUIENTE: v2.0.5.
  - ⬜ **v2.0.5 fallback de slot por-linaje** (cura el fallo correlacionado NIM: Kimi+Mistral misma
    infra). Cada voz = lista ordenada de proveedores del MISMO linaje (preserva diversidad).
    Pre-requisito: mapear proveedores gratis/multi-cuenta por linaje vivos (CN no-NIM). Aquí se paga
    la config retry por-`Provider` con consumidor real.
  - ⬜ **v2.1 debate por rondas** (opt-in, NO cambia el one-shot → `verified_producer` a salvo).
    CAVEAT grabado por Mistral en vivo: el spec debe resolver estado/abandono a mitad + interacción
    con colas/permisos/métricas; "aditivo" es necesario, NO suficiente.
  - ⬜ **v2.2 puerta de reinicio de loop** (mayor radio; toca loops vivos; después).
  - ✗ **sucesión = MEDIR antes de construir** (¿`record_synthesis` mejora el juicio de Atlas?), no
    máquina. `wire-before-claim` aplicado al roadmap.
  - Próxima acción: brainstorming de v2.0 (fiabilidad) en sesión limpia → spec → plan.

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

## Línea activa: endurecimiento auditoría 2026-06-22 (lecciones en `MEMORY.md`)

Auditoría multi-subagente + correcciones vía `/autobuild` (auditor cazó 2 regresiones sutiles).

- ✅ **Seguridad (tipo-2)**: jail fail-closed para código generado (OMEGA+verify ya NO usan `_execute_normal`),
  SSRF pin a nivel de conexión (TLS contra hostname), HMAC de aprobaciones con clave local dedicada,
  `resolve_path` contención estricta (bug real de escape de workspace), `BLOCKED_IMPORTS` += egress.
- ✅ **Split orchestrator**: `maintenance_facade` + `pipeline_runner` extraídos. orchestrator.py 2691→2029
  (−662, ~25%). Lección: llamadas a métodos públicos parcheables van por `self._orch.X()`.
- ✅ **Honestidad docs**: README histórico, ROADMAP coherente, cabeceras ADR-039/040 Implemented.
- 🔄 **Cablear código muerto** ← SIGUIENTE: `cascade.py` (ADR-042) + `lesson_store.py` (ADR-044) a caller vivo.
- 🔄 Backlog técnico: ✅ tests `operational_wal`/`AgenticExecutor` (autobuild, +29 tests; cazó bug rotación→tech-3)
  · ✅ consolidar coseno duplicado (autobuild; canónica vector_store, lesson_recaller delega) · ⬜ jail rootfs
  mínimo, seccomp, `git apply`, snapshot integrity, warning Starlette.

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
  - ✅ Paso 3 skills servidos: `SkillStore` (sirve `docs/skills/*.md` sin descarga) + tronco expone
    `get_skill`/`list_skills`. 1er skill real: `atlas-coding-discipline` (nuestras máximas, fuente única
    anti-deriva), registrado en catálogo (mode=served, tags coding+productivity-meta). 4 tests.
  - ✅ Paso 4 sembrar registro oficial: `RegistrySource` (/v0/servers, allowlisted) +
    `registry_to_candidates` (con procedencia) + `scripts/mcp_seed_registry.py`. Sembrados 100
    candidatos reales → `docs/design/mcp_catalog_seeded.yaml` (máquina-generado, candidato/uncategorized,
    0 instalable). 3 tests. Triaje/clasificación = decisión posterior.
  - ✅ Pasos 5-6 instalador por mode: `plan_install` (solo `verificado`, enruta served→noop /
    connected→connect / installed→place_skill) + `vet_action` (veto SentinelGate pre-spawn, metachars/
    IOC) + `execute` (runner inyectable). Script muestra el plan. 4 tests. Hoy plan vacío (0 verificado).
  - ✅ Agregador indexa lo CONECTADO (no solo native_roots): `servers_from_registry` parsea
    `mcp__server__tool`; `TrunkAggregator(servers=...)`. Así un MCP externo aparece en su sector.
  - ✅ **FLUJO E2E PROBADO** con server externo real (`@modelcontextprotocol/server-everything`):
    prove-it (13 tools) → marcado `verificado` en catálogo → tronco lo auto-spawnea → indexado en
    commodity-infra (13) → `trunk_invoke echo` enruta y responde. La visión completa, en vivo.
  - ✅ **C CERRADO**: catálogo v2 + tronco catalog-driven + skills servidos + sembrado del registro
    (100) + instalador por mode con veto + e2e externo verificado. Maquinaria + flujo demostrados.
  - ✅ **Taxonomía v3 — dominios humanos** (a petición del usuario: autoexplicativos, sin manual):
    9 sectores (programación/diseño/ciberseguridad/datos/investigación/conocimiento-memoria/
    productividad/ia-agentes/infraestructura) × subsectores, con alias y solapamiento por tags.
    `load_taxonomy` + `find` (buscador por nombre/alias, madurez-first) + navegación de 3 niveles en el
    tronco (`trunk_sectors`/`trunk_subsectors`/`trunk_tools`/`trunk_find`). `phase` para desarrollos
    nuestros. Verificado en vivo (find 'seguridad'→Trail+Playwright vía tag). Catálogo curado remapeado.
  - ✅ **Skills ecosystem (saber) + MCP (hacer)** — desarrollo conceptual (Grok, prove-it-eado): son
    complementarios; nuestro catálogo YA los co-clasifica por dominio. Cadena de suministro de skills:
    descubrir (repos awesome-* + tech-leads-club/agent-skills), instalar (`npx skills add`, vercel-labs/
    skills → `mode:installed`/`place_skill`), servir lo nuestro (`get_skill`/`mode:served`). Seguridad:
    `vet_action` ahora veta TODO comando (connect + place_skill), no solo connect. Instalar externo =
    consentimiento explícito (demostrado: harness bloqueó `npx skills` sin autorización). Diseño en doc.
  - ✅ Seeder de skills (`atlas.mcp.skills_seed` + `scripts/mcp_seed_skills.py`): GitHub contents API
    (estructurado, no scraping) → candidatos kind=skill con `npx skills add` + procedencia. Sembrados 9
    de vercel-labs/agent-skills → `mcp_catalog_skills_seeded.yaml`. 2 tests.
  - ✅ **SKILL INSTALADO E2E** (autorizado): `npx skills add vercel-labs/agent-skills --skill
    vercel-react-best-practices` → `.agents/skills/` (universal + symlink Claude Code), aparece en la
    lista de skills viva. Registrado en catálogo (programación/frontend, instalado). Cadena de
    suministro de skills COMPLETA: descubrir→sembrar→consentir→instalar→vivo.
  - ✅ **Taxonomía de LÍNEAS completa** (investigación 2026: el stack de extensión son ~10 kinds, no 4):
    `kind` ampliado a skill/mcp/api/tool/prompt/command/hook/subagent/plugin/rule/workflow, cada uno
    con su `mode` por defecto (served/connected/installed). `by_kind`+`of_kind` + navegación POR LÍNEA
    en el tronco (`trunk_kinds`+`trunk_catalog`). "StormMCP por línea" realizado: 1 catálogo, N líneas,
    navegable por dominio Y por kind. Verificado en vivo. 4 tests.
  - ✅ **Foundation de sembrado por línea** (`atlas.mcp.line_seed`): `GithubLineSource`+`dirs_to_candidates`
    (genérico GitHub) + `ApisGuruSource`+`apis_to_candidates` (APIs). UA por defecto + apis.guru allowlisted.
  - ✅ **TODAS las líneas sembradas** (vía 3 subagentes paralelos, reusando foundation; cero conflicto):
    apis(150) · tools(30) · prompts(80) · commands(23) · rules(80) · subagents(80) · hooks(12) ·
    plugins(80) · workflows(80) = **615 candidatos** en `docs/design/seeded/*.yaml`, todos
    candidato/uncategorized con procedencia. Guard de integridad en tests. Repos fuente verificados por
    los subagentes.
  - ✅ **Auto-clasificador a dominios** (`catalog.classify`, por tags/alias, sin manual) +
    `scripts/mcp_classify_seeded.py` → `mcp_catalog_classified.yaml` (724 candidatos clasificados).
    Cobertura: TODOS los dominios poblados (programación 356, ia-agentes 36, diseño 34, datos 33,
    infra 20, ciber/investig 17, …; 203 uncategorized sin señal = honesto). El tronco carga curado +
    clasificado para el BROWSE (candidatos nunca se conectan; trunk_children filtra a verificado/
    instalado). Live: 11 líneas, browse por dominio poblado, find sobre 700+. "En todas partes" ✅.
  - ✅ Fallback por línea en `classify` (`kind_default`): sin señal de alias, enruta por naturaleza del
    kind (workflow→productividad, plugin/subagent→ia-agentes, hook/tool→infra, command/rule→programación,
    api→datos); transversales (prompt/skill/mcp) a alias-only. Uncategorized 203→43. La señal SIEMPRE gana.
  - ✅ **Línea APIs verificada E2E** (nuestro código, sin consent): `OpenMeteoSource` (clima) +
    `FrankfurterSource` (divisas), sin auth, por el pipeline knowledge-src (run_mission→sustrato con
    procedencia). prove-it LIVE (ingesta real ok). tools en knowledge_server + manifest; catálogo
    instalado (datos). Ahora 4 APIs nuestras vivas (Wikipedia/WorldBank/Open-Meteo/Frankfurter).
  - ✅ **MCP de referencia verificados** (prove-it LIVE, sin secretos): `sequential-thinking` (ia-agentes/
    planning) + `mcp-memory` (knowledge graph oficial, conocimiento-memoria/grafos). Catálogo verificado/
    vetted; el tronco los frontea automáticamente → 6 hijos (3 nuestros + everything + 2 nuevos).
  - ✅ **2 skills más instalados E2E** (sin secretos): `web-design-guidelines` (diseño/ux) +
    `writing-guidelines` (productividad/ofimática), vivos en la lista de skills. Catálogo: 48 entradas
    (12 instalado, 3 verificado). Items verificados/instalados ya cubren mcp·api·skill en varios dominios.
  - ✅ **Soporte de credenciales**: `CatalogEntry.env_passthrough` + `trunk_children` pasa los NOMBRES
    de env vars (nunca el valor) a `McpServerConfig` → servicios con secreto funcionan al verificarse,
    sin meter secretos en git/catálogo. Infra para TODO servicio con credencial.
  - ✅ **Google Workspace ENCHUFADO** (OAuth): el usuario creó el OAuth client (Desktop/PKCE); secretos
    en `~/.config/atlas-mcp/secrets.env` (chmod 600, fuera de git). Desplegado en Claude Code vía
    `claude mcp add -e` → `uvx workspace-mcp --tool-tier core` ✔ Connected (45 tools: Gmail/Calendar/
    Drive/Docs/Sheets/Tasks/…). OAuth de navegador al PRIMER uso (token en `~/.google_workspace_mcp/`).
    Catálogo: instalado. NOTA seguridad: client secret pegado en chat → rotar tras confirmar. NO se usó
    el flag inseguro OAUTHLIB_INSECURE_TRANSPORT ni el token ADC (no necesarios). Está como conexión
    DIRECTA (no vía tronco; el tronco necesitaría el env en shell + restart).
  - ✅ **Sincronizador `scripts/mcp_sync.py`** (un comando = descarga + ordena TODAS las líneas):
    re-siembra del registro MCP + apis.guru + 7 repos awesome-* (config `LINES`) y re-clasifica a
    dominios. `files_to_candidates` (fichero-por-item) añadido a line_seed. `--offline` solo reclasifica.
    Idempotente, fuentes caídas aisladas. Probado live (734 clasificados). Listo para cron/scheduled.
  - ✅ **Automatización periódica (3 capas, robusta)**:
    (1) Agente programado de Claude `mcp-catalog-sync` (diario 08:07 local; corre mcp_sync, commitea en
        rama si cambia, reporta cobertura; no mergea ni instala). En `~/.claude/scheduled-tasks/`.
    (2) Cron local de respaldo (diario 04:00 → log `~/.config/atlas-mcp/sync.log`) por si el agente falla.
    (3) "en atlas": el `self_maintenance/scheduler.py` YA scoutea MCP (registry_scout/community_scout) →
        capa de descubrimiento interna existente. POSIBLE follow-up: puentear mcp_sync ↔ ese scheduler.
  - Credenciales de otros servicios (GitHub/Slack/Linear/Notion/Postgres/Firecrawl/Brave/Figma) = el
    usuario las consigue (lista + env vars dada); se enchufan como Google al recibirlas.
- ⏸ **F5 Rust por-raíz** — GATILLO NO DISPARADO: el design pide Rust solo cuando una raíz concreta lo
  justifique por performance; hoy ninguna es caliente (coseno sobre conjuntos pequeños, I/O). No se
  arranca por arrancar (anti-vapor). Reabrir cuando haya un cuello de botella MEDIDO.

- ✅ Demo CLI `atlas completeness-demo [--json]` cableada (9 escenarios; `tests/test_cli_completeness_demo.py`).
  cli.py mypy limpio (eran 13 errores del módulo dinámico). Complementa el paper.
- ⏸ Paper `subject_enforced_completeness` — listo; subida a arXiv = acción del usuario.
- ⏸ Deuda diferida del sustrato: multihilo (sin consumidor), IC/corpus mayor en 1c.
- ✅ **opt#1 lazy-spawn**: McpRegistry.ensure_started + dispatch arranca el owner on-demand; serve() sin start_all (índice desde native_roots). Cero spawns/descargas al conectar el tronco. 7 tests.
- ✅ **opt#2 creds-en-tronco**: serve() carga ~/.config/atlas-mcp/secrets.env (setdefault) → los MCP con env_passthrough (google-workspace) se pueden frontear por el tronco. Secretos fuera de git.
- ✅ **opt#3 tests-invariante**: los tests del catálogo real afirman invariantes (verificado→vetted+install; connect→command+no-vetado) en vez de listas exactas → dejan de romperse al verificar items nuevos.
- ✅ **opt#4 branch-policy**: el agente mcp-catalog-sync reutiliza UNA rama estable `chore/mcp-sync` (force-push) en vez de ramas por fecha → no se acumulan.
- ✅ **opt#5 subdirs-anidados**: `nested_dir_candidates` (categories/<cat>/<item>) en line_seed + subagents añadido a LINES del sync (item:nested) → ya no queda congelado. 1 test. (2 nits mypy pre-existentes corregidos.)
- ✅ **opt#6 dedup**: `dedupe_by_kind_name` (por kind+name, conserva primero) en catalog, aplicado en mcp_sync y mcp_classify_seeded antes de clasificar → sin duplicados entre fuentes. 3 tests.
- ✅ **opt#7 classify-refinado**: podados alias genéricos de programación + subsector pesa 2× (específico gana). programación 258→195 (−24
## Línea: Atlas usa el ecosistema + motor de auto-construcción
- ✅ **A conectar Atlas al tronco**: `atlas_mcp_config` + `scripts/atlas_install_trunk.py` → escribe ~/atlas/mcp_servers.json apuntando al tronco (fusiona, no pisa). Atlas pasa a USAR memoria/knowledge/skills/APIs. 9 tests.
- ✅ **B motor backlog (dry-run honesto)**: `self_maintenance/backlog.py` (BacklogItem/load_backlog/pending) + `docs/backlog.yaml` (6 huecos Fase 2) + `scripts/atlas_self_build.py` (lista qué atacar por prioridad). Base del motor de auto-construcción; no genera código aún (consent). 5 tests.
- ✅ **A DESPLEGADO**: `atlas reality` → mcp server_count 1, status configured. Atlas (su orchestrator/McpRegistry) ya consume el tronco: memoria/knowledge/skills/APIs disponibles a su loop. La desconexión cliente-vs-runtime, cerrada.
- 🔄 **B base puesta**: backlog + dry-run vivo. FALTA (gran salto, con consent): cablear generate capaz + auditoría autobuild para que Atlas GENERE+adopte sobre su backlog (no solo lo liste).
- ✅ **L2 frontier (NVIDIA)**: `inference_hub` gana provider `nvidia_llama_large` (llama-3.1-405b) en L2 (antes vacío) con `account_pool` de 2 cuentas (NVIDIA_API_KEY/_2) + fallback. integrate.api.nvidia.com allowlisted. Es la palanca #1: cerebro potente para self-build. 6 tests. (2ª cuenta: añadir NVIDIA_API_KEY_2.)

## Línea: profundizar el MCP + memoria al máximo (sesión 2026-06-25 — INVESTIGACIÓN, sin implementar)

Contexto: el usuario pide exprimir el MCP (sospecha que lo infrautilizamos) y desarrollar la memoria al
máximo, hacia una visión larga (workflow por-Gate, regulador de tokens, copia-digital → reducir HITL).
NADA implementado esta sesión salvo honestidad-docs (tech-9 done + AGENTS.md:220). HARD-GATE brainstorming.

- ✅ **Honestidad-docs**: tech-9 marcado done (rootfs mínimo ya existía en `bwrap_jail.py:159-185`, verificado);
  `AGENTS.md:220` corregida ("/ bind read-only" → rootfs mínimo).
- ✅ **Auditoría MCP HECHA** (`docs/design/mcp_six_primitives_audit.md`, grep no asunción): recuento honesto
  **2 de 6** — Tools a fondo + Resources solo 2 docs (`operating://agents|ledger`). Prompts=0 (skills van por
  Tools `get_skill`, NO por el primitivo Prompts), Sampling=0, Roots=0 (`RootSpec` es nombre interno, colisión
  léxica), Elicitation=0. Huecos priorizados: **#1 Resources del catálogo** (= "JSON índice" del usuario =
  mesa SP-A, internal-prior-art, coste bajo) ← EMPEZAR · #2 Prompts para skills · #3 Elicitation (marco de
  HITL/SP-D, NO construir aún; verificar floor `mcp>=1.2`) · #4 Sampling (medir, SP-B) · #5 Roots diferido.
  → **PRÓXIMA ACCIÓN: brainstorming de "Resources del catálogo" (#1).**
- 🔄 **Hallazgo embeddings (investigado)**: memory MCP corre sobre `StubEmbedder(dim=64)` (hash, no semántico).
  `LiteLLMEmbedder` ya existe y NO es Gemini-locked. Pero API hospedada = lock-in (usuario lo rechaza con razón).
  Respuesta universal = modelo LOCAL in-process (BGE-M3/Qwen3-0.6B/EmbeddingGemma-300M/MiniLM). Trade-off:
  dep pesada + descarga vs stub cero-deps. → backlog `memory-mcp-local-embedder` (prio-2, DEPENDE del audit).
- ⏸ **Visión larga (registrada, NO empezada — cada una su spec→plan cuando toque)**:
  - SP-B **regulador de tokens**: conoce gasto, sube/baja consumo según dificultad (atada al modelo), acelera lo
    fácil, cuida lo difícil.
  - SP-C **memoria al máximo**: trust-scoring, FTS/híbrido, grafo temporal tipado, recall verbatim-sin-resumen
    (anti-alucinación, lección Hermes), user-modeling. Empieza por el embedder local (SP-C ladrillo 1).
  - SP-D **copia-digital / reducir HITL** (con investigación de por medio, prioridad seguridad; Elicitation MCP
    es el hook nativo). Manía: `no-deepen-hitl-coupling` mientras no haya mecanismo seguro.
  - SP-E **workflow por-Gate** (Dynamic Workflows): el primitivo NATIVO para el loop autónomo autobuild +
    Cónclave + tronco MCP. Mapeo: orchestrator-script=Opus · subagents por tier=impl-sonnet/haiku ·
    adversarial-review=auditor · ledger=variables del script (resume tras compact — PRUEBA en vivo 2026-06-25:
    un subagente murió por límite de sesión porque el plan vivía en mi contexto; el workflow lo arregla) ·
    trunk_find/invoke=agents llaman al tronco por subtarea. Planificar 1 vez → mesa de trabajo compartida
    agentes/subagentes (= Resources MCP, SP-A), todo con etiqueta de estado; con el tiempo un proyecto entero
    por workflow. Disponible: CLI 2.1.177 ≥ 2.1.154. Invocación `ultracode:` / `/effort ultracode`. Guardar:
    `/workflows`→`s`→`.claude/workflows/atlas-autobuild.md` (= mecanismo de evolución versionable).
    **Caveats grabados:** (1) FRONTERA HITL — sin sign-off a mitad de run; lo autónomo solo tipo-1 reversible
    test-gated; lo irreversible/sensitivity=high sigue escalando (choca con `no-deepen-hitl-coupling`).
    (2) coste vs ahorro → tier por necesidad, no max-paralelismo. (3) pre-allowlistear `mcp__atlas-trunk__*`.
    (4) research preview, sale-de-sesión = reinicia. INTENTO 2026-06-25: lancé `ultracode:` para tech-9 y NO
    apareció tarjeta de aprobación → el runtime DW no es drivable desde mi lado (assistant); queda como acción
    del USUARIO. **Próxima acción (plan medido-primero, no vapor):** el usuario lanza un prototipo de 1 item como
    `ultracode:` en slice pequeño → medir coste/calidad en `/workflows` vs autobuild-skill → si gana, diseñar
    frontera HITL + allowlist tronco → guardar el workflow. Ver [[dynamic-workflows-autobuild-conclave]].
  - SP-A **mesa de trabajo** (consultar el tronco 1 vez al planificar → manifest compartido a agentes) = depende
    de que el MCP exponga Resources → BLOQUEADO por `mcp-audit-six-primitives`.
