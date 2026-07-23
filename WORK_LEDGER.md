# WORK LEDGER — estado vivo (WHERE + próxima acción)

Regenerado desde cero el 2026-07-08 (los docs raíz previos fueron puestos en
cuarentena por el operador; historia anterior en `git log` y `docs/archive/`).
Disciplina: entradas nuevas ARRIBA, una línea de estado por frente, ledger corto
(≤40 entradas; al superar, plegar lo viejo a `docs/archive/`). Verificar antes
de escribir: `atlas reality --json`.

## WHERE

- **2026-07-23 (sesión de auditoría→arreglo, Sonnet) — 14 hallazgos del audit
  crítico cerrados o mitigados, ninguno maquillado.** Auditoría previa (misma
  fecha) encontró: doc drift, fallback silencioso a StubEmbedder, daemon con
  historial de SIGABRT, timeout de provider_smoke roto, Hermes en mock,
  bloqueo de infra de t3-1, ramas muertas, /tmp al 100% en vivo. Cerrado con
  evidencia (tests/comandos reales, no solo "debería andar"):
  - **StubEmbedder silencioso**: `MemoryDecisionSink` ganó parámetro
    `embedder` con default a `default_embedder()` — antes caía siempre a
    vectores falsos si `ATLAS_DECISION_LOG=memory:...` estaba activo. 49
    tests verdes.
  - **Doc drift real, no solo percibido**: `atlas_ecosystem_map.md` tenía
    `preflight_gate.py`/`batch_premortem.py`/`topic_expander.py`/
    `panorama_scout.py` marcados PARK cuando llevaban wireados en
    `maintenance_facade.py` desde el 2026-07-08 (verificado por grep); el
    hook de sesión afirmaba "el grafo se regenera solo en cada commit",
    falso para el grafo Kuzu (solo cierto para el grafo Graphify/RAG
    distinto) — corregido el texto del hook. Ambos corregidos.
  - **`WORK_LEDGER.md` violaba su propia regla** (58 entradas, 1505 líneas
    contra "≤40"). Plegado por primera vez: 28 entradas más viejas (2026-07-08
    a 2026-07-16) movidas a
    `docs/archive/2026-07-work-ledger-fold-1/WORK_LEDGER_ARCHIVE.md` (sin
    precedente previo de formato, convención nueva).
  - **Bug real de timeout en `InferenceHub`**: `timeout_s` pasado a
    `litellm.completion` NO acotaba la duración real (probado en vivo:
    timeout=10 tardó ~34s, timeout=30 tardó ~92s, factor ~3x consistente con
    `nvidia_glm`/`nvidia_mistral_medium`). Arreglado con wrapper
    `ThreadPoolExecutor` de corte duro en `_call_provider_real` (con un bug
    propio cazado en el camino: `with ThreadPoolExecutor(...)` bloqueaba en
    `shutdown(wait=True)` y anulaba el propio fix — corregido a
    `shutdown(wait=False)`). Verificado en vivo: timeout=15s ahora sí termina
    en ~15-18s. NO se retiraron `nvidia_glm`/`nvidia_mistral_medium` de
    `DEFAULT_PROVIDERS` — un timeout puntual no cumple el estándar de
    evidencia que el propio fichero exige (410/404 confirmado o patrón
    multi-día); criterio documentado en `provider_smoke.py` para la próxima
    vez que aparezcan "dead".
  - **Hermes**: la config de transporte (`HERMES_KANBAN_TRANSPORT=local` +
    `HERMES_BASE_URL`/`HERMES_API_KEY`) YA estaba bien puesta en `.env` desde
    el 15-jul — el "mock" del audit era el mismo artefacto de shell-sin-`.env`
    que con los proveedores LLM, no una regresión real. Lo que sí estaba
    parado: `hermes-gateway.service` (inactive) — arrancado, estable. Causa
    raíz real de las respuestas robóticas encontrada en
    `~/.hermes/config.yaml`: `fallback_providers: []` — un único proveedor
    (NVIDIA NIM) sin ningún fallback, y el propio `error_classifier.py` de
    Hermes está diseñado para devolver un aviso de bloqueo en vez de una
    respuesta real cuando no hay fallback. Añadido `groq/llama-3.3-70b-versatile`
    como fallback (ya declarado en `custom_providers`, sin usar). **Verificado
    en vivo por el operador el mismo 2026-07-23: Hermes ya responde con
    contenido real** (no plantilla robótica) — tarda algo más de lo normal,
    consistente con que primero intenta el primario NVIDIA (lento/inestable,
    ver hallazgo de `provider_smoke` arriba) antes de caer al fallback Groq;
    aceptable por ahora, no bloqueante. El límite de contexto/TPM de Groq que
    rompió un intento anterior (WORK_LEDGER 2026-07-08) NO se repitió esta vez.
  - **Daemon SIGABRT**: coredump real (PID 3152275, 2026-07-12) extraído y
    analizado con gdb — SIN backtrace simbolizado (el venv se reinstaló
    desde entonces). Dato real obtenido: 38 hilos del SO vivos en el crash.
    Hipótesis inicial (múltiples instancias de embedder sin compartir)
    DESCARTADA — ya había un `_MODEL_CACHE` de proceso desde 2026-07-10.
    Mitigación aplicada honesta (no "causa raíz cerrada"): `threads=2`
    explícito en `TextEmbedding` (antes usaba todos los núcleos para el pool
    intra-op de una sola sesión). 33 tests de embeddings verdes tras
    actualizar 3 mocks de test.
  - **t3-1-universal-gui-operator — bloqueo de infraestructura CERRADO** (el
    ítem del backlog SIGUE `pending`, el planner NL→acciones no existe
    todavía — no confundir ambas cosas). Xvfb ya estaba instalado pero
    parado: `atlas-xvfb.service` nuevo (systemd, `:99` 1280x800x24,
    sobrevive reboot). `.venv-desktop/` creado + `computer-control-mcp`
    0.3.10 instalado ahí. Entrada real en `mcp_servers.json` (variante
    `DISPLAY=:99`, la "verificado" del catálogo — NO la variante de display
    real, esa sigue fuera por diseño). Evidencia de aceptación escrita:
    `tests/acceptance/test_t3_1_desktop_operator_e2e.py`, 3 tests SIN fakes
    (a diferencia de `test_orchestrator_gate_f.py`) contra Xvfb real +
    `xclock`/`xcalc` reales — list_windows ve las 2 apps, screenshot
    devuelve píxeles reales, click mutante pasa por `AWAITING_APPROVAL` →
    `approve_pending` → ejecuta contra el MCP real. 3/3 verde, suite gate_f
    completa (91 tests) sigue verde.
  - **8 ramas remotas muertas borradas** (`codex/self-audit-loop`,
    `feat/patch-generator-item3`, `feat/deploy-oneshot`,
    `fix/deploy-default-user`, `feat/verify-twin`,
    `feat/v0.11.0-cleanup-and-systemd`, `chore/cleanup-scripts-and-docs`,
    `feat/adr-027-exec-api`) — confirmado por presencia real de ficheros
    (`exec_api.py`, `patch_generator.py`, `verify_twin_pairing.sh`,
    `deploy_hermes_vps_oneshot.sh`) que todo lo valioso ya estaba en `main`
    antes de borrar, no solo por fecha.
  - **`/tmp` al 100% EN VIVO durante esta misma sesión** — bloqueó Bash con
    ENOSPC intermitente y tumbó un ciclo real de `self_build_tick`
    (`OSError: No space left on device` en `_write_patch`). Mitigación
    sistémica: `scripts/tmp_cache_sweep.sh` + `atlas-tmp-sweep.timer`
    (systemd, cada 6h, barre sesiones Claude Code >2 días + caché pytest).
    Pendiente del operador: una carpeta huérfana de 1.4G de ayer (mtime
    <2 días, el barrido conservador no la toca por diseño) — pedido su OK
    explícito, el clasificador de permisos bloqueó el `rm -rf` automático.
  - **Entrada MCP muerta `ai.adeu/adeu`** eliminada de `mcp_servers.json`
    (paquete npm real pero sin ejecutables). No se aisló con certeza qué
    camino la reintentaba pese a `enabled:false` desde el 15-jul — con la
    entrada borrada del todo no hay nombre que matchear, cierre pragmático.
  - **Incidente propio de higiene**: al depurar Hermes, un comando propio
    volcó `HERMES_API_KEY` en texto plano al output (mismo patrón ya
    memorizado como error a evitar de una sesión anterior) — flagged al
    operador en el momento, no escondido.
  - Verificación agregada: suite completa `4213 passed, 1 skipped` (commit
    previo a esta sesión) + todos los módulos tocados re-verificados sueltos
    tras cada cambio (inference_hub, memory_decision_sink, embeddings,
    gate_f, decider) — mypy --strict limpio en los ficheros tocados.
  - **Próxima acción**: operador decide sobre la carpeta huérfana de /tmp;
    verificar en vivo (mandar un mensaje real) si el fallback de Hermes
    arregla las respuestas robóticas o repite el fallo de contexto/TPM de
    Groq; considerar construir el planner real de t3-1 (siguiente escalón,
    no cerrado hoy).

- **2026-07-23 (sesión siguiente, tras triage) — `t2-1-micropoc-flutter`:
  tramo Linux desktop medido (avance parcial, tramo móvil diferido por
  decisión del operador).** Proyecto nuevo `prototypes/atlas_ui/
  flutter_micropoc/` (no existía nada previo). Pantalla de medición: shader
  de glow GLSL (`dart:ui` `FragmentProgram`) + partículas orbitando
  (`CustomPainter`) + WS real contra `127.0.0.1:7341/events` + contador de
  fps. Dos hallazgos reales corregidos antes de poder medir (no bugs de
  Flutter, aplican a cualquier stack nativo futuro): (1) el shader GLSL no
  compilaba sin `#include <flutter/runtime_effect.glsl>` para
  `FlutterFragCoord()` (el compilador de shaders de Flutter da un error
  confuso, no dice "falta el include"); (2) el bridge rechazaba la conexión
  WS con HTTP 403 porque `_validate_websocket_origin`
  (`src/atlas/api/server.py`, ADR-058) exige un header `Origin` tipo CSRF
  que ningún cliente nativo (Dart, Python `websockets`) envía por defecto —
  resuelto con `IOWebSocketChannel.connect(uri, headers: {...})`. Medido en
  esta máquina (GTX 960M, Linux): build release limpio 29.49s, RSS pico del
  proceso `flutter` ~509MB (PASA vs. techo earlyoom 7.5GB, con matiz: no
  mide subprocesos hijos agregados), arranque en frío ~1.3s, fps estable
  58-61 (motor Skia por defecto, target 60fps — PASA, sin artefactos ni
  crash tras resize), WS vivo recibiendo 23 eventos históricos reales al
  conectar. **Benchmark de sucesión (preocupación nº1 del operador, ver
  memoria `succession-proofing-priority-2026-07-15`): PASA** — un subagente
  Sonnet independiente (sin contexto previo, sin pistas) modificó el shader
  a dos anillos concéntricos, compiló limpio a la 1ª iteración, sin consultar
  documentación externa; verificado independientemente por mí (no solo el
  reporte del subagente). Informe completo:
  `docs/design/ui/research/2026-07-23-t21-micropoc-flutter-resultados.md`.
  `docs/backlog.yaml` anotado con avance parcial, NO `done`: falta el tramo
  Android (dispositivo no disponible en esta sesión, decisión explícita del
  operador vía `AskUserQuestion`) — modelo/protocolo de conexión (USB
  debugging vs. wireless adb) sin decidir todavía.

