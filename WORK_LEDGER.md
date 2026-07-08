# WORK LEDGER — estado vivo (WHERE + próxima acción)

Regenerado desde cero el 2026-07-08 (los docs raíz previos fueron puestos en
cuarentena por el operador; historia anterior en `git log` y `docs/archive/`).
Disciplina: entradas nuevas ARRIBA, una línea de estado por frente, ledger corto
(≤40 entradas; al superar, plegar lo viejo a `docs/archive/`). Verificar antes
de escribir: `atlas reality --json`.

## WHERE

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
