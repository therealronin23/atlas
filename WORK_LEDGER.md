# WORK LEDGER — estado vivo (WHERE + próxima acción)

Regenerado desde cero el 2026-07-08 (los docs raíz previos fueron puestos en
cuarentena por el operador; historia anterior en `git log` y `docs/archive/`).
Disciplina: entradas nuevas ARRIBA, una línea de estado por frente, ledger corto
(≤40 entradas; al superar, plegar lo viejo a `docs/archive/`). Verificar antes
de escribir: `atlas reality --json`.

## WHERE

- **OLA BOOTSTRAP COMPLETA — T0 núcleo de sucesión + T5.1 + cola de auditoría
  (2026-07-17)** — 8 commits: c0f2b72f/2852e132/68ff22f6 (T0: migración de 58
  memorias harness + 2 doctrinas al sustrato con procedencia, recall verificado
  0.700/0.733 con Merkle; `atlas handoff` genera docs/handoff/GENERATED/ con
  `--check` de frescura; backups pre-migración .pre-t0-migration.bak), 00f84212
  (revisión final de rama Sonnet: APROBADO CON ARREGLOS, 1 Important+6 Minor,
  arreglados I1/M2/M3/M5-M7, M4 no-cambio adjudicado), 6e145c04 (T5.1: el smoke
  YA existía desde 2026-07-09 y corrió hoy — el gap real era visibilidad;
  sección provider_smoke en `atlas reality`, que HOY aflora
  openrouter_qwen3_coder_free muerto), 5b2300a1 (umbral matched 0.8→0.5 MEDIDO:
  positivos 0.533-0.774 vs ruido 0.303-0.449; chunking de docs largos → T0.5b),
  6f08e972 (ADR-070: HermesRestAdapter retirado con evidencia de cero callers,
  -909 líneas; canal canónico = Kanban/atlas-twin). 4bis-1: tick del grafo
  diagnosticado SIN bug (horario, gating por HEAD, fail-closed correcto).
  4bis-4: .venv-scraping reconstruido (crawl4ai 0.9.2), marcador real
  success=200 vía SSRF bridge. Re-verificación: 183 tests dirigidos verdes +
  reality limpio. F2.6 PENDIENTE con prompt listo
  (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md — la ola
  llegó con >50% de presupuesto consumido, regla bootstrap).
  **Próxima acción:** decisiones del operador (secret OAuth, 12 fuentes largas,
  F2.6) + siguiente ola: T2.1 consola mínima ∥ T0.5b digestión.
- **F3 CERRADA → PLAN TOASTY F1-F5 COMPLETO (2026-07-16 noche)** — últimas
  piezas: tools `graph_communities()` y `graph_semantic_neighbors(note)` en el
  tronco (graph_server + RootSpec; la semántica graphify — comunidades con
  cohesión y miembros — por fin consultable por MCP; 3 tests nuevos + paridad,
  mypy --strict; NOTA: la BD servida aún no tiene ObsidianNote — responderán
  el mensaje limpio "vault no ingerido" hasta que el próximo tick alcance
  HEAD e ingiera graphify-vault). F3.3 quedó cubierta por la sesión Codex con contrato MÁS
  estricto que el plan (Symbol==0 o cache roto invalida la regeneración entera
  en vez de loguear — desviación aceptada: mejor honesto que silencioso).
  Excepción puntual a la delegación: estas 2 tools las implementó Fable
  directo — el agente Sonnet murió 4 veces por la incidencia 529 de Anthropic
  y cada reanudación re-pagaba su transcript; hacerlo a mano era más barato.
  Pendientes de la campaña: revisión final de rama única + decisiones del
  operador (monitor graphify, higiene docs/handoff en INDEX, F2.6, spec B+C).
- **F3/F5 CIERRE DE CABLEADO (2026-07-16)** — la revisión de los cambios
  pendientes encontró tres huecos reales: el tick no pasaba el vault a Kuzu,
  `ObsidianNote` no migraba `cohesion`, y el tronco no conservaba
  `timeout_seconds` ni adopciones persistidas. Se añadieron migración aditiva,
  propagación de timeout, adopción fail-open con catálogo curado por delante,
  telemetría/cooldown y smokes de proceso. **Próxima acción:** suite completa
  local y publicar el lote; el runner remoto sigue limitado por
  bubblewrap/dependencias opcionales. La suite local queda en 3532 verdes;
  `reality --run-checks --include-browser` sigue bloqueándose en su subproceso
  GraphRAG y se detuvo por PID exacto, por lo que no se declara ese smoke como
  verde.

- **F4 DAEMON: REARRANCADO + NOTA DE HONESTIDAD (2026-07-16)** — el daemon
  estuvo PARADO desde el 2026-07-12 20:44:52 (parada MANUAL limpia vía
  systemctl, el journal la registra; 19min de CPU consumidos) hasta hoy
  15:50 — **4 días sin documentar en ningún doc canónico y sin rearrancar**;
  el ledger ColdUpdate sin propuestas nuevas desde el 12-jul 15:19.
  Rearrancado tras reinstalar el unit (el repo llevaba hardening de la
  auditoría Codex — UMask=0077, NoNewPrivileges, RestrictSUIDSGID,
  PrivateTmp — más los límites MemoryMax=4G/TasksMax=4096 ya commiteados):
  `active`, journal limpio. Guarda nueva contra recaídas:
  `scripts/daemon_idle_guard.sh` en el hook SessionStart (silencio salvo
  inactive >24h; tests 8 passed) — el grueso lo commiteó la sesión Codex
  concurrente (066b4163/a03484c8) y esta sesión lo verificó contra el spec
  del plan. F4 del plan toasty-hatching-pillow CERRADA.