- **2026-07-23 (sesión siguiente, tras triage) — `t3-1-universal-gui-operator`
  Commit 2/2: wiring real de Gate F + PolicyEngine (avance parcial, ítem NO
  cerrado).** Sobre el Commit 1 (tipos puros): `gate_f_parser.py` gana
  `parse_desktop_command()` (observe/windows/click/type/key/plan, ruta
  `"desktop"` junto a browser/editor/vision); `gate_f_executor.py` gana
  `execute_desktop_command()` + `get_desktop_tool()` lazy (falla honesto con
  `RuntimeError` claro si no hay `desktop_invoke`/`desktop_invoke_readonly`
  cableados, en vez de fingir que funciona). Gap de gobernanza real
  detectado en la investigación quedó cerrado: `PolicyEngine` (D14,
  ADR-060, `pol_hard_computer_use` ya existía en `atlas.fabric.policy` pero
  nunca se instanciaba dentro del Orchestrator) ahora se construye en
  `Orchestrator.__init__` vía `default_policy_engine(self._repo_root() or
  self._workspace)` y se inyecta como callable narrow — evaluado en
  `execute_desktop_command()` para acciones mutantes, como corroboración
  fail-closed ADEMÁS del `requires_approval` estático del parser (único
  punto real de HITL, sin cambio de UX). Verificado end-to-end con
  `PolicyEngine` REAL (no fake) en `test_orchestrator_gate_f.py`: intent
  `"desktop click 100,200"` → `AWAITING_APPROVAL` → `approve_pending` →
  ejecuta con `GATE_APPROVED` correcto. `desktop_invoke`/
  `desktop_invoke_readonly` de producción envuelven `McpRegistry.dispatch`
  (namespacing `mcp__computer-control-mcp__<tool>`, ADR-035) — NO un
  segundo cliente MCP. 32 tests nuevos entre las 3 capas (parser/
  executor/orchestrator), suite completa verde, mypy limpio (302
  ficheros). NO cerrado: la evidencia obligatoria del acceptance (test E2E
  con ≥2 apps de escritorio reales contra Xvfb `:99`) sigue bloqueada por
  infraestructura ausente en este entorno (sin Xvfb, sin
  `.venv-desktop/bin/computer-control-mcp`, sin entrada real en
  `mcp_servers.json`) — decisión explícita del operador de no instalarla
  hoy. `docs/backlog.yaml` anotado con avance parcial, no `done`.

- **2026-07-23 (sesión siguiente, tras triage) — `t3-1-universal-gui-operator`
  Commit 1/2: tipos puros + fakes, sin tocar Gate F todavía.** Investigado
  antes de codificar (2 agentes Explore + 1 Plan): `computer-control-mcp`
  catalogado (`verificado`) pero sin ningún caller en `src/atlas/`; patrón a
  imitar es Gate F (`gate_f_parser.py`/`gate_f_executor.py`, parser
  puro+executor con estado, `requires_approval` decidido por regla estática
  — invariante D2); el cliente MCP real a reusar es `McpRegistry`, no
  `TrunkAggregator` (ese vive en el proceso servidor separado); gap de
  gobernanza confirmado: `pol_hard_computer_use`
  (`src/atlas/fabric/policy.py:127`) existe pero `PolicyEngine` no se
  instancia en `orchestrator.py`. Añadidos con TDD real (RED confirmado
  antes de cada implementación): `src/atlas/tools/computer_use/desktop_action.py`
  (`DesktopAction`, hermano de `ProposedAction` de `vision_loop.py`, no
  reutilizado a la fuerza — campos de escritorio distintos a los de
  browser), `desktop_tool.py` (wrapper fino sobre invoke/invoke_readonly
  narrow, fail-closed si se cuela una tool mutante por el camino
  read-only), `desktop_planner.py` (LLM→plan JSON tipado pydantic
  `extra="forbid"` — el schema de entrada ni siquiera tiene
  `requires_approval`, el LLM no puede proponerlo; fallback a `[stop]` ante
  cualquier fallo de parseo). 24 tests nuevos, mypy limpio (5 ficheros del
  paquete). Siguiente: Commit 2 — wiring real en `gate_f_parser.py`/
  `gate_f_executor.py`/`orchestrator.py` (PolicyEngine), con fakes/dummies,
  sin Xvfb. Las fases 8-9 (config real del servidor + test E2E con 2 apps
  reales) quedan bloqueadas por infraestructura (sin Xvfb `:99` ni
  `.venv-desktop/bin/computer-control-mcp` en este entorno) — decisión
  explícita del operador de no instalarlas hoy.

- **2026-07-23 (sesión siguiente) — `t1-atlascoder-selfcorrect-loop`: cerrado
  SIN cambios de producción, el mecanismo ya existía desde 6df920e**. Antes de
  implementar, verificación de código real (`git log -S`) mostró que
  `AtlasCoder.code()` ya inyecta `test_output` de la iteración fallida en el
  prompt del siguiente intento (`_ITERATION_ERROR_SECTION`,
  `atlas_coder.py:487-488`) — el "why" original del ítem de backlog afirmaba
  lo contrario sin haber grepeado. Único gap real: sin test que lo probara.
  Añadido `tests/test_atlas_coder.py::test_code_corrects_using_previous_test_error`
  (TDD: hub mockeado solo corrige si ve el marcador del error previo en el
  prompt; verificado por mutación que el test detecta la regresión si se
  desactiva la inyección). `docs/backlog.yaml` marcado `done`; corrección
  añadida a `docs/design/2026-07-23-t15-coding-territory-veredicto.md`.
  Ver memoria `feedback-scope-adoption-as-extraction`.
  - **`t5-context-window-condensation-retry` — gap real, verificado y
    cerrado**: a diferencia de t1, el grep (`condense`/`truncate_history`/
    `trim_history` en inference_hub.py/atlas_coder.py: cero resultados) SÍ
    confirmó ausencia real. `classify_provider_error` ya clasificaba
    `ErrorKind.CONTEXT_LENGTH` pero ningún caller actuaba sobre ello más allá
    de marcar el proveedor degradado y probar el siguiente (mismo error de
    tamaño). Añadido a `inference_hub.py`: `_effective_messages()`/
    `_condense_messages()`/`_condensed_request()` (recorte determinista por
    presupuesto de tokens aprox. por caracteres, sin tiktoken ni LLM
    adicional, preserva system + últimos 4 mensajes; `None` si condensar no
    cambiaría nada, evita reintentar a ciegas) enganchado en `_infer_raw`
    tras `_walk_chain` fallar con `error_kind=="context"` — condensa y
    re-camina la cadena UNA vez. TDD real (RED confirmado antes de
    implementar): 2 tests nuevos en
    `test_inference_hub_real.py::TestContextWindowCondensation`. mypy limpio
    (299 ficheros), suite dirigida verde. Ambos ítems T0.5b-paso-3/T1.5
    Track A cerrados esta sesión.

- **Sesión post-MAXIMUS — los 3 frentes de Cycle 14 EJECUTADOS en paralelo
  (2026-07-22 23:20)** — el operador pidió correr F2.6/Taxonomía/T0.5b-paso3
  a la vez, auditando (autobuild), con trabajo pesado en subagentes de fondo
  para no reventar la ventana de contexto. Los tres, cerrados:
  - **F2.6 (código real, vía `/autobuild`, 4 tareas T1-T4 en orden estricto,
    verificado por mí antes de cada avance, nunca solo confiando en el
    subagente)**: `atlas f26 run` construido — lee la rúbrica del propio doc
    PENDIENTE en runtime (fail-closed si el doc cambia de forma), dispara
    `claude -p --model sonnet --output-format stream-json --verbose`
    (dispatcher sustituible), guarda transcript JSONL. Grading estructurado
    nuevo (`f26_grading.py`): los 6 ítems evaluados por separado, 3
    deterministas sobre la secuencia real de `tool_use` (grafo-antes-que-grep,
    GoldenRoute-antes-que-Edit, sin `git add -A`/push), 3 heurísticos de texto
    documentados como tal. Auto-registro (`record_f26_run`) cableado dentro de
    `run_f26`, con regla dura 6/6=pass sin aprobado parcial, y NUNCA se
    registra si el dispatch falló (probado explícito). Notificación:
    `f26_gate_notification()` genera title/tldr/prompt listos para
    `spawn_task`, cableada en `atlas f26 status`/`atlas reality` — respeta que
    `spawn_task` es una tool intra-sesión-agente (el código nunca la invoca
    él mismo); propuesta de paso 1b en AGENTS.md dejada en
    `docs/inbox/2026-07-22-agents-md-f26-notification-proposal.md`, NO
    aplicada (política: docs raíz los cura el operador). Auditoría final
    agregada (autobuild-auditor, Opus): **PASS, 0 correcciones**, 71/71 tests,
    mypy limpio. **Estado real**: la infraestructura está completa y probada;
    el gate SIGUE `due` porque ejecutar la rúbrica de verdad requiere una
    sesión `claude -p` con credencial viva — el 401 documentado desde
    2026-07-17 sigue abierto, no resuelto por esta sesión (requiere
    `claude setup-token` del operador). Archivos:
    `src/atlas/core/self_maintenance/{f26_gate.py,f26_grading.py}`,
    `src/atlas/interfaces/cli.py`, `tests/test_f26_{gate,run,grading}.py`.
  - **Taxonomía (subagente único, verificación de valor ANTES de clasificar,
    tal y como pedía el diseño)**: resultado NEGATIVO con evidencia real
    contra el mapa (no intuición) — de las 51 líneas de tabla de
    `atlas_ecosystem_map.md`, 14 no son piezas clasificables (otras tablas con
    esquema propio) y de las 37 reales, `Tramo` es mecánicamente derivable de
    la columna `Taxonomy` existente; el único contraejemplo real ya está mejor
    resuelto por `Relationship to Atlas`. Vocabulario árbol
    (raíz/tronco/rama/hoja/savia) descartado formalmente en
    `docs/superpowers/specs/2026-07-15-succession-ecosystem-design.md` §5;
    `atlas_ecosystem_map.md` NO se tocó.
  - **T0.5b paso 3 (multi-agente: 4 divisiones + 4 auditores rotados + síntesis
    NO delegada, hecha por mí)**: 708/708 docs clasificados (corpus_inventory
    regenerado con `--write`, subió de 707 a 708). Auditoría cruzada real: de
    191 registros revisados, 17 corregidos (8.9%) — incluye 2 falsos "gap" de
    la División A que ya estaban implementados en código (verificado por
    grep), evitando que entraran al plan v2. Síntesis en
    `docs/design/2026-07-22-t05b-paso3-sintesis.md`: 50 gaps reales agrupados
    en 4 clusters (el mayor, ~29 docs: Osmosis/Compliance Gateway — código +
    ADRs + papers + outreach real, CERO representación en T0-T6, decisión N3
    explícita dejada para el operador, no tomada por esta sesión), 43
    contradicciones (la mayoría ya resueltas o auto-corregidas en el propio
    corpus — p.ej. ADR-059→071 NO es contradicción activa), lista explícita de
    "revisado y descartado". Datos crudos permanentes en
    `docs/knowledge/t05b_paso3/` (antes solo en /tmp, efímero). **Cierre
    honesto**: la parte mecanizable (clasificación+auditoría) 100% cerrada; la
    decisión N3 sobre Osmosis queda explícitamente pendiente del operador, con
    la evidencia ya reunida.
  - **Próxima acción real**: ninguna urgente. Si el operador quiere avanzar:
    (a) `claude setup-token` para desbloquear una ejecución REAL de F2.6, (b)
    decidir la disposición de Osmosis/Compliance Gateway (síntesis T0.5b §1.1/
    §4), (c) revisar/aplicar la propuesta de AGENTS.md paso 1b. Nada de esto
    bloquea nada más.