- **CI IMPORTS ESTABLES (2026-07-16)** — `uv run` aislado no incluía la raíz:
  se corrigió `PYTHONPATH` y `scripts/`/`tests/` son paquetes explícitos.

- **GRAPHRAG REANUDABLE SIN VOLVER A CERO (2026-07-16)** — causa raíz
  reproducida: Graphify 0.9.11 escribía cache incremental por chunk con
  `merge_existing=True`, un chunk podía contaminar otra fuente y dos rollbacks
  por nombres borraban 15/16 resultados ya pagados al fallar el último. La
  publicación atómica se conserva, pero el trabajo previo ahora se separa:
  extracción serial por fuente, writer incremental desactivado, salida 16.384,
  sin retry adaptativo que subcuente tokens, filtro de fuente exacta, schema y
  hash estable antes del write atómico. Cada respuesta registra uso real al
  callback; fallos transitorios conservan otras fuentes y bloqueos de
  cuota/billing/auth/modelo cortan el lote. Regresiones locales cubren
  reanudación selectiva, contaminación cruzada, parciales, corte fatal y que el
  wrapper no vuelva a purgar checkpoints verificados. **Próxima acción:** en
  futuras reconstrucciones, usar siempre el quality wrapper; una interrupción
  debe mostrar misses decrecientes, nunca reiniciar fuentes verificadas.
- **LÍMITE VIVO DE LA CORRIDA SEMÁNTICA (2026-07-16)** — tras el arreglo, el
  cache conserva 702/714 fuentes detectadas; las 12 restantes no se publicaron.
  NVIDIA (70B/8B) y Ollama (4B/0.5B) quedaron bloqueados en la primera fuente
  larga bajo sus límites; los procesos fueron detenidos por PID exacto y no se
  declara un full scan semántico verde. El camino de reanudación sí quedó
  probado localmente y conserva los 702 hits. **Próxima acción:** repetir con
  un proveedor/modelo que responda al corpus; esa operación ya no debe repetir
  los hits ni borrar progreso.

- **CIERRE DE RESIDUOS Y PAQUETE PUBLICABLE A `main` (2026-07-16)** — los
  cinco cambios locales restantes se clasificaron por evidencia. Se conserva
  Vite 7.3.6 + plugin React 5.1.4 porque elimina 13 avisos del lock anterior;
  Node 22.22.2 queda reproducible y el shell entra en CI con instalación,
  auditoría y build. Los hooks portables de Claude/Codex quedan configurados y
  sus comandos verificados; el wrapper resuelve la raíz Git real de Codex con
  regresión, pero la carga requiere confiar la capa `.codex/` en el cliente.
  `.codex/config.toml` se mantiene
  local, ignorado y con modo 0600 porque contiene credencial/rutas/permisos del
  host. El export bruto "Diseño UI Atlas.md" se conserva solo como fuente
  histórica privada: su valor ya está destilado, queda fuera de Git/Graphify y
  en modo 0600 para no exponer URLs firmadas ni contaminar el grafo con alternativas
  obsoletas. **Próxima acción:** tras actualizar `main`, revisar/confiar los
  hooks del proyecto en Codex; rotar fuera del repo el client secret OAuth ya
  observado y relanzar el conector sin transportarlo por argv.

- **AUDITORÍA INTEGRAL ADVERSARIAL — CIERRE LOCAL Y SEMÁNTICO VERDE
  (2026-07-16)** — pre-mortem, revisión multidimensional y remediación
  ejecutados sobre seguridad, ejecución, API/WS, Telegram/HITL, Merkle,
  memoria/embeddings, MCP/grafos, Graphify/GraphRAG/Neo4j, CI/supply-chain,
  systemd/auditoría y Hermes oficial. Suite core, marcador computer-use,
  mypy, scanner Atlas, Merkle, quality GraphRAG estricto y regresiones dirigidas
  pasan; Crawl4AI real se omite por `.venv-scraping` ausente. GraphRAG se
  reconstruye por full scan, sin fallos/huecos/parciales/schema warnings, y el
  export Obsidian es transaccional. `atlas reality --run-checks` proyecta sus
  resultados al resumen de tests sin conservar estados `unknown`; los
  checkpoints semánticos verificados por fuente sobreviven a fallos posteriores
  mientras la publicación incompleta se revierte transaccionalmente.
  Hermes/VPS/proveedor/Telegram y Neo4j no
  se declaran vivos: `atlas reality` marca Hermes mock y no había credenciales
  ni servicio Neo4j. Informe canónico:
  `docs/design/audit_premortem_postmortem_2026-07-16.md`.
  **Próxima acción:** solo decisiones operativas separadas: rotar la credencial
  OAuth observada en argv, y si se autoriza desplegar/probar Hermes real,
  proveedor, Telegram o Neo4j. Cualquier commit futuro invalida el sello y exige
  reconstruir Graphify y proyecto Kuzu y reconectar MCP hasta `FRESH`.

- **F1 GRAPHIFY: SANGRADO CORTADO (2026-07-15, plan toasty-hatching-pillow)** —
  2 procesos runaway matados ~15:4x (monitor PID 927269 desde 00:31, capture
  PID 1278946). Causa raíz: el monitor nunca cargaba `.env` → fallback
  perpetuo `openai:gpt-4o-mini` contra el endpoint NVIDIA (que no lo sirve),
  contadores acumulados sobre log duplicado, y fallos jamás cacheados → 446
  docs reintentados sin fin (culpable principal:
  `docs/design/mcp_catalog_classified.yaml` 195KB vs presupuesto de salida
  4096). Fixes TDD (Sonnet, 23 tests rojo→verde, mypy --strict):
  `.graphifyignore`, `source .env` en el monitor, remapeo residual
  `gpt-*→meta/llama-3.3-70b-instruct`, contadores por delta persistido,
  `scripts/graphify_failure_guard.py` (3 fallos → auto-ignore idempotente),
  log en append con cabecera por corrida. El monitor NO se relanza en bucle
  (decisión del operador pendiente). Corrida limpia única lanzada para
  verificar que `graphify-out/quality-report.json` existe por fin.
  **CORRECCIÓN (revisión final, 2026-07-16 noche)**: la auditoría Codex
  RETIRÓ después `graphify-monitor-and-switch.sh`, `capture-llm-failures.sh`
  y `graphify-autoremediation.sh` (stubs fail-closed `exit 64`: usaban
  pgrep/kill workstation-wide y cambio implícito de proveedor). De F1 sigue
  vivo el trío `.graphifyignore` + `graphify_failure_guard.py` (con flock
  desde la revisión final) + el quality wrapper. La vía única y deliberada:
  `run-graphify-quality-pipeline.sh` en foreground. La decisión "¿monitor en
  bucle?" queda RESUELTA por retiro.
- **MISSION LAYER v0 + MISSION CONSOLE (2026-07-15, ADR-069)** — el export
  "Diseño UI Atlas.md" (65.640 líneas) destilado a `docs/inbox/
  atlas_foundry_v0_destilado_2026-07-15.md` + spec en `docs/design/
  mission_layer_self_construction_spec.md` (cumple el prerequisito de
  ADR-068). Construido y verificado en navegador real: 3 schemas Foundry
  (mission/receipt/soul_manifest), adapter puro ColdUpdate→Mission +
  receipt determinista, radar con 4 detectores (cazó en vivo el bucle real
  del vault Obsidian ×15 + 3 bucles de dep-bumps), endpoints read-only
  `/missions*`, y Mission Console como vista por defecto del shell.
  **RUTA DORADA CERRADA el mismo día**: `GoldenRoute` en
  `src/atlas/missions/golden_route.py` — fachada pública que ENVUELVE
  ColdUpdateManager (adopt-real): petición determinista sin LLM (v0 es
  doc-only, append bajo docs/; lo demás se rechaza honesto) → plan → patch
  unificado → worktree del motor → validación observable → aprobación
  humana registrada en Merkle ANTES de actuar (PermissionError sin ella)
  → apply con commit del motor → receipt (mission_receipt) + audit_ref.
  El xfail(strict) se quitó y el E2E corre verde sobre repo fixture (+ test
  de rechazo que aparca sin tocar main). Revisado por subagente Sonnet
  ANTES de commitear (ACEPTAR CON ARREGLOS): 2 bugs de borde reales
  arreglados — patch imposible sobre fichero de 0 bytes (hunk @@ -0,0 +1)
  y `_approval` fijado aunque el motor rechazara la transición — + guarda
  anti-symlink explícita, cada uno con su test. 72 tests del paquete
  afectado, mypy --strict limpio.
  **Próxima acción**: primera soul (devil_advocate) sobre el contrato
  soul_manifest ya existente; después, ampliar el vocabulario de peticiones
  de la ruta (hoy: append de línea a docs/).

- **CAMPAÑA x10 (2026-07-10, plan de-acuerdo-puedes-hacerlo-fizzy-sifakis):
  Fable planifica/audita, Sonnet implementa, el lazo mastica en paralelo** —
  - A: f2-6b despiezado en 3 items mecánicos (gen pares → runner juez vs
    baseline → informe con veredicto) tras el techo medido; graphiti-study
    reasignado. Cola del lazo: vault-wiring → f2-6b-1..3 → mem-1.
  - B: disección adopt-real de Graphiti/Zep (clon efímero borrado):
    2 patrones con sustancia — mem-1 (tiempo-del-hecho vs tiempo-de-sistema,
    alta en backlog) y mem-2 (invalidación por contradicción, SOLO propuesta
    con gate de auditoría); RRF/MMR descartados con evidencia
    (docs/inbox/graphiti_dissection_2026-07-10.md).
  - C: medición de memoria POR FIN reproducible — fetch idempotente del
    dataset (bug real de symlink HF cazado y arreglado) + **3ª aparición de
    'embedder ignora el env'**: eval_longmemeval medía SIEMPRE el stub
    (0.30/0.36); con el fix R@5=0.94 (n=50, fastembed) vs 0.35 stub.
    BenchmarkGate CABLEADO al batcher (TODO histórico) + bug to_dict()
    (señal siempre None) + tri-estado skipped accionable. ADR-057: canónico
    por caso de uso, puente diferido con trigger cuantitativo. multihop=0.0
    anotado como anomalía pre-existente.
  - D: grafo fase 2 — embeddings reales por env (ATLAS_GRAPH_EMBEDDER=
    fastembed, activado) + call-graph de Graphify (217 JSONs ya extraídos,
    prior art interno) cargado a Kuzu con tools graph_callers/graph_callees
    en el tronco. El vault-wiring es del LAZO (su item).
  - E: digestión cableada al tick diario — informes → candidatos de
    catálogo deterministas, dedupe fail-closed, status siempre 'candidato'.
    Sanity real: 128 hallazgos → 0 candidatos (sin señal cruzada aún, cero
    falsos positivos).
  - F: cuarentena CERRADA — git resolvió las deleciones como RENAMES (la
    reorg movía a docs/audits|outreach, no borraba); INDEX regenerado,
    validate limpio (216 entradas, 0 missing/orphans/expired).
  - Método: 7 subagentes (2 Explore + 1 Plan + 4 Sonnet impl) con specs
    cerrados y ficheros disjuntos; el facade (hotspot) en UN commit de
    wiring de Fable; cada diff auditado antes de commitear.