- **MAXIMUS Cycle 14 — cierre de sesión: F2.6/taxonomía "hecho bien" diseñados
  (no parcheados) + brief T0.5b paso 3 redactado (2026-07-22 21:56)** — el
  operador cerró explícitamente el "vamos al lío" con una instrucción clara:
  NO otro parche barato en F2.6 ni en la taxonomía ("creo que conviene hacer
  algo que sea válido, funcional, profesional y que sea definitivo, no
  pequeños parches... si quieres hacer algo rápido ahora y dejar apuntado
  para que en una sesión futura se haga de la forma correcta"). Aplicado
  literal en los tres frentes pendientes:
  - **F2.6**: `docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md`
    ampliado con el diseño real de lo que falta para que sea definitivo — NO
    otro comando suelto, sino 4 piezas ordenadas: (1) `atlas f26 run` que
    dispare la sesión fría (sustituto validado del `claude -p` bloqueado por
    credencial: subagente Sonnet vía Agent tool, PRIME Cycle 6, 6/6), (2)
    grading estructurado del transcript por ítem (no impresión humana de
    memoria), (3) auto-registro (`record_f26_run()` desde el propio comando,
    no un paso manual separado — ahí es donde se pierde en la práctica), (4)
    notificación accionable (`spawn_task`) SOLO al final, nunca primero. El
    bloqueador de credencial (`claude -p` 401 desde 2026-07-17) sigue abierto
    y no es mío de resolver — requiere `claude setup-token` del operador.
  - **Taxonomía**: `docs/superpowers/specs/2026-07-15-succession-ecosystem-design.md`
    §5 (raíces/tronco/ramas/hojas/savia) marcada **SUPERSEDED formalmente**
    por la taxonomía real de `atlas_ecosystem_map.md` — no se abandona el
    mapa real, se abandona el vocabulario árbol que nunca se implementó.
    Diseño completo de la reconciliación "hecha bien" documentado para
    sesión futura: columna `Tramo` en las 51 filas del mapa real (trabajo de
    clasificación humana, 1-2h, NO automatizable), con paso explícito de
    verificar que produce valor real antes de construir nada sobre ella (si
    no predice nada nuevo, descartar formalmente en vez de mantener a
    medias).
  - **T0.5b paso 3**: brief completo y autocontenido en
    `docs/superpowers/plans/2026-07-22-t05b-paso3-parallel-digestion-BRIEF.md`
    — el diseño del operador (4 proveedores en paralelo + pool de modelos
    dentro de cada uno + auditor cruzado por división, rotación A→C/B→D/C→A/
    D→B para evitar autoevaluación) traducido a plan ejecutable con
    proveedores/modelos REALES de `DEFAULT_PROVIDERS` (no inventados) y
    números reales del corpus (707 docs, 461 `sin_clasificar` tras Cycle 6 =
    división D/Gemini, ventana de contexto grande para el caso ya conocido de
    docs largos diluyendo el coseno). Incluye prompt listo para copiar/pegar
    en la sesión fresca; la síntesis final (gaps+contradicciones+plan v2)
    queda explícitamente marcada como NO delegable — es juicio real de la
    sesión orquestadora, no de las 4 divisiones.
  - `AGENTS.md` revisado (grep por F2.6/ecosystem_map/plugin/A1/A2/A3): NO
    estaba desfasado, sin cambios necesarios.
  - **Próxima acción real:** ninguna — el operador cerró la sesión explícito
    ("no quedaría nada más por cerrar... pasamos ya en la siguiente sesión
    fresca"). La siguiente sesión arranca con el prompt del brief T0.5b, o
    con cualquiera de las 4 piezas de F2.6 si el operador prefiere resolver
    la credencial `claude setup-token` primero.
- **MAXIMUS Cycle 13 — detector de deriva mapa-del-ecosistema↔disco (spec
  B+C §5) (2026-07-22 22:40)** — cierra el último ítem de "vamos al lío".
  "Pieza en disco sin fila en el mapa" traducido determinista: ¿todo ADR
  real tiene su número citado en `docs/design/atlas_ecosystem_map.md`? Los
  ADR ya son el mecanismo establecido del repo para "decisión de
  arquitectura", y el propio mapa ya los cita como Evidence/Authority —
  reusar esa convención en vez de inventar un vocabulario de "pieza" nuevo.
  `atlas.core.self_maintenance.ecosystem_drift`: soporta cita individual
  (`ADR-072`) Y por rango inclusivo (`ADR-024..040`, cuando varios ADRs
  contiguos comparten una fila "SELLADO" — 2 rangos reales en el mapa hoy).
  **2 bugs propios cazados y corregidos ANTES de confiar en el resultado**:
  (1) el número se guardaba como int y perdía el cero-relleno (`ADR-99` en
  vez de `ADR-099`); (2) el sufijo-letra opcional (`013b`) chocaba con
  citas por nombre de fichero completo (`adr_072_supply_chain...md` —
  la "s" de "supply" se leía como intento de sufijo) — arreglado con
  `(?![a-z])` (el sufijo solo cuenta si NO sigue otra minúscula).
  **Primera corrida honesta, no maquillada**: 37 de 51 ADRs sin cita
  aparente — investigado ANTES de aceptar el número (no es ruido de mi
  detector: son 2 rangos reales, `ADR-024..040`/`ADR-026..029`, que
  colapsan 14 ADRs a una sola fila). Con soporte de rango: **23 ADRs reales
  sin fila** — verificado a mano, coincide exacto con la salida del
  programa. Es un hallazgo real de deriva acumulada, no un bug — mismo
  espíritu que `docs_graph_drift` (201 docs sin enlace, nunca maquillado).
  Wireado en `scripts/sanitation_audit.py` (`ecosystem_map_drift()`,
  fail-open) y en `PreflightGate._run_sanitation()` (nueva clave
  `ecosystem_map_drift`, gratis en cada preflight del lazo de
  autoconstrucción). 14 tests nuevos TDD; mypy canónico 288 ficheros 0
  errores; prove-it en vivo: 23 hallazgos reales, conteo verificado a mano.
  **Próxima acción real:** ninguna de las 4 tareas de "vamos al lío" queda
  pendiente. Reconciliar los 23 ADRs sin fila (añadirlos al mapa o
  confirmar que están cubiertos por prosa no-citable) es trabajo de
  contenido, no de código — decisión del operador si perseguirlo.
- **GitHub puesto al día — secreto OAuth real scrubbeado del historial +
  push forzado con lease + CI corriendo de nuevo (2026-07-22 22:20)** — el
  operador pidió ponerse al día con GitHub tras el hallazgo de Cycle 11
  (65 commits locales sin subir desde el 16-jul). Al intentar el primer
  `git push origin main`, **GitHub Push Protection lo bloqueó**: el
  secreto OAuth viejo (client ID Y secret en claro) estaba commiteado en
  `docs/operations/oauth_rotation_google_workspace.md` desde esta misma
  mañana (commit `aa2f8adc`, previo a esta sesión — no lo introduje yo,
  solo edité ese fichero después en Cycle 8) — nunca había llegado a
  GitHub, bloqueado justo a tiempo. **No se intentó "permitir" el secreto
  vía el enlace de GitHub** (habría dejado pasar la fuga en vez de
  arreglarla). Backup local creado ANTES de tocar nada (rama+tag), historial
  reescrito con `git filter-branch --tree-filter` (acotado a `main`, 668
  commits procesados, ~3 min) sustituyendo ambas cadenas por marcadores
  `[REDACTED-...]` — verificado con `git log -S<secreto> main` tras el
  rewrite: cero resultados, en fichero y en TODO el historial. Backup local
  borrado tras verificar el éxito (mantenerlo habría dejado la misma fuga
  al lado). Push normal rechazado por non-fast-forward (esperado, el
  historial cambió de hash); **`git push --force-with-lease origin main`**
  — la única vía correcta tras reescribir historia — avisado explícitamente
  antes de correrlo pese a tener autorización general ("hazlo tu sin
  miedo"), dado que force-push a `main` es su propia categoría de riesgo.
  Aceptado por GitHub: `origin/main` 110f2a4→7c7350b. **CI confirmado
  corriendo de nuevo** en el push (`in_progress` en vivo). Rama
  `origin/codex/self-audit-loop` revisada: ya está al día con su propio
  remoto (nada local pendiente) — vieja/muy divergida de `main` (612
  commits detrás), no tocada (fusionarla es decisión aparte, no pedida).
  **Nota de proceso**: el clasificador de modo automático bloqueó el
  `filter-branch` DOS veces (una antes de la autorización explícita del
  operador, otra después — la autorización en chat no basta, hace falta
  un ajuste de settings) y bloqueó varios comandos de limpieza posteriores
  (`reflog expire`, `gc --prune`) de forma inconsistente incluso tras
  permiso — quedó sin purgar el reflog/objetos inalcanzables localmente
  (no crítico: no se pushean, y `main` en sí ya está limpio).
- **MAXIMUS Cycle 11-12 — investigación CI + bug report a Graphify-Labs +
  F2.6 como gate automático recurrente (2026-07-22 21:40)** — "vamos al
  lío" del operador, separando lo que era mío de lo que no.
  **CI investigado** (no era un problema de GitHub): `origin/main` seguía
  exactamente en `110f2a40` (el último commit del 16-jul) porque **nadie
  había hecho `git push` en 6 días** — `main` local quedó 65 commits por
  delante (todo PRIME 1-10 + MAXIMUS 1-10). Trigger de CI, permisos de
  Actions, todo correcto — simplemente nunca recibió un push. Repo es
  PÚBLICO en GitHub; hacer push queda señalado para el operador, no
  decisión mía.
  **Bug de graphify/eCryptfs reportado** (autorizado explícitamente):
  github.com/Graphify-Labs/graphify#2109 — encontrado el issue previo
  relacionado (#1094, ya cerrado, que introdujo el cap de 200 bytes);
  el mío es el caso que ese fix no cubre (el cap asume NAME_MAX=255
  universal). Root cause + repro + fix sugerido (`os.pathconf` en vez de
  hardcodear), sin exponer contenido real del repo (ejemplo sintético).
  **F2.6 como gate automático** (spec B+C §4): `atlas.core.self_maintenance.
  f26_gate` — determinista, sin red ni LLM, mismo principio que
  `PreflightGate`: la rúbrica de 6 ítems sigue siendo una sesión LLM real,
  cara, deliberada — NUNCA se dispara sola. Lo que se automatiza es la
  DETECCIÓN de cuándo está debida: "cambio grande" (spec) = ADR nuevo desde
  el último run REGISTRADO (`atlas f26 record-run --result pass|fail
  [--at-sha SHA]`, el flag `--at-sha` es para backfill honesto de corridas
  pasadas). `f26_gate_status()` fail-honesto (git que falla nunca dice
  'current' por defecto). Wireado en `atlas reality` (`f26_gate` section,
  mismo patrón que `graph`/`provider_smoke`) y en `atlas f26 status`.
  17 tests nuevos TDD, mypy canónico 287 ficheros 0 errores.
  **Backfill real hecho, no cosmético**: registrada la corrida REAL de F2.6
  (PRIME Cycle 6: 6/6 vía subagente Sonnet frío; PRIME Cycle 8: ceremonia
  golden-route completa en Merkle, commit `07795a04`) como línea base —
  sin esto, `atlas reality` habría alarmado falsamente con "51 ADRs nunca
  revisados". Resultado en vivo, exacto: `due — 2 ADR(s) nuevo(s)` →
  ADR-072 y ADR-073 (los añadidos DESPUÉS de esa corrida real, durante la
  recuperación del worktree en PRIME Cycle 10) — ni de más ni de menos.
  **Próxima acción:** Cycle 13 — detector de deriva mapa-del-ecosistema↔disco
  (spec B+C §5), en curso.
- **MAXIMUS Cycle 10 — graphify restaurado con procedencia real; hook de
  producción confirmado ILESO al bug encontrado (2026-07-22 21:10)** —
  cierra el hallazgo bloqueado al final de Cycle 7 (el operador dio la
  fuente: github.com/Graphify-Labs/graphify). Verificado antes de instalar
  nada: el paquete PyPI real es **`graphifyy`** (doble-y) — el propio
  proyecto avisa que otros `graphify*` NO están afiliados; 93.681 estrellas,
  MIT, mantenimiento casi diario. `0.9.11` (la versión que
  `scripts/install-knowledge-hooks.sh` exige literal) confirmada real en
  PyPI, publicada 2026-07-09 — coincide con la época en que este repo la
  usaba. Instalada con `uv add --optional knowledge-graph "graphifyy==0.9.11"`
  — extra PROPIA, no `dev`: trae ~25 parsers tree-sitter transitivos
  (resolviendo de paso el misterio de Cycle 7 sobre esos mismos paquetes)
  que ningún test/mypy necesita; meterlos en `dev` habría hecho más pesado
  el job rápido de CI sin motivo. `pip-audit` limpio, mypy canónico 286
  ficheros 0 errores, suite completa 3773 passed/0 failed (sin regresión).
  **Investigación honesta de un bug real encontrado al verificar en vivo**:
  `scripts/update-knowledge-graph.sh` (el pipeline COMPLETO, invocado a
  mano) choca con `OSError: File name too long` en `graphify export
  obsidian` — investigado a fondo, no descartado a la primera. Root cause
  real: `$HOME` está montado sobre **eCryptfs cifrado**
  (`stat -f` → `Longnombre: 143`), con un límite EFECTIVO de nombre de
  fichero de 143 bytes en esta máquina — graphify asume 255 (su propio cap
  interno, `_cap_filename`, es de 200 bytes, calculado para el límite
  estándar). Confirmado sistémico, no un caso aislado: retirada una entrada
  duplicada/fuera-de-tema (paper de astrofísica sobre ALMA, falso positivo
  de las queries expandidas "repository mutation"/"document indexing" en
  `docs/knowledge/research_2026-07-10.md`, título de 164 bytes) que
  disparaba el crash — reintentado, y chocó con OTRO título distinto de 169
  caracteres. Recortar contenido uno a uno NO escala contra un límite de
  filesystem; no perseguido más allá de esa única limpieza (justificada por
  sí sola: duplicado + fuera de tema, no un intento de arreglar el bug).
  **Severidad real, correctamente acotada tras leer el hook con calma**:
  `.githooks/post-commit` (lo que corre en CADA commit real) NO llama a
  `update-knowledge-graph.sh` en absoluto — usa
  `graphify.watch._rebuild_code()` directamente, una ruta mucho más
  estrecha (solo `graph.json`/`GRAPH_REPORT.md`, código sin LLM) que NUNCA
  invoca `export obsidian`/`export neo4j`. El bug de eCryptfs es real y
  reproducible, pero solo afecta a quien corra el pipeline completo A MANO
  — no al hook automático que de verdad importa para `atlas reality`/uso
  diario. Confirmado con un commit real de este mismo ciclo: sin el aviso
  "could not locate a Python with graphify installed" de antes.
  **No perseguido, señalado para decisión futura (no es un accidente de
  esta sesión, es una incompatibilidad genuina graphify↔eCryptfs)**: o bien
  reportar el bug aguas arriba a Graphify-Labs (`_cap_filename` debería
  detectar el NAME_MAX real vía `os.pathconf`, no asumir 255), o mover
  `graphify-vault`/`graphify-out` fuera del `$HOME` cifrado si se quiere
  volver a correr el pipeline completo con regularidad.
  **Próxima acción:** ninguna pendiente de los 4 encargos de hoy — todos
  cerrados (CVEs, conector Google, spec B+C, graphify). Quedan las líneas
  ya señaladas en Cycles 7-9 (T0.5b paso 3, F2.6 gate automático, detector
  de deriva ecosystem-map, investigar por qué CI no corre en `main` desde
  el 16-jul) para cuando el operador las priorice.
- **MAXIMUS Cycle 9 — auditoría spec B+C secciones 2-6 + 2 deliverables
  reales cerrados (2026-07-22 20:30)** — a petición del operador
  ("auditoría de si se puede mejorar... una vez terminado hazlo"). Auditoría
  sección por sección de `docs/superpowers/specs/2026-07-15-succession-
  ecosystem-design.md` contra el estado REAL del repo (no solo releída):
  **§2** (`atlas handoff`) listaba 6 deliverables (a-f); solo (a)-(d)
  existían — (e) "mapa del ecosistema resumido" y (f) "primeros 10 minutos"
  nunca se construyeron, pese a que el pack se genera y usa activamente
  (regenerado 3 veces hoy mismo en esta sesión). **§3** (migración de
  memoria) verificada EN VIVO: 60 registros `harness:*`/`doctrine:*` reales
  en `~/atlas-mcp/memory.db`, criterio de partición exacto al spec (`user`
  excluido). **§4** (F2.6): probado 2 veces (PRIME Cycles 6/8) pero nunca
  como gate automático recurrente — sigue siendo invocación manual; su
  "primeros 10 minutos" es literalmente §2(f). **§5** (mapa del
  ecosistema): existe desde 2026-07-07 (ANTES que esta spec) con una
  taxonomía DISTINTA (Core/Capability/Adapter/... + SELLADO/ACTIVO/
  PENDIENTE/PARK/VAPOR/MURO) a la propuesta aquí (raíces/tronco/ramas/
  hojas/savia) — nunca reconciliadas; la real es más granular, no vale la
  pena migrar. El "radar de deriva" (pieza en disco sin fila en el mapa)
  que pide NO existe como detector — gap real, señalado, no perseguido.
  **§6**: verificado tal cual, fail-cerrado real.
  **Implementado** (los 2 deliverables reales, TDD): `ecosistema_body()` —
  parser determinista de la tabla `## Canonical Map` (conteo por estado +
  lista de ítems `PENDIENTE`, los más accionables para un driver nuevo;
  NUNCA redacción LLM, mismo principio "proyección no redacción" del resto
  de `atlas handoff`) → `05_ECOSISTEMA.md`. `primeros_10_minutos_body()` —
  secuencia estática y determinista (AGENTS.md → `atlas reality --json` →
  ruta dorada de demo con recibo → primer cambio real) → `06_PRIMEROS_10_
  MINUTOS.md`. `docs/design/atlas_ecosystem_map.md` añadido a
  `REPO_SOURCES` (contrato de frescura del manifest ahora también lo
  cubre). De paso, corregidas las 2 filas que el propio hallazgo de hoy
  dejó obsoletas: Supply-chain admission scan (A1) y Declarative
  PluginManifest v1 (A2) seguían marcadas `PENDIENTE` con "A3: ..." como
  next-action, cuando A3 completo (Cycles 2-4 de hoy) ya las cerró —
  fusionadas en una fila `ACTIVO` con los 3 módulos reales. 8 tests nuevos
  (parser de tabla + ambos bodies + integración con `generate_handoff`),
  34 verdes en `test_handoff.py`, suite completa 3773 passed/0 failed
  (+8 vs. el conteo de Cycle 7), mypy canónico 286 ficheros 0 errores.
  Pack real regenerado 2 veces (tras el código y tras la corrección del
  mapa) — `05_ECOSISTEMA.md` real muestra 8 PENDIENTE reales de un
  total de 37 filas, útil de verdad para un driver nuevo. Spec B+C
  actualizada con el resumen de esta auditoría y los gaps señalados,
  no perseguidos: F2.6 como gate automático, detector de deriva
  ecosystem-map↔disco, reconciliar/abandonar formalmente la taxonomía
  árbol de la spec.
- **MAXIMUS Cycle 8 — conector google-workspace reconfigurado: secreto fuera
  de argv (2026-07-22 20:00)** — corrección de un hallazgo del propio audit
  de hoy: la memoria de PRIME Cycle 2 decía "OAuth rotado", pero verificado
  en vivo (`ps aux | grep GOCSPX`) el secreto VIEJO seguía embebido en el
  `--mcp-config` de 2 procesos Claude Code corriendo — solo se había
  completado el paso 2 del runbook (guardar el secreto nuevo a salvo en
  `~/.config/atlas/google-oauth.env`, client `228819788474-...`), nunca el
  paso 3 (reconfigurar el conector). El operador confirmó haber rotado el
  client ID en Google Cloud Console (paso 1, credencial suya) y pidió que el
  paso 3 (edición de config, no manejo de credenciales) lo hiciera yo.
  Localizado `~/.claude.json` (config MCP de Claude Code, fuera del repo,
  fichero de texto plano — no algo oculto en UI de Electron como se
  documentó en 2026-07-17) → proyecto `atlas-core` → `mcpServers.
  google-workspace`. Editado: `command`/`args` apuntan ahora a
  `scripts/google_workspace_mcp_wrapper.sh --tool-tier core`, `env: {}` —
  el wrapper inyecta el secreto vía `safe_dotenv.py` (nunca en argv).
  Verificado antes de tocar la config viva: wrapper probado en aislado con
  los args reales (arranca limpio, sin ERROR de precondición). Verificado
  después: JSON sigue válido, cero coincidencias de `GOCSPX`/
  `344051770277` en todo el fichero. Efectivo desde el próximo arranque del
  conector (las 2 sesiones ya vivas conservan el argv viejo hasta
  reiniciarse — reiniciarlas no es mío, mataría sesiones activas).
  **Pendiente, explícitamente del operador**: confirmar que el secreto
  expuesto quedó REVOCADO en Google Cloud Console (no solo sustituido en el
  fichero local) — sin eso, el secreto que ya estuvo en claro en argv sigue
  siendo válido aunque ya no se use. Runbook actualizado con el estado real.
  Memoria de PRIME Cycle 2 corregida (decía "resuelto", no lo estaba).
- **MAXIMUS Cycle 7 — 4 CVEs reales eliminadas + 2 dependencias huérfanas de
  producción declaradas correctamente (2026-07-22 19:30)** — a petición del
  operador ("hazlo todo sin pausa"), tras el hallazgo del audit previo:
  `pip-audit` (el mismo gate que `PreflightGate` corre antes de cualquier
  auto-mejora) mostró 4 CVEs en 2 paquetes. `mcp==1.28.0` (CVE-2026-59950,
  fix 1.28.1): upgrade directo, dependencia real y activa. `gitpython==3.1.50`
  (3 CVEs, fix 3.1.51): investigado de dónde venía — lo traía
  `opentimestamps-client`, un paquete **sin una sola referencia en todo el
  repo** (ni en `pyproject.toml` ni importado en ningún `.py`) — huérfano de
  verdad, invisible al `vapor_audit` existente porque ese solo escanea
  `src/`, no paquetes instalados. Retirada la cadena completa
  (opentimestamps-client + opentimestamps + gitpython + gitdb + smmap).
  `pip-audit` limpio: 0 vulnerabilidades.
  **Error propio cometido y corregido en el camino, con evidencia completa**:
  al verificar consistencia con `uv.lock`, corrí `uv sync --frozen --extra
  mcp --extra dev` sin pensar en qué extras tenía el venv REALMENTE — `uv
  sync --frozen` sincroniza el venv EXACTO a los extras dados, así que
  borró paquetes de extras que no pasé: `fastembed` (extra `embeddings`) y
  `playwright` (extra `computer-use`), ambos en uso real esta sesión.
  Detectado por chequeo de imports post-sync (no por casualidad), corregido
  con `uv sync --frozen --extra dev --extra computer-use --extra embeddings
  --extra mcp` (el set real). **Lección**: nunca correr `uv sync --frozen`
  con un subconjunto de extras sin verificar antes qué tenía instalado el
  venv — pasa de "arreglar un CVE" a "borrar media suite" en un comando.
  **Hallazgo mayor, no planeado, surgido de mi propio error**: el resync
  correcto reveló que `mypy` ganó 3 errores nuevos que no existían minutos
  antes (`acp/server.py`, `tools/video_gen_tool.py`, `tools/image_gen_tool.py`
  — todos "Returning Any"/"cannot subclass has type Any"). Investigado a
  fondo: dos paquetes REALES, con imports perezosos marcados `# noqa:
  PLC0415` en código de producción SÍ WIREADO (CLI `atlas acp`,
  `image_gen_tool.py`/`video_gen_tool.py`), llevaban meses viviendo como
  instalaciones manuales sin declarar — `agent-client-protocol` (paquete
  `acp`, absorción Hermes-Agent 2026-07-18) y `fal-client` — **ninguno de
  los dos existía en `pyproject.toml` ni en `uv.lock`**. Barrido sistemático
  de TODOS los imports perezosos `# noqa: PLC0415` del repo (no solo los que
  mypy señaló) para no dejar un tercero suelto: `crawl4ai` confirmado
  correctamente aislado por diseño (venv separado, documentado); `playwright`/
  `uvicorn` ya declarados. Solo `acp`/`fal_client` eran el gap real.
  Corregido con `uv add --optional acp agent-client-protocol` + `uv add
  --optional media-gen fal-client` (no un `pip install` suelto — habría
  recreado el mismo anti-patrón que acabo de limpiar). CI (`ci.yml`)
  actualizado en paralelo: su job de `mypy strict` nunca sincronizó estas
  extras tampoco (solo `--extra dev`) — mismo gap, mismo root cause; añadido
  un paso de sync adicional con `--extra acp --extra media-gen` antes de
  mypy. **Hallazgo aparte, NO perseguido esta vuelta** (fuera del alcance
  pedido): CI no ha corrido en `main` desde 2026-07-16 — ninguno de los 9
  commits de hoy (PRIME+MAXIMUS) disparó un run; causa raíz desconocida
  (posible config de trigger/permisos de GitHub Actions, no diagnosticable
  solo con el repo local) — señalado para que el operador decida si
  investigar.
  **Verificación final, todo limpio**: `pip-audit` 0 vulnerabilidades, mypy
  canónico 286 ficheros 0 errores, suite completa 3765 passed/1 skipped/0
  failed (corrida 3 veces durante el proceso, siempre estable).
  **Próxima acción:** Cycle 8 (conector google-workspace) + Cycle 9
  (auditoría spec B+C), ya en curso sin pausa.
- **MAXIMUS Cycle 6 — T0.5b paso 2: clasificador semántico del corpus,
  mecanismo construido y corrido en vivo (2026-07-22 18:10)** — el operador
  pidió "a y b por orden"; (b) investigado antes de elegir (igual que
  Cycle 2): las "decisiones toasty" resultaron mayormente operator-gated
  (rotación de secret OAuth, revisión de spec B+C — no son mías de
  ejecutar) y F2.6 ya estaba resuelto (PRIME Cycle 8); T0.5b paso 2 (86% del
  corpus `sin_clasificar` tras paso 1) era el único candidato genuinamente
  accionable — y, verificado, usa `fastembed` LOCAL (sin coste de API ni
  cupo, contra la suposición inicial de que necesitaba "presupuesto propio").
  `atlas.knowledge.corpus_semantic_classifier`: `extract_plan_sections()`
  parsea T0-T6 de `atlas_master_plan.md §5` (acotado a esa sección, nunca se
  cuela contenido de `## 6`/`## 7`); `classify_corpus_semantically()`
  compara cada doc `sin_clasificar` contra las 7 secciones por coseno,
  reusando `_cosine_similarity` de `lesson_recaller` (mismo patrón de import
  cross-módulo que ya usa `memory_index.py`) y el umbral **0.5 YA MEDIDO**
  en la ola bootstrap del 2026-07-17 (no re-derivado). Solo toca
  `sin_clasificar` — nunca reinterpreta un bucket de paso 1; un doc bajo el
  umbral queda `sin_clasificar` con el score igual registrado (nunca
  confianza inventada). Límite heredado de esa misma medición documentado,
  no oculto: docs largos enteros diluyen la señal (~0.45) — el chunking que
  lo arreglaría es su propio trabajo, deliberadamente fuera de esta loncha.
  **Bug real cazado en el diseño de mis propios tests antes de correrlos**:
  un `_FakeEmbedder` de 1 dimensión no puede distinguir direcciones — el
  coseno es invariante a escala, dos escalares positivos cualesquiera dan
  1.0 siempre; rediseñado a vectores one-hot multi-dimensión. CLI `--semantic`
  en `atlas corpus-inventory` (wire-before-claim), embedder resuelto vía
  `atlas.memory.embeddings.default_embedder()` (mismo selector que memoria
  del tronco, gobernado por `ATLAS_EMBEDDER`). TDD real (RED → arreglo de mi
  propio bug de test → GREEN); 14 tests nuevos (incluye 2 CLI end-to-end),
  142 verdes en el área corpus+knowledge+recall+memory_index, mypy canónico
  limpio. **Corrida real en vivo sobre los 705 docs actuales del repo**
  (local, `ATLAS_EMBEDDER` default=fastembed, ~24s, cero llamadas de red):
  **sin_clasificar 86%→65%** (604→461; 143 docs reclasificados: T3=49,
  T4=43, T0=32, T2=15, T5=4). Spot-check manual de los 8 mejores y 5 peores
  matches: plausibles en los dos extremos (p.ej. `t51-provider-smoke-
  surfacing.md`→T5, `atlas_ecosystem_map.md`→T4, `f2_6_personal_factual_
  design.md`→T0 — todas defendibles). `docs/knowledge/corpus_inventory.json`
  (artefacto trackeado de PRIME Cycle 4, referenciado en INDEX.yaml)
  regenerado con el resultado real; `docs_index_drift`/`docs_graph_drift`
  verificados limpios (el drift de enlaces preexistente es idéntico al de
  Cycle 1, no mío). **Honestidad de alcance — T0.5b NO está cerrado**: el
  ítem T0.5.b del master plan pide, además de la clasificación, lista de
  GAPS + lista de CONTRADICCIONES + "plan v2 con fuentes citadas" — eso es
  síntesis/juicio real (no mecánico), explícitamente fuera de esta loncha;
  esta es la pieza algorítmica (paso 2), no T0.5.b completo. No toqué el
  texto vivo del master plan (`§7. Estado y próxima acción` es para cierre
  de TRAMO completo, no de un sub-paso; y `atlas_master_plan.md` es terreno
  del operador, no mío por diff directo).
  **Próxima acción:** paso 3 de T0.5b (síntesis de gaps/contradicciones/plan
  v2 — sesión de investigación propia, juicio real, no delegable a un
  ciclo MAXIMUS) — o volver a las decisiones toasty cuando el operador
  quiera resolverlas él (rotación OAuth, revisión spec B+C).
- **MAXIMUS Cycle 5 — SkillStore descubre plugins activados: cierra el gap
  real que Cycle 4 documentó (2026-07-22 17:20)** — el operador pidió "a y b
  por orden" tras el cierre de A3; (a) = este ciclo. `atlas.mcp.skills_store.
  SkillStore` ganó `plugins_active_root` opcional kw-only (default `None` =
  comportamiento IDÉNTICO al de siempre, los 6 tests preexistentes intactos
  sin tocar): descubre `<active_root>/<plugin_id>/skill/*.md` bajo namespace
  `plugin:<plugin_id>/<contribution_id>` — evita que un plugin pueda
  sombrear o confundirse con un skill nativo del mismo nombre (test
  dedicado). Sirve el DESTINO del symlink (no lo rechaza como haría
  `plugin_admission`: aquí el link ES el mecanismo, no una señal de
  manipulación). Guardia anti path-traversal en `plugin_id`/`contribution_id`
  (regex `^[a-z0-9][a-z0-9-]*$`, mismo charset que `_PluginId` del manifest)
  — probado con 2 intentos de escape (`../secret.txt`, `x/../../secret.txt`).
  Cableado en producción: `trunk_server.py` construye el store con
  `ATLAS_HOME/plugins/active` — el MISMO patrón de resolución que
  `adopted_servers_path()` y ~15 sitios más del repo (no inventé un nuevo
  helper compartido; seguí la convención existente, aunque duplicada, para
  no forzar un refactor de 15+ ficheros fuera de alcance de este ciclo).
  Único constructor de producción de `SkillStore` en todo el repo — cero
  otros call-sites que actualizar. TDD real (RED → GREEN); 10 tests nuevos
  (incluida una integración real con `PluginActivator`, no un doble), 16
  verdes en `test_mcp_skills_store.py`, 52 verdes en todo el área
  trunk_server+skills+capabilities+manifest (incluido el guard de
  `tool_overhead<=25`, intacto — no se añadió ninguna tool MCP nueva). mypy
  canónico limpio. **Prove-it EN VIVO fuera del arnés**: reconstruí el
  `SkillStore` con la MISMA construcción exacta de `trunk_server.py`
  (mismo `ATLAS_HOME`), materialicé+activé un plugin real, y `list_skills()`/
  `get()` lo sirvieron con contenido real sin reiniciar ningún proceso;
  revocado y limpiado al terminar, cadena Merkle real verificada íntegra.
  **Honestidad de alcance señalada, no nueva**: el registro de cada skill
  como MCP `Prompt` nativo sigue baked-in al arranque (propiedad preexistente
  del bucle de `trunk_server.py`, no algo que este ciclo rompiera ni
  arreglara) — un plugin activado necesita reiniciar el tronco para el
  descubrimiento vía Prompt, no para `get_skill`/`list_skills` (ya vivo).
  El tronco MCP corriendo en PID vivo hoy NO se reinició (acción de estado
  fuera de alcance de un ciclo de mejora; decisión del operador cuándo).
  **Próxima acción: (b)** — T0.5b paso 2 / las decisiones toasty / el master
  plan de ciclos PRIME (watchdog daemon, etc. — verificar cuáles siguen
  pendientes antes de elegir, varios PRIME Cycles 2-10 ya los cerraron).
- **MAXIMUS Cycle 4 — A3.3: activador reversible, CAMINO A (ADR-072/073)
  CERRADO de punta a punta para fuente LOCAL (2026-07-22 16:50)** — última
  loncha de A3, continuación directa de A3.2 (Cycle 3). `atlas.mcp.
  plugin_activator.PluginActivator`: consume EXCLUSIVAMENTE un
  `PluginReceipt.status=="issued"` (nunca el `MaterializationResult`
  original), re-verifica de forma independiente (`compute_tree_sha256`,
  extraído de `plugin_materializer.py` con test de guardia anti-deriva) que
  el árbol staged sigue siendo BYTE-A-BYTE el que el recibo describe — dos
  veces: en `activate()` y de nuevo en `approve_activation()`, porque son
  dos ventanas TOCTOU distintas (staging no está fs-locked, solo protegido
  por convención + re-verificación en cada punto de confianza, mismo
  principio que A2/A3.1). Aplica cada contribución como symlink bajo
  `<workspace>/plugins/active/<plugin_id>/<kind>/<contribution_id>.md`
  (fuente única — nunca copia bytes, mismo principio explícito del propio
  `SkillStore`). **Decisión de diseño**: activar consulta el `Decider` DE
  NUEVO (`mutating=True, requires_approval=True`) en vez de heredar el
  veredicto del recibo — un `admit`/aprobación de A2 fue evidencia, nunca
  permiso de instalación (promesa hecha explícita en la CLI desde Cycle 2,
  honrada aquí). `revoke()` NO consulta al decisor (retirar capacidad no
  necesita permiso, mismo principio que `ColdUpdateManager.rollback_applied`/
  `reject()`) y por defecto BORRA staging (`--keep-staging` para no
  hacerlo) — nunca toca nada fuera de `active_root`/`staged_root` (fijado
  con un canario en los tests). Wire-before-claim:
  `Orchestrator.plugin_activator()` (mismo patrón, reusa el MISMO
  `plugin_receipts()` — nunca reconstruye un broker propio) + CLI `atlas
  plugin activate` + `atlas plugin activation show/list/approve/revoke`;
  corregido de paso un mensaje de CLI ya obsoleto ("A3.3 pendiente") que
  Cycle 2 dejó en `plugin materialize` — ya no lo está. TDD real (RED
  import → GREEN, 1 bug propio de fixture cazado — misma fuente reusada dos
  veces en un test de reactivación, no un bug del activador; 1 colisión real
  de mypy documentada y resuelta: un método público `.list()` sombreaba el
  builtin `list` para anotaciones posteriores en la misma clase —
  independiente del orden textual, por cómo `from __future__ import
  annotations` resuelve strings contra el namespace completo de la clase;
  fix con alias a nivel de módulo, sin renombrar la API pública). 21 tests
  nuevos (19 unitarios + 2 CLI end-to-end), 108 verdes en toda el área
  plugins+golden-route+CLI, 238 verdes en el barrido orchestrator+decider
  completo. mypy canónico limpio. **Prove-it EN VIVO fuera del arnés,
  cadena completa**: materialize (ATLAS_DECIDER=autonomous) → recibo
  issued → activate → symlink real verificado apuntando a staging
  (`readlink -f` confirma fuente única, contenido servido real) → revoke →
  active_root Y staging ambos confirmados borrados → cadena Merkle real
  verificada íntegra al final (`verify_chain() == (True, "OK")`).
  ADR-073 y design doc actualizados con el estado real y una nota de
  alcance honesta: el activador aplica los 4 `kind` uniformemente pero solo
  `skill` tiene HOY un consumidor runtime (`SkillStore`, que sirve
  `docs/skills/`, NO el árbol de plugins activos — no extendido, no
  reclamado); `prompt`/`rule`/`command` se aplican sin que nada los lea aún.
  **Próxima acción real (no A3, ese camino está cerrado):** extender
  `SkillStore` para descubrir `<workspace>/plugins/active/*/skill/*.md` (el
  gap de consumidor que este cycle documentó en vez de ocultar), o volver a
  T0.5b paso 2 / las decisiones toasty / el master plan PRIME.
- **MAXIMUS Cycle 3 — A3.2: recibo Merkle + broker de aprobación humana para
  plugins staged (2026-07-22 16:10)** — segunda loncha de A3 (ADR-073),
  continuación directa de A3.1 (Cycle 2). `atlas.mcp.plugin_receipt_broker.
  PluginReceiptBroker`: liga `record_id`+`manifest_sha256`+`provenance`
  (tree-hash)+`staged_root`+decisión en un `PluginReceipt` pydantic estricto,
  persistido + logueado en la cadena Merkle real (`plugin.receipt_issued/
  pending_approval/denied/approved/declined`). **Decisión de diseño clave:
  NO se reinventó HITL** — un veredicto `review` de A2 se traduce 1:1 a
  `sensitivity="high"` sobre el `Decider` protocol YA existente (ADR-040,
  `atlas.core.decider`): `HumanDecider` lo suspende siempre (regla
  constitucional #4), `AutonomousDecider` lo deniega siempre (invariante 2)
  — un `review` nunca se promueve solo porque nadie miró, bajo NINGÚN modo de
  decisor, sin lógica de aprobación ad-hoc. Un `admit` emite recibo `issued`
  de inmediato bajo cualquier decisor (`mutating=False`: emitir evidencia no
  otorga capacidad; la activación real de A3.3 consultará el decisor de
  nuevo con su propio `mutating=True` y su propio undo). Un `block` nunca
  llega al broker — `request()` rechaza explícito, nada que aprobar.
  Resolución humana (`approve`/`decline`) vive DELIBERADAMENTE fuera del
  seam del decisor, mismo patrón que `atlas update approve` para ColdUpdate.
  Wire-before-claim: `Orchestrator.plugin_receipts()` (mismo `_merkle`/
  `_decider` que `golden_route()`/`cold_update()`, patrón idéntico) + `atlas
  plugin materialize` ahora emite recibo automáticamente + CLI nueva `atlas
  plugin receipt show/list/approve/decline`. TDD real (RED import → GREEN,
  1 bug de fixture propio cazado en el camino — `expected_plugin_id` no
  coincidía con el `plugin_id` del manifest, no un bug del broker); 21 tests
  nuevos (15 unitarios + 6 CLI end-to-end), 86 verdes en toda el área
  golden-route+CLI+plugins, 236 verdes en el barrido orchestrator+decider
  completo (nada regresionado por el campo nuevo en `Orchestrator`). mypy
  canónico limpio. Prove-it EN VIVO fuera del arnés: `atlas plugin
  materialize` → recibo `issued` real, `atlas plugin receipt list` en un
  proceso NUEVO lo encuentra (persistencia real en disco), cadena Merkle
  real verificada íntegra tras las escrituras (`verify_chain() == (True,
  "OK")`). ADR-073 y design doc actualizados con el estado real.
  **Próxima acción:** A3.3 — activador reversible que consuma SOLO un
  recibo `issued` (nunca re-decide, solo re-verifica árbol vs
  provenance.tree_sha256 antes de aplicar contribuciones declarativas) +
  revocación/limpieza de staging.
- **MAXIMUS Cycle 2 — A3.1: materializador de plugins a staging inmutable
  (2026-07-22 15:15)** — primera loncha de A3 (ADR-073, la "próxima acción"
  declarada de Cycle 10). `atlas.mcp.plugin_materializer.PluginMaterializer`:
  fuente LOCAL → directorio NUEVO bajo staging, fail-closed en cada paso
  (symlinks, ficheros irregulares, solapamiento fuente/staging, colisión de
  destino, límites de `ScanLimits` reutilizados del scanner); tree-hash
  medido ANTES y DESPUÉS de copiar (mutación durante copia = fail + limpieza
  del parcial); procedencia MEDIDA (revision=sha256 del árbol, no asertada)
  en sidecar `<dest>.provenance.json` FUERA del árbol staged — los bytes
  escaneados son exactamente los admitidos; re-escaneo post-copia vía
  `PluginAdmissionGate` (A2): la admisión queda ligada al árbol STAGED.
  Sin red/subprocess POR CONSTRUCCIÓN (test fija los imports prohibidos).
  Fronteras deliberadas: solo fuente local (fetchers remotos = ADR propio);
  un admit es evidencia, NO permiso de activación (A3.3); block no borra el
  árbol (revocación = dominio del activador/operador). wire-before-claim:
  CLI `atlas plugin materialize` (patrón golden-route), exit 0 solo con
  materialized+admit. TDD real (RED import → RED CLI → GREEN); 10 tests
  nuevos; 58 verdes en área plugins+CLI completa; mypy canónico limpio;
  prove-it EN VIVO fuera del arnés (admit + sidecar reales). Design doc
  actualizado (A3.1-2 HECHO para local; A3.2/A3.3 sin existir por diseño).
  **Hilo estale cerrado de paso:** la "regresión tool_overhead" de Cycle 6 ya
  estaba resuelta (umbral 25 con causa raíz fechada en el propio test:
  graph_communities+graph_semantic_neighbors del 07-16, d39782c8) — el
  "próxima acción: investigar" de esa entrada queda obsoleto.
  **Próxima acción:** A3.2 (recibo Merkle + broker de aprobación humana
  ligando record_id+manifest+procedencia+decisión), luego A3.3 (activador
  reversible que consuma solo ese recibo).
- **MAXIMUS Cycle 1 — probe acotado en el smoke + mypy --strict global limpio
  + INDEX al día (2026-07-22 14:45)** — evaluación crítica global con
  evidencia (mandato del operador: ciclos acotados, honestidad brutal).
  **1)** ProviderChainSmoke heredaba la política de producción del hub
  (120s × 3 intentos, Timeout=transitorio): el smoke de HOY colgó 18 min
  medidos en `nvidia_mistral_medium` (latency_ms=1087936). Fix: overrides
  aditivos `timeout_s`/`max_retries` en `InferenceRequest` (None = constantes
  de módulo, cero cambio para callers previos) + política de probe 30s × 1
  intento en el smoke. TDD real (RED por import → GREEN); `test_provider_smoke.py`
  NUEVO — el smoke no tenía tests propios, por eso su política nunca quedó
  especificada. 486 tests de toda la superficie del hub en verde.
  **2)** Vara de medir de mypy CORREGIDA: los "6 errores preexistentes en
  trunk_capabilities.py" de Cycles 9/10 solo existen bajo `--strict` CLI, que
  PISA las relaxaciones deliberadas y documentadas de pyproject (Pragmatismo
  Gate D: `disallow_untyped_calls/decorators=false`). Bajo la config canónica
  del repo — el gate real del pre-commit — el fichero ya estaba limpio; mis
  ignores inline de primer intento salieron flagged como unused por el propio
  hook y fueron REVERTIDOS (deuda fantasma, no deuda). Estado verificado:
  `mypy src/` canónico = 282 ficheros, 0 errores. Claims futuros de mypy:
  citar la config canónica, no `--strict` CLI ad-hoc.
  **3)** `docs/INDEX.yaml` regenerado (897 entradas; 12 altas legítimas:
  ADR-071/072/073, designs A1/A2, research T2.1, corpus_inventory). Verificado
  en diff que --write preservó campos curados (4 notes movidas por reorden,
  no perdidas). `docs_index_drift` LIMPIO, `--strict` exit 0.
  **No-acciones justificadas:** `nvidia_mistral_medium` NO retirado (1 día
  muerto; el 07-17 estaba OK — el estándar de retirada del repo exige
  persistencia, seguirá el smoke diario); el "dead" de qwen en el smoke de hoy
  es residuo pre-retiro (smoke 08:30–08:53, retiro 08:40, se autolimpia
  mañana); hipótesis "PreflightGate bloqueado por drift de docs" FALSA
  (el gate solo bloquea por CVEs — verificado en código, y el lazo commiteó
  hoy). Pack de sucesión regenerado (hook lo marcaba desfasado), viaja aquí.
  **Próxima acción:** A3 (ADR-073), T0.5b paso 2, o (si se quiere subir el
  listón de tipos) anotar legacy y flipar las relaxaciones Gate D en pyproject
  — decisión de config, no ignores inline.
- **ATLAS PRIME Cycle 10 — recuperado y cerrado el worktree abandonado
  `feat/atlas-engine-program` (2026-07-22 14:15)** — investigado a petición
  del operador tras el hallazgo de Cycle 9 (worktree con ~2 días de trabajo
  sin commitear). Diagnóstico: rama 1 commit por delante de `main`
  (`e57744aa`) + WIP real de la fase A2 (PluginManifest declarativo +
  admisión staged, ADR-072/073), capturada a mitad de un ciclo TDD — 59/60
  tests, el único rojo (`test_trial_gate_does_not_promote_unstaged_local_
  third_party_mcp`) documentaba exactamente el invariante que el propio WIP
  añadía a `MEMORY.md` (`staged-artifact-is-not-an-argv`) pero el código aún
  no lo aplicaba en `_trial_mcp_install()`: un módulo de terceros con argv
  "limpio" (p.ej. `python -m third_party_mcp`, no dispara
  `requires_network_bootstrap` por no ser npx/uvx) pasaba el trial sin
  verificación real de spawn. Fix: `is_atlas_native_module(cmd)` distingue
  código propio (confiable sin spawn) de terceros (exige staging). 60/60 en
  el worktree, cerrado con commit propio en la rama (`9384cea3` en ese
  checkout). Sin colisión con nada de hoy (verificado: `main` no tocó
  ninguno de estos ficheros en toda la sesión). Traído a `main` limpio (11
  ficheros del feature — `plugin_admission.py`, `plugin_manifest.py`,
  `supply_chain.py`/`_models.py`, `static_content.py`, ADR-072/073, 2 schemas
  nuevos, tests) sin tocar `WORK_LEDGER.md`/`MEMORY.md` de la rama (ambos
  desactualizados frente a hoy — reescritos aquí en su lugar). **Suite
  completa en `main` tras el merge: 3684 passed, 0 failed.** mypy --strict
  global limpio salvo `trunk_capabilities.py` (6 errores preexistentes,
  confirmados sin relación vía `git stash`, no tocados).
  **Estado nuevo declarado:** Supply-chain admission scan (A1, PENDIENTE) +
  Declarative PluginManifest v1 (A2, PENDIENTE) en
  `docs/design/atlas_ecosystem_map.md`. **Próxima acción:** A3 (materializador
  de procedencia inmutable + receipt Merkle/HITL + activador reversible,
  ADR-073) — o T0.5b paso 2 / las 4 decisiones toasty.
- **ATLAS PRIME Cycle 9 — ColdUpdate apply() ya no hace `git add -A` a ciegas
  (2026-07-22 13:40, commit be97eb0e)** — investigado a petición del
  operador tras el hallazgo de cierre de Cycle 8 (commit automático
  `5a889529 cold_update: apply 8eed7466-c47` arrastró `WORK_LEDGER.md`/
  `docs/INDEX.yaml`/`docs/knowledge/research_2026-07-22.md`; legítimo del
  daemon esta vez, pero el mecanismo era el problema). Verificado: **cero
  colisión con Codex hoy** (0 commits de Codex en `main`; el único worktree
  con cambios sin commitear — `atlas-core-engine-program`, supply-chain
  admission scan — tiene timestamps del 2026-07-20, no concurrentes,
  señalado aparte, NO tocado). Pero el riesgo es real, no hipotético: el
  repo tiene precedente documentado de sesiones Codex concurrentes sobre
  este mismo checkout. `_commit_with_evidence()` hacía `git add -A` — el
  commit de evidencia de CUALQUIER apply() arrastraba todo lo sucio en el
  árbol bajo un mensaje que solo describe esa propuesta, el mismo
  anti-patrón que el repo prohíbe explícitamente en otros sitios. Fix:
  `_patch_touched_paths()` nuevo parsea las cabeceras del patch; el commit
  ahora hace `git add -- <rutas>` escopado; sin rutas parseables, falla
  explícito a forensics en vez de caer a `-A`. TDD real (RED con un fichero
  ajeno colándose en el commit, GREEN tras el fix). 34/34 + 64/64 en el
  área relacionada, mypy --strict limpio.
  **Hallazgo aparte, no tocado:** `atlas-core-engine-program` tiene ~2 días
  de trabajo sin commitear (12 ficheros, feature de supply-chain admission
  scan, toca `WORK_LEDGER.md`/`MEMORY.md`) — decisión del operador si
  recuperarlo, revisarlo o descartarlo.
  **Próxima acción:** T0.5b paso 2, las 4 decisiones toasty, o decidir sobre
  el worktree abandonado de arriba.
- **ATLAS PRIME Cycle 8 — F2.6 CERRADO de verdad, por la ruta dorada
  (2026-07-22 13:15, commits 810f969d/0a364d9a/07795a04)** — plan aprobado
  por el operador ("haz una lista y ejecútalo"): cerrar los 3 gaps que F2.6
  había dejado abiertos y completar el ciclo hasta el final.
  **8a** (`810f969d`): `TestSelfBuildCycleWiring` (2 tests) — causa raíz
  exacta vía Explore: la fixture `orch` de `tests/test_maintenance_autoloop.py`
  (2026-07-04) nunca se actualizó cuando el guard anti-recursión
  `ATLAS_NESTED_TEST_RUN` aterrizó (041f3972, 2026-07-09); si el entorno real
  lo traía puesto, los tests veían `calls==[]` en silencio. Fix puntual +
  hardening de raíz: `ATLAS_NESTED_TEST_RUN` ahora se limpia en el autouse
  global de `conftest.py` — ningún test futuro puede repetir el gap.
  **8b** (`0a364d9a`): `test_real_executor_can_inspect_authorized_external_git_repo`
  — usaba `Path(__file__).resolve().parent.parent` como "repo externo
  autorizado", que deja de ser el checkout principal dentro de un worktree
  efímero de ColdUpdate (el `.git` del worktree apunta a metadata FUERA de
  sí mismo, invisible al sandbox bwrap). Reproducido de forma aislada
  (`git worktree add` manual + pytest directo) antes de tocar nada — TDD
  real. Fix: el test crea su propio repo git desechable en `tmp_path`.
  **Suite completa: 3652 passed, 0 failed** — primera vez en toda la sesión.
  **F2.6 aplicado de verdad** (`07795a04`): propuesta `8eed7466-c47` —
  `atlas golden-route request` → `validate` (passed=True, 3651 tests+mypy)
  → `approve` → `apply`, ceremonia completa en Merkle. La línea
  "F2.6 ejecutado" está en `docs/continuation/CONTINUATION_STATE.md`, vía
  el camino correcto, no un Edit directo.
  Ítem E del plan (fila de `inference_hub` en `atlas_ecosystem_map.md`)
  **descartado tras revisión**: ese doc es un inventario de componentes
  arquitectónicos (Mission Layer, GoldenRoute, BwrapJail...), no una tabla
  de fan-in por módulo — ni `orchestrator.py` ni `merkle_logger.py` (más
  centrales aún) tienen fila. El hallazgo del subagente F2.6 fue una
  confusión de categoría, no un gap real; no se tocó el doc.
  **Próxima acción:** T0.5b paso 2 (clasificación semántica, sesión propia)
  o las 4 decisiones toasty pendientes de juicio del operador.
- **ATLAS PRIME Cycle 6 — F2.6 ejecutado vía subagente Sonnet frío, no vía
  `claude -p` (2026-07-22 12:30, commit 061d80c4)** — `claude -p` sigue en
  401 (bloqueado, operador). Corrí el rubric F2.6 dos veces con un subagente
  Sonnet real sin memoria de esta sesión (Agent tool, model=sonnet) —
  aproximación válida al espíritu del test (sustrato sin contexto de
  conversación), no idéntica al mecanismo documentado.
  **1ª corrida: 5/6** — único fallo: usó Edit directo en vez de
  `atlas golden-route request` (wireado HOY en Cycle 3) para anexar una
  línea a un doc; AGENTS.md nunca lo mencionaba — gap mío, no del agente.
  Fix: AGENTS.md §4b. **2ª corrida: 6/6 en comportamiento** — descubrió y
  usó la ruta dorada correctamente; `atlas update validate` corrió la suite
  completa (3651 tests) en worktree aislado y encontró 2 regresiones reales
  NUEVAS; el agente NO forzó la aprobación sobre el gate fail-closed
  (correcto) y verificó por su cuenta que las regresiones eran preexistentes
  a su propio cambio. La línea "F2.6 ejecutado" por tanto sigue SIN estar en
  CONTINUATION_STATE.md — comportamiento correcto, no bug pendiente.
  Regresión 1 (mía, Cycle 4 de hoy) CERRADA: `docs/knowledge/
  corpus_inventory.json` (>100KB) sin cubrir en `.graphifyignore` — añadido.
  Regresión 2 flagueada, NO mía (verificado: solo toqué graph_server.py hoy,
  sin tools nuevas): `test_mcp_trunk_manifest.py` espera tool_overhead()≤23,
  mide 25 — deriva ambiental o gap preexistente, requiere investigación
  propia. Bonus: el agente corrió `atlas handoff --check` sin pedírselo
  (STALE, reportado con honestidad — señal positiva extra de la rúbrica).
  **Próxima acción:** investigar la regresión de tool_overhead (¿qué añadió
  las 2 tools de más?) + reintentar `atlas golden-route request` para F2.6
  ahora que el gate debería pasar (o cuando el operador retome `claude -p`
  para la corrida oficial vía CLI).
- **ATLAS PRIME Cycle 5 — cierra la ventana SIGTERM del arranque (2026-07-22
  12:00, commit 00bed343)** — diagnosticado en Cycle 1, diferido en Cycle 2.
  `run_forever()` instalaba los signal handlers DESPUÉS de `start()` (varios
  threads/servers, puede tardar); un SIGTERM en esa ventana caía en la acción
  por defecto del sistema — proceso muerto sin `stop()`, sin log
  `service.stopped`, sin limpiar telegram/offline monitor. Fix: handlers
  antes de `start()` + `threading.Event` propio (`stop_requested`,
  independiente de `_running` que `start()` reescribe a mitad de su propia
  ejecución) + `stop()` ahora guarda con `_started` (fijado al final de
  `start()`), no con `_running` — el guard viejo trataba "`_running` ya en
  False por una señal" como "nunca arrancó" y saltaba TODA la limpieza sin
  avisar. 2 tests dirigidos (TDD real), 72/74 verdes en el área (2 fallos
  preexistentes en test_maintenance_autoloop.py, confirmados sin relación vía
  git stash). Verificado en vivo: `systemctl restart atlas-core.service` paró
  en <1s (antes: 90s timeout → SIGKILL, visto el 12-jul y 17-jul). **Cierra
  el backlog de robustez del daemon abierto en Cycles 1-2.**
- **ATLAS PRIME Cycle 4 — T0.5b paso 1: inventario del corpus (2026-07-22
  11:50, commit b91a0573)** — T0.5b (master plan §T0.5.b) pedía clasificar
  666/701 docs contra el plan (alimenta-ítem/candidata/histórico/GAP) con
  evidencia de cobertura; SPEC-ONLY, nada empezado. La clasificación
  semántica completa no cabe en un ciclo (692 docs de contenido real, juicio
  no mecanizable) — este ciclo construye la línea base medible:
  `atlas.knowledge.corpus_inventory.inventory_corpus()` + CLI
  `atlas corpus-inventory`, bucket heurístico por convención de ruta, todo lo
  no reconocido = `sin_clasificar` (nunca inventa confianza). Corrida en
  vivo: **701 docs, 86% sin_clasificar** — guardado en
  docs/knowledge/corpus_inventory.json. 9 tests dirigidos, mypy --strict
  limpio. **Próxima acción:** paso 2 de T0.5b (clasificación semántica del
  86% restante, probablemente vía embeddings/graphify contra secciones del
  master plan — trabajo de investigación real, mejor con presupuesto propio
  o delegado) — o retomar F2.6/decisiones toasty cuando el operador lo diga.
- **ATLAS PRIME Cycle 3 — GoldenRoute wiring (2026-07-22 11:20, commit
  ec0d122a)** — cerrado el gap "implementado+5 tests E2E pero CERO callers de
  producción" (hallado por Explore en Cycle 1). `Orchestrator.golden_route()`
  reusa el MISMO ColdUpdateManager/Merkle que `cold_update()` (nunca
  `GoldenRoute.for_repo()` — esa fábrica es para tests, usarla en producción
  crearía un segundo ledger desconectado e invisible a `atlas update status`).
  CLI nuevo: `atlas golden-route request TEXT` traduce texto libre a propuesta
  real; validate/approve/apply siguen siendo EXACTAMENTE `atlas update
  validate/approve/apply` — cero atajo al camino humano (norma del spec
  mission_layer_self_construction). TDD real (RED: "No such command
  'golden-route'"), 5 tests nuevos + 94 verdes en el gate de commit, mypy
  --strict limpio. **Próxima acción:** Cycle 4 — T0.5b digestión del corpus
  (666 docs vs master plan) o F2.6 cuando el operador retome el token 401.
- **ATLAS PRIME Cycle 2 — watchdog daemon + TimeoutStopSec (2026-07-22 10:50)**
  — TimeoutStopSec=30 en atlas-core.service (limita stop-sigterm hang de 90s a 30s). daemon_idle_guard.sh mejorado: auto-rearranca si inactivo >24h (salvaguarda: toque ~/.atlas/daemon_idle_parked para aparcar deliberadamente si la parada fue intencional). 11 tests dirigidos verdes. Ventana SIGTERM fija (handlers instalan DESPUÉS de start(), linea 401-408 en service_runner.py) diferida — bajo investigación abierta, ciclo propio. F2.6 test de sucesión SIGUE BLOQUEADO — intentado 2026-07-22 con token nuevo (setup-token corrido dos veces) y aún 401 "Invalid authentication credentials"; no es un problema de formato del token, algo más profundo en la credencial de cuenta. Diferido, operador decide cuándo retomar. OAuth google-workspace rotado (nuevo client ID: 228819788474-u6ts3hamsjplf307tifmqob3oon1jv2u; secret guardado fuera del repo en ~/.config/atlas/google-oauth.env, inyectado por wrapper vía safe_dotenv). **Próxima acción:** F2.6 execution (operador o Sonnet con presupuesto) + Cycle 3 GoldenRoute wiring.
- **Desbloqueos operador (2026-07-22 09:30)** — Anthropic token renovado (sk-ant-oat01-..., válido 1 año); F2.6 test de sucesión EJECUTABLE ahora con `claude -p`. OAuth google-workspace rotado (228819788474-k5s30lhsop9e7rcspg503p7qsc607blt; secret en ~/.config/atlas/google-oauth.env 0600, fuera del repo, inyectado por wrapper vía safe_dotenv — argv limpio de credenciales ahora). Pending: F2.6 execution (operador o Sonnet con presupuesto) + 4 decisiones toasty (spec B+C, monitor graphify, higiene handoff INDEX).
- **ATLAS PRIME Cycle 1 — daemon rearrancado + frescura del grafo en reality +
  proveedor muerto retirado (2026-07-22)** — el daemon llevaba PARADO desde el
  2026-07-17 12:21 (stop limpio vía systemctl, nunca rearrancado; la guarda
  SessionStart avisó y se actuó): `active` de nuevo. Gap de honestidad cerrado:
  `atlas reality` ahora aflora la frescura del grafo Kuzu — `graph_freshness()`
  en project_graph.py como FUENTE ÚNICA del vocabulario FRESH/DIRTY/STALE/
  SERVER_STALE/EMPTY/UNKNOWN/NO_DB/UNAVAILABLE; graph_server MCP ahora DELEGA
  en él (fin de la lógica duplicada), sección `graph` + capability
  `graph.project` en reality (fail-honesto estilo provider_smoke, seam
  ATLAS_GRAPH_DB). Verificado en vivo: reporta DIRTY con el árbol sucio de esta
  misma sesión — exactamente la verdad. openrouter_qwen3_coder_free RETIRADO
  del hub (smoke diario: dead, 429 upstream persistente, único failed de 14;
  patrón comentario fechado; Qwen3-Coder-480B queda sin acceso vivo en la
  cadena). TDD real (RED visto), 149 tests dirigidos verdes, mypy --strict
  limpio en los 4 ficheros. Journal: persisten 2 stop-sigterm timeout→SIGKILL
  (12-jul y 17-jul 07:47) — el apagado se cuelga ~90s; sospecha
  cgroup/hijos (unit sin KillMode/TimeoutStopSec explícitos) — ciclo propio.
  **Próxima acción:** Cycle 2 — watchdog de vida del daemon (de aviso a acción,
  con opt-out documentado para parking deliberado) + fix ventana SIGTERM +
  TimeoutStopSec en el unit; después GoldenRoute wiring (implementado+probado
  pero huérfano de callers) y T0.5b digestión.
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
  -909 líneas; canal canónico = Kanban/atlas-twin). 4bis-1 CORREGIDO en la
  misma ola: el primer veredicto "sin bug" era incompleto — el mecanismo del
  tick es correcto pero load_bitemporal_into_kuzu re-embebía el histórico
  ENTERO (~29k llamadas ONNX CPU) en cada regen → ticks de HORAS, grafo
  perpetuamente STALE bajo flujo de commits (cazado en vivo con py-spy:
  scheduler 5h dentro de embed()). Arreglado con ingesta incremental por
  id path@commit_sha (re-pasada = 0 embeds, delta-only; test con embedder
  contador) — el re-sello FRESH ocurre solo tras el restart del daemon.
  4bis-4: .venv-scraping reconstruido (crawl4ai 0.9.2), marcador real
  success=200 vía SSRF bridge. Re-verificación: 183 tests dirigidos verdes +
  reality limpio. F2.6 PENDIENTE con prompt listo
  (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md — la ola
  llegó con >50% de presupuesto consumido, regla bootstrap).
  EXTENSIÓN misma ola (orden operador "haz todos"): 52822e86 (trabajo daemon
  commiteado) + 18af7e0c (higiene INDEX: 500 handoff→historico, --strict
  limpio) + aa2f8adc (wrapper OAuth sin secretos en argv + runbook — la
  ROTACIÓN queda para el operador) + cf5ce30b (ciclos scheduler loguean
  fallos con traceback) + 6a533d05 (12-fuentes: Groq NO —413 TPM medido—,
  Gemini free SÍ, 12 exclusiones deliberadas, cobertura 98.3%→99.3%, quedan
  5 grandes re-intentables al reset del cupo; + guard pre-push refs/codex/*).
  F2.6 INTENTADA en real: 401 token revocado → prerequisito operador
  `claude setup-token` (doc F2.6 actualizado).
  **Próxima acción:** operador: rotar secret OAuth (runbook
  docs/operations/oauth_rotation_google_workspace.md) + claude setup-token
  (desbloquea F2.6) + re-run 5 fuentes al reset (comando en ledger campaña).
  Siguiente ola: T2.1 consola mínima ∥ T0.5b digestión.

## Archivo

Entradas más antiguas (2026-07-08 a 2026-07-16, 28 entradas) plegadas
el 2026-07-23 a `docs/archive/2026-07-work-ledger-fold-1/WORK_LEDGER_ARCHIVE.md`
para cumplir la disciplina de ≤40 entradas de este fichero.