- **Mañana 2026-07-10 (post-reset): suite 7.5GB→1.9GB, hook vivo, ciclo
  autónomo completo verificado** —
  - **RSS de la suite RESUELTO** (2262de41): cache de proceso del modelo ONNX
    de fastembed (cada carga costaba ~500MB que el allocator no devuelve;
    verificado con gc: 0 instancias vivas y el RSS se queda). Medido con
    plugin RSS por test en scope de 4G: antes moría al 22% con 3.86GB; ahora
    la suite COMPLETA pasa (2957 tests) en 3:48 con pico 1941MB. earlyoom ya
    no tiene qué matar.
  - Hook híbrido + derive_test_cmd por targets EN VIVO (e97c8301, subagente
    Sonnet, verificado aquí): commits ya SIN --no-verify (gate de 6.9s).
  - La noche validó el ciclo entero SOLO: research 128 hallazgos (48 arXiv)
    → triage → ingesta → recall e2e; inbox amaneció vacío. Fix posterior:
    arXiv con frase entre comillas (ce0c388d; sin comillas all: hace OR).
  - Otra sesión (paralela) cerró tech-8 directo (c396cd2c) y dejó test_cmd
    con `python` a pelo → runner resuelve python/python3→sys.executable
    (b64078b3, 3ª aparición del bug).
  - AGENTS.md grafo-primero aplicado + backlog: status 'deferred' nuevo (los
    2 mcp-* diferidos dejan de quemar ticks) + runway repuesto con
    tmp-sandbox-sweeper y graphiti-absorption-study (91f68e37).
  - graphs.py: ingested_at determinista por posición (bab3f890; _latest_sha
    era flaky por empate — 1/2960 en la medición).
  - **PRIMERA CONVERGENCIA AUTÓNOMA (05:25 UTC)**: run_item
    tmp-sandbox-sweeper → success en 1 iteración → propuesta ColdUpdate
    ac39fe6b-702 sin intervención. Criterio de cierre de la campaña CUMPLIDO
    mecánicamente. La propuesta se RECHAZÓ con evidencia (cold_update.rejected
    en Merkle): era un duplicado — el sweeper existe cableado desde 6c0eeb5a
    y el item se dio de alta sin comprobar prior art interno (lección:
    curar backlog exige grep del prior art ANTES; el lazo ejecuta fielmente
    inputs malos). La fuga REAL de /tmp era tests CLI (120 dirs, cf481b2a).
  - Cierre total 2026-07-10 (orden del operador): worktrees filtrados
    retirados (trabajo huérfano del watcher archivado en
    atlas-cold-updates/orphan-mcp-subs-watcher-2026-07-10.patch),
    queue_state limpio, backoff persistente de adopción MCP + fail-fast
    sin secretos (f1c156a1 — ai.agenttrust acumulaba 530 stacktraces),
    trabajo sin commitear de la sesión paralela verificado y en main
    (trunk_prepare/preflight 79 tests; docs_index_audit que el triage
    carga en runtime; pin kuzu; lecciones), estado runtime del lazo a
    .gitignore, test_ssrf_bridge con DNS determinista (flaky real bajo
    carga). Quedan para el operador: mcpevo.md, scripts/hermes_local.sh,
    scripts/ollama_cpu.sh (dudosos, no los toco) y la reorg de docs en
    cuarentena. **SELLO: suite completa 2961 passed / 0 failed en 3:38
    (scope 4G) — verde entera, sin earlyoom, sin flaky.**
- **Ciclo investigación→acción CERRADO + grafo vivo automático + asesino
  SIGTERM identificado (2026-07-09/10, sesión curious-cuddling-forest
  fases 3bis.3/3bis.4/4)** —
  - atlas-graph promovido a raíz nativa del tronco (467ad720): el catálogo lo
    declaraba externo con `install: python -m ...` y `python` no existe en el
    sistema — el spawn perezoso moría en silencio; `is_read_only` ahora es
    estático sobre config (spawn perezoso + índice estático hacían fail-always
    en frío). Verificado vía trunk: graph_importers = grep (20/20).
  - Investigación→acción (e72c0edd): regla determinista research_*.md →
    docs/knowledge en docs_triage (que además ya no destruye la cabecera de
    INDEX.yaml) + `maintenance_knowledge_ingest_tick` (ATLAS_KNOWLEDGE_INGEST=1,
    diario, ingesta incremental por sha256 al sustrato ~/atlas-mcp/memory.db)
    + recall MCP e2e devolviendo el informe ingerido como primer hit.
  - TopicExpander curado (7399a6e3): consultas en inglés técnico corto +
    filtro determinista post-parse; con las MISMAS semillas 0 → 45 hallazgos
    reales (Graphiti/Zep etc.). arXiv en allowlist PENDIENTE de decisión del
    operador.
  - Grafo vivo automático (4533dd2d): `maintenance_project_graph_tick`
    (ATLAS_PROJECT_GRAPH=1) gateado por HEAD, sin LLM; regenera sobre COPIA +
    swap atómico porque el write-lock de Kuzu excluye lecturas de otros
    procesos (~9 min de apagón medido con build directo); build completo 530s,
    2017 nodos. Hook SessionStart: grafo primero para estructura.
  - scheduler.stop() cancela extra_cycles pendientes y despierta el sleep
    (Event; riesgo residual de la bomba recursiva cerrado).
  - nvidia_kimi RETIRADO con 2ª señal (404 'Function not found for account'
    en las 2 cuentas, curl por cuenta): asiento CN del trío re-mapeado a
    z-ai/glm-5.2 (prove-it en vivo, responde).
  - f2-6b: sus 3 strikes de backoff son de la era ciega (cero rastro en
    Merkle — no hay NI UN run_item suyo registrado); contador reseteado para
    un intento limpio ya auditado. tech-8 mantiene sus 3 (documentados:
    2× test_cmd >900s, 1× tests rojos).
  - **Asesino SIGTERM del pre-commit IDENTIFICADO con strace + journal:
    `earlyoom` (PID 1147)**. La suite completa pica ~7.5GB RSS; earlyoom
    manda SIGTERM al proceso más gordo al cruzar mem/swap 10% —
    `sending SIGTERM to process 598179 "python": badness 882, VmRSS 7577 MiB`.
    Explica el patrón 47-50% y por qué '10GB libres' no salvaba. Pendiente
    (decisión operador): hook con suite dirigida en vez de completa, y atacar
    el RSS acumulado de la suite.
- **Tronco como preflight por tarea (2026-07-09)** — `trunk_prepare(goal)`
  añadido al atlas-trunk: paquete compacto con recomendaciones de catálogo,
  resources, candidatos no conectados, env faltante, read-only tools y uso real
  externo cuando existe `ToolUsageCounter`. `AtlasCoder`/`ToolCoder` inyectan una
  sección fail-open de Trunk preflight antes del loop de código, sin Redis,
  LangGraph ni nuevas dependencias. Catálogo vivo curado en raíces Atlas
  (`atlas-memory`, `atlas-graph`, `atlas-knowledge`, `atlas-operating`) y regla
  de absorción temporal explicitada: clonar en `/tmp`/worktree, extraer patrón,
  borrar repo. 2026-07-10: el código quedó COMMITEADO (estaba solo en el
  árbol vivo; verificado 79 tests + mypy y cerrado en main). Pendiente:
  medir si el preflight aumenta uso real del MCP (necesita días de
  ToolUsageCounter — no cerrable hoy) y decidir si `trunk_exec_readonly`
  merece fase 2.
- **CAMPAÑA "construir directo, darle el conocimiento a Atlas" COMPLETA
  (2026-07-09, plan curious-cuddling-forest)** — inversión de método dictada
  por el operador: Claude construye directo lo que falta, Atlas recibe el
  conocimiento en su sustrato. 7 fases cerradas en un día:
  - F1 backlog: 5 items prio-1 marcados done con evidencia (5284751a).
  - F2 memoria: grafo vivo del proyecto en Kuzu + MCP atlas-graph (dd22bd30,
    verificado 19/19 vs grep) + ingesta de 44 docs vigentes/306 records al
    sustrato con fastembed dim=384 (d511fb76).
  - F3 harness: worktree efímero real para run_item (fusionadas 2 ramas
    claude/* que otra sesión dejó publicadas sin mergear), cola con backoff
    persistente, planning previo en ToolCoder, ToolCoder como backend de
    parallel_coder, repo-map automático (6c0eeb5a).
  - F4 investigación: panorama_scout+topic_expander cableados al scheduler —
    semillas desde las lecciones recientes (descubrimiento abierto), informe
    diario a docs/inbox/ como propuesto; primer informe autónomo real
    generado (822c7a84; fix de URL-encode encontrado en la pasada en vivo).
  - F5 inferencia: smoke diario de cadena (probe_provider + ProviderChainSmoke,
    df3746ee); en vivo: 9 ok, 3 rate-limited, nvidia_kimi 404 (marcado, no
    retirado — decisión de operador con segunda señal).
  - F6 MCP: sampling/elicitation/roots verificados INCONDICIONALES en el
    tronco real (el condicional del plan ya no existía) — sin cambios.
  - F7 daemon: suite completa 2921/2922 en solitario, atlas-core.service
    reactivado (enabled, 0 reinicios), ATLAS_RESEARCH+ATLAS_PROVIDER_SMOKE
    en .env; primer tick con research+smoke auditados en Merkle; run_item
    en curso al cierre (LLM L2, convergencia pendiente de observar).
- **INCIDENTE MAYOR RESUELTO (2026-07-09): bomba de procesos recursiva del
  lazo** — la suite que el tick corre en su worktree hereda el env del daemon
  (ATLAS_SELF_BUILD=1); un test que arrancaba el scheduler real (más un hilo
  que sobrevivía a stop()) disparaba OTRO run_item real → cascada de
  worktrees git + pytest anidados (13 worktrees/12 pytest la primera vez;
  reproducido en producción tras reactivar el daemon). Corte estructural
  ATLAS_NESTED_TEST_RUN en emisores (ToolCoder/AtlasCoder/ValidationRunner/
  evo) y receptores (los 3 ticks del facade) — 041f3972. Relacionados: /tmp
  tmpfs 4G lleno por sandboxes huérfanos de ToolCoder (~487M c/u, barrido +
  exclusión .claude/.cursor) y stacer --hide a 62% CPU en autoarranque
  (desactivado) — causa real de los cierres de sesión de escritorio, no
  Atlas ni la contención con Ollama (atribución previa corregida).
- **Lazo de automejora v0.1 COMPLETO** (detect→judge→propose→verify→apply→learn):
  las 4 piezas del roadmap "juicio real" 2026-07-04 quedaron cableadas en
  producción el 2026-07-08 (antes: construidas+testeadas pero 0 callers).
- **Autobuild DESTAPADO (2026-07-09)**: 4 estranguladores apilados encontrados
  ejecutando el tick directo — scheduler no arranca sin
  `ATLAS_MAINTENANCE_SCHEDULER=1`; techo 10 turnos (→30 + env); descarte de
  trabajo al agotar turnos (→salva vía tests); timeout tests 120s vs suite 7min
  (→env). El lazo en sí FUNCIONA (verificado en vivo 2 veces).
- **Fusión Graphify→Obsidian→Kuzu COMPLETA de punta a punta (2026-07-09)**:
  grafo de atlas-core/src generado (4206 nodos, 154 comunidades, 0 tokens LLM),
  vault Obsidian (4360 notas) digerido por nuestro parser, cargado en Kuzu
  (26.392 links, 0 unresolved, queries Cypher OK). Salida:
  `~/proyectos/atlas-graph/graphify-out/`. Diseño: `docs/inbox/graphify_obsidian_kuzu_fusion.md`.
- Daemon `atlas serve` requiere relanzarse con el scheduler encendido (receta
  en la entrada 2026-07-09); cola: `docs/backlog.yaml` (obsidian_vault_parser
  ya HECHO a mano — pendiente de marcar done por el operador).
- Próxima acción: aprobar/rechazar propuestas ColdUpdate del tick; misión
  bitemporal Kuzu sobre el gancho `ingested_at`; batch-insert en el cargador.

✅ **SelfBuildRunner fuera del árbol vivo (2026-07-08)** —
`run_item` y `run_item_with_evolution` ejecutan ToolCoder y generan el patch en
worktrees git efímeros (mismo patrón que `_evaluate_candidate_in_worktree` /
ColdUpdateBatcher); `_revert_new_changes`/`_git_status_lines` eliminados — el
revert sobre el árbol vivo podía destruir trabajo concurrente sin commitear
(misma clase que el incidente "9 YAML regenerados"). El patch ahora incluye
ficheros NUEVOS (`git add -A` dentro del worktree efímero). Invariante intacto:
origin="self_audit" → HITL siempre. `tests/test_self_build_runner.py` green
(incl. regresión: fichero sucio del operador durante el run sobrevive a un
run_item fallido); mypy `src/atlas/` clean.

✅ **Dual audit MCP + Atlas runtime (2026-07-07)** —
`docs/governance/audits/audit_complete_premortem_2026-07-07.md` sección B+C cerrada:
manifest memory drift (`recall_multihop`/`shred`), catálogo skills, read_only trunk,
`.cursor/mcp.json`, path `.claude/skills`, docs stale marcados. MCP smoke stdio
desde Codex OK; `trunk_recommend_stack` y `trunk_health` exponen shortlist/diagnóstico
2026 sin instalar terceros; Cursor config preserva `src` + venv `site-packages`.
Runtime: `pytest` green, mypy clean, browser ready, Merkle OK. LLM: groq smoke OK;
openrouter rate-limited; Hermes sin `HERMES_BASE_URL` → local/mock. Dependency
floors accepted: `pyyaml>=6.0.3`, `cryptography>=49.0.0`, `litellm>=1.89.0`.

## Entradas

- **2026-07-09 — Matriz de patrones arquitectónicos 4×5 COMPLETA**
  - Documento: `docs/design/architectural_patterns_matrix_2026-07-08.md` (versión 2.0).
  - Criterio de aceptación cumplido: matriz completa con patrones arquitectónicos (no features) para Aider/Cursor/Codex/Claude Code.
  - Priorización basada en presión real detectada en delegaciones 2026-07-08.
  - Cada patrón incluye código de referencia o paper verificable.
  - Validación cruzada con invariantes Atlas (D2, Merkle, AST Guard).
- **2026-07-09 — Autobuild destapado + fusión Graphify/Obsidian/Kuzu completa**
  - Tick self-build invocado DIRECTO (sin daemon): pipeline entero corre;
    falló primero por techo de turnos, luego por timeout de tests — ambos
    arreglados (commits 015ef22c + este). Cuarto estrangulador documentado
    en `workspace/lessons/autobuild_unthrottled_2026-07-09.yaml`.
  - `ToolCoder`: turnos 10→30 (`ATLAS_TOOL_MAX_TURNS`), salvamento de
    ediciones al límite, timeout tests configurable
    (`ATLAS_TOOL_TEST_TIMEOUT_S`). `SelfBuildRunner`: nivel configurable
    (`ATLAS_SELF_BUILD_LEVEL`). Receta serve completa:
    `ATLAS_SELF_BUILD=1 ATLAS_MAINTENANCE_SCHEDULER=1 ATLAS_MAINTENANCE_POLL_S=900 ATLAS_SELF_BUILD_LEVEL=L2`.
  - Graphify corrido entero (AST local, sin API key): god-nodes = Orchestrator/
    MerkleLogger/SSRFBridge — coincide con la arquitectura real. Parser
    obsidian_vault con fix multilínea; `obsidian_to_kuzu.load_vault_into_kuzu`
    nuevo (schema-first, MERGE idempotente, gancho bitemporal).
  - Limpieza: 2 worktrees self-build efímeros + rama obsidian-parser borrados;
    `atlas-cold-updates` se conserva (patches ColdUpdate);
    `atlas-codegraph` (detached, procedencia desconocida) pendiente de decisión.

- **2026-07-09 — Ollama local ARREGLADO: fix permanente completado**
  - Fix permanente aplicado (2026-07-09 00:XX): `sudo systemctl edit ollama`
    → `[Service] Environment="CUDA_VISIBLE_DEVICES="` → restart. GTX 960M
    ahora corre en modo CPU (sin CUDA), sin crashes. Verificado:
    `systemctl show ollama -p Environment | grep CUDA_VISIBLE_DEVICES=` ✓
  - `ollama_local` del hub REVIERTE a puerto 11434 (sistema, permanente).
    Daemon CPU (127.0.0.1:11435, scripts/ollama_cpu.sh) ya NO necesario.
  - Verificación: Ollama responde en 11434, qwen2.5-coder:7b disponible,
    41 tests de inference_hub pasan en 6.55s.
  - Notas: el workaround CPU fue la prueba VIVA de que el problema era GPU↔runner,
    no de hardware (primero visto en 2026-07-08); fix del operador eliminó la
    dependencia temporal. Última barrera al fallback: vencida.

- **2026-07-08 — Absorción slice 1 (Aider/Codex/Claude-harness → Atlas)**
  - `InferenceRequest.wait_for_ratelimit` + `_infer_raw` re-camina la cadena
    (hasta 2 veces, espera ≤120s al cooldown más próximo) en vez de devolver
    all_failed; ToolCoder lo activa (lazo largo). 2 tests nuevos (41 verdes
    en test_inference_hub_real.py).
  - Repo-map (patrón Aider) ENCENDIDO por defecto en `atlas code`: estaba
    cableado a nivel de librería y el CLI nunca lo pasaba (dormido). Flag
    `--repo-map/--no-repo-map`; candidatos = `git ls-files '*.py'`; el builder
    recorta a 4KB por relevancia. mypy limpio; 130 tests coders/CLI verdes.
  - Base para lo siguiente: la encuesta harness-engineering 2026-06-27 (9
    arneses, 25 técnicas) es el mapa de absorción; prioridad dictada por
    evidencia de presión real, no por catálogo.
  - BLOQUEO que requiere al operador: el runtime de Ollama está COLGADO a
    nivel de sistema — ambos modelos locales (llama3.1:8b y qwen2.5-coder:7b
    recién descargado) crashean con "signal arrived during cgo execution" con
    10GB de RAM libre. El servicio es root (pid 2476); arreglo probable:
    `sudo systemctl restart ollama` (o el unit que corresponda). Sin esto,
    Atlas no tiene último recurso local y las delegaciones dependen 100% de
    tiers gratis rate-limitados.

- **2026-07-08 — Delegación real a Atlas destapa cadena de proveedores podrida**
  (sesión Fable 5; manía delegar-en-Atlas aplicada con presión real).
  - Delegado a `atlas code --engine tool` (worktree aislado `../atlas-codegraph`)
    el slice 1 del grafo de código. La PRESIÓN destapó, con evidencia en vivo:
    (1) `groq_deepseek_r1` decomisionado por Groq — retirado de DEFAULT_PROVIDERS;
    (2) `openrouter_hermes_405b` y `openrouter_liquid` muertos (NotFound) — retirados;
    (3) el fallback aterrizaba requests CON tools en modelos sin tool-calling
    (groq_compound) y el coder moría — arreglado: `Provider.supports_tools` +
    filtro en `_infer_raw` + marcado EN CALIENTE al ver "tool calling not
    supported" (3 tests nuevos, 39 verdes en test_inference_hub_real.py);
    (4) threshold del LessonRecaller en codegen: 0.8 no recuperaba NADA — medido
    en vivo (relacionadas 0.55-0.69, ajenas ≤0.47) y fijado a 0.55 SOLO en el
    camino avoid_patterns del facade (inmune intacto).
  - Conocimiento inyectado a Atlas: 3 lecciones corroboradas en
    `workspace/lessons` (orden de docs, run_item muta árbol vivo, multihop≠grafo
    + Kuzu libre para KG temporal); recall verificado con el threshold nuevo.
  - Resultado de 5 delegaciones: Atlas ESCRIBIÓ un scripts/code_graph.py
    funcional (verificado contra src real: 199 módulos, 464 aristas; fan-in
    top: merkle_logger 38, contracts 26) en `../atlas-codegraph`; sus tests
    quedaron rotos porque las iteraciones fueron saboteadas primero por rate
    limits y luego por /tmp lleno (3.5GB de temporales pytest — limpiado).
    Techo observado: el cuello es PROVEEDORES+infra, no el arnés.
  - ollama: qwen2.5-coder:7b descargado; ollama_local cambiado a llama3.1:8b
    (el config apuntaba a un modelo inexistente — el último eslabón del
    fallback fallaba justo cuando más se le necesitaba).
  - Verificación final (tras limpiar /tmp): suite COMPLETA `2871 passed,
    2 skipped` (exit 0) + mypy limpio + 39 verdes en test_inference_hub_real.

- **2026-07-08 — Grafo de conocimiento de docs (slice 1, nativo)**
  - `scripts/docs_graph.py`: grafo real desde `[[wikilinks]]` (convención que ya
    vivía en membrana/; resolución por stem exacto Y por prefijo) + mdlinks.
    Consultas: salientes/backlinks/rotos/huérfanos. Sin Obsidian ni Graphiti
    como dependencia, pero markdown+wikilinks = vault compatible.
  - Señal real del primer build: 21 enlaces rotos accionables (docs vigentes;
    archive filtrado) incl. OSMs referenciados nunca escritos (OSM-001/002/
    011/016/017/020/021/034…) y **106 docs vigentes sin ningún enlace**.
  - Autodefensa: `docs_graph_drift` en sanitation_audit y en PreflightGate.
  - 7 tests nuevos (25 en el bloque docs-tooling). Slice 2 propuesto (backlog):
    fusionar docs+memoria en Kuzu (ya dependencia core) con aristas
    bitemporales, patrón Graphiti/Zep (arXiv:2501.13956).
  - Hallazgo colateral: 15 worktrees huérfanos de ColdUpdate (1.7 GB) en
    `../atlas-cold-updates/` — fuga de limpieza; chip/tarea creada.
  - Verificación: suite COMPLETA `2868 passed, 2 skipped` (exit 0) + mypy
    limpio (216 ficheros).

- **2026-07-08 — Orden real de docs/: reorganización + índice máquina + inbox/triage**
  (sesión Fable 5, aprobado por el operador: "todo incluida reorganización").
  - Reorg física con `git mv` (historia preservada): `reference/` disuelto →
    `decisions/adr` (35 ADRs) + `decisions/gates` (16 sellos) + `operations/`
    (USAGE, runbook, prometheus, seguridad) + `compliance/` + `outreach/`
    (paper+posts) + `audits/` (26 auditorías + 9 reports). `design/`,
    `membrana/`, `governance/` (REPO_STANDARD+CAPABILITIES), `archive/`,
    `superpowers/`, `skills/`, `demo/` intactos (varios son load-bearing).
    Todas las referencias de código/tests/docs actualizadas; REPO_STANDARD §1
    reescrito con la taxonomía nueva.
  - `docs/INDEX.yaml` (210 entradas): índice MÁQUINA con type/status/verified.
    Generador+validador `scripts/docs_index_audit.py` (--write preserva campos
    curados; --strict para gates). 6 tests.
  - `docs/inbox/` + `scripts/docs_triage.py`: dedupe por hash → reglas
    deterministas → LLM barato (fail-open a `hold`); `--apply` mueve e indexa
    como `status: propuesto` (la promoción a `vigente` es humana). 6 tests.
  - El orden se defiende solo: desviaciones árbol↔índice entran en
    `sanitation_audit.py` y en el `PreflightGate` del lazo (el daemon las ve
    cada hora antes de gastar LLM).
  - Verificación (2026-07-08 ~14:3x): suite COMPLETA `2862 passed, 2 skipped`
    (exit 0) + `mypy src/` limpio (216 ficheros) + radar sin desviaciones de
    índice ni referencias stale tras la reorg.

- **2026-07-08 — Hermes local en PC: Telegram + twin sin VPS**
  - Hermes Agent oficial (`~/.hermes/hermes-agent`, v0.18.2) quedó instalado
    localmente desde el repo de Nous.
  - `ATLAS_DISABLE_TELEGRAM=1`: el dueño del bot vuelve a ser Hermes; Atlas ya
    no hace long-polling sobre el mismo token.
  - `HERMES_KANBAN_TRANSPORT=local`: el canal Atlas -> Hermes deja de depender
    del SSH al VPS; `KanbanBridge` usa el `hermes kanban` local cuando existe.
  - Atlas ya delega de verdad por `HermesKanbanAdapter`: el orquestador deja de
    duplicar delegaciones exitosas en `OfflineQueue` cuando el board de Hermes
    ya es la fuente durable.
  - Verificación live 2026-07-08 13:18 CEST: `atlas reality --json` reporta
    `hermes.mode=kanban_local`; una delegación real creó la tarea
    `t_57d5aa9f` en Hermes y el worker local la completó con éxito.
  - Telegram verificado en el PC: `hermes-gateway.service` quedó activo y
    `hermes send --to telegram` entregó mensaje al home channel `656190718`.
  - Hardening 2026-07-08 13:25 CEST: NIM quedó como proveedor primario real en
    `~/.hermes/config.yaml` porque OpenRouter agotó crédito y Gemini falló en
    generación real aunque `doctor` validara conectividad básica. Groq quedó
    registrado como proveedor opcional pero no activado porque esta clave hoy
    sí responde por API, pero la cuenta on-demand no soporta el tamaño de
    contexto mínimo que Hermes envía (413 TPM) y por eso no se dejó en la
    cadena automática de fallback.
  - La memoria compartida NO se duplicó: el aprendizaje mutuo sigue viviendo en
    el `LessonStore` unificado `workspace/lessons/`, que ya era la autoridad.

- **2026-07-08 — Cableado v0.1 del lazo de automejora** (sesión Fable 5).
  - `Orchestrator.cold_update()` inyecta `RootCauseClassifier` (¿fallo ambiental
    o causado por el diff?) con hub diferido `_DeferredHub` (fail-open).
  - `MaintenanceFacade.maintenance_cold_update_batcher()` inyecta
    `BatchPremortemGate` (riesgo de COMBINAR antes de pagar la suite) y
    `FailureLessonSink` → LessonStore `workspace/lessons/` (el lazo por fin
    APRENDE de sus fallos: antes las exclusiones de bisección no dejaban lección).
  - Tick de autoconstrucción extraído a `maintenance_self_build_tick()` con
    `PreflightGate` delante (CVEs+radar, determinista): si no pasa, salta el
    ciclo con evidencia Merkle `self_build.preflight_blocked` (nunca silencioso).
  - Contrato fijado en `tests/test_self_improvement_wiring.py` (6 tests).
  - `scripts/sanitation_audit.py`: 4 clasificaciones PARK/KEEP retiradas
    (dejaron de ser 0-importer al cablearse).
  - Verificación (2026-07-08 12:2x): suite COMPLETA `2842 passed, 2 skipped`
    (exit 0) + `mypy src/` limpio en 216 ficheros. Baseline pre-cambios:
    2834 passed, 2 failed.
  - Nota: baseline previo de la suite completa: 2834 passed, 2 failed — ambos
    fallos eran la AUSENCIA de AGENTS.md/WORK_LEDGER.md (cuarentena), no código.
