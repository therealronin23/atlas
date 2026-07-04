# WORK LEDGER — estado vivo de la matrioska

Fuente única del "¿dónde estamos?" (autoridad del ESTADO; el design doc NO duplica estado).
Una línea por nodo activo. Se actualiza EN EL MISMO COMMIT que el trabajo (parte de "done").
Sobrevive a compactaciones: leer esto al retomar y se está orientado.
Detalle por feature en su design doc; el porqué/lecciones en memoria (`MEMORY.md`).
Higiene: ≤ ~40 líneas; podar nodos cerrados a la sección de archivo cuando crezca.

Formato: `[estado] nodo — próxima acción / bloqueado-por`. Estados: ✅ hecho · 🔄 en curso ·
⬜ pendiente · 🧱 muro (tipo-3) · ⏸ diferido.

## Capa 0 — auto-construcción (ATLAS_MANUAL_MASTERPLAN-1.md, G0.0→G0.9)

✅ G0.0 self-audit · ✅ G0.1 LessonRunner+BwrapJail · ✅ G0.2 LessonPromoter E2E · ✅ G0.3 avoid_patterns
✅ G0.4 VerifiedProducer HITL · ✅ G0.5 TransparencyLog+anti-replay durable · ✅ G0.6 tier1_auto_apply fail-closed
✅ **G0.7** `LessonSynthesisRecorder` + `convene_for_decision(synthesis_recorder=)` (2026-06-27, 12 tests)
✅ **G0.8** `SelfImprovementBridge`+`CveDepProposer` YA cableados (knowledge_scan_step → service_runner);
   test HITL invariante añadido: CVE → origin='self_audit', bloqueado de tier1_auto_apply por diseño.
✅ **G0.9** `TwinDecider` shadow + `record_human_verdict` (Slices 2-3, 2026-06-27, 15 tests verdes).
   Métrica de acierto acumulada en `ShadowAccuracyLog`; warmup MIN_CORPUS_SIZE=30; shadow-only hasta tener números.
🔑 **CAPA 0 CERRADA** (2026-06-27) — 2401 tests verdes. Próximo: Capa 1 / G1.0.
**Fix ortogonal**: `InferenceHub` auto-carga `.env` via python-dotenv al importar → claves disponibles sin source.

## G0.10 — Batching HITL + roadmap "juicio real" self-audit (2026-07-03/04)

Motivado por hallazgo real: bucle self_audit atascado 38 veces (2026-06-26→07-01) por 9 YAMLs
seedeados regenerados sin commit — causa raíz ajena a las dependencias propuestas, nadie razonaba
el porqué de los fallos. Cónclave (3 rondas, FAIL 3/3 las 2 primeras, FAIL-con-correcciones la 3ra)
estableció: mantener HITL pero por LOTE (no por cambio), y dar juicio real al pipeline antes de
ampliar autonomía — condicionado a métricas objetivas futuras, no a promesa.

✅ **ColdUpdateBatcher** (`cold_update_batcher.py`) — acumula propuestas validated+self_audit,
   prueba juntas, bisección si falla. ✅ **BenchmarkGate** (LongMemEval antes/después, razonamiento
   no velocidad). ✅ **EventType.COLD_UPDATE_BATCH_READY** + Telegram + CLI `atlas update
   batch-review/batch-approve` — única decisión humana por lote, sigue pasando por el decisor.
✅ **Roadmap "juicio real" (5/5 pasos, orden corregido por Cónclave: barato→caro):**
   1. `PreflightGate` — CVEs (pip-audit) + conexión (`sanitation_audit.py` reusado) determinista.
   2. `BatchPremortemGate` — riesgo de combinación, barato, ANTES de correr tests; escala al trío
      completo si toca ruta sensible.
   3. `RootCauseClassifier` — chequeo GRATIS contra git (HEAD vs working tree) primero; solo cae a
      LLM barato si no hay evidencia. Habría detectado el incidente YAML sin gastar un token.
   4. `DepAnalyst` — juicio de riesgo por bump individual (1 solo LLM, no dual: DepCandidate ya es
      tipado/autoritativo de PyPI).
   5. `FailureLessonSink` + `LessonStore.record_recurring()` — dedup por hash(intent+reason),
      contador de ocurrencias en vez de un archivo nuevo por repetición.
   Las 3 deliberaciones del Cónclave quedaron registradas retroactivamente en LessonStore (veredicto
   + síntesis/corrección humana, no solo el texto crudo) — regla nueva: TODA convocatoria real al
   Cónclave debe pasar `synthesis_recorder`, sin excepción.

✅ **4 pendientes cerrados (2026-07-04), usando ToolCoder como motor principal:**
   - `FailureLessonSink` cableado en `ColdUpdateBatcher._bisect()` (señal, nunca bloquea).
   - `BenchmarkGate` integrado en `run_batch()` (dentro del try, antes de limpiar el worktree;
     solo si el lote ya pasó los tests) — ToolCoder convergió LIMPIO en 1 iteración, 12/12 tests.
   - `ToolUsageCounter` — métricas reales de uso por tool, cableadas en el punto central de
     despacho `TrunkAggregator.invoke()/invoke_readonly()`. Alcance honesto: cubre tools
     enrutadas por el tronco, NO los ~32 tools "meta" registrados directo vía `@server.tool()`.
   - `SotaSnapshotRecorder` — primer paso ACOTADO hacia medirse vs SOTA externo (captura fechada,
     no comparación automática); reutiliza `CrawlerTool`, probado en vivo contra github.com.
   **Medición de ToolCoder (4 intentos, `--engine tool`)**: 1 convergencia limpia (0 arreglos),
   3 con 1 bug pequeño y localizable cada una (typo en patch de test, cast de mypy, función no
   definida en vez de `field(default_factory=)`) — nunca "cero output" como en intentos
   anteriores de la sesión. Patrón: specs de una sola pieza de comportamiento (no 5+ ramas a la
   vez) convergen con alta fiabilidad, con errores pequeños y baratos de corregir a mano.

⬜ **Pendiente honesto, aún no resuelto:**
   - MCP: sigue sin instrumentar el uso de los tools "meta" del propio tronco (fuera del scope
     de `invoke()`/`invoke_readonly()`).
   - Visión larga (Atlas investigando SOTA externo sin parar, mejora recursiva, comparación
     automática contra `SotaSnapshotRecorder`) — explícitamente diferida, no construida.
**Lección medida**: AtlasCoder (Llama-70B) completó G0.7 parcialmente (1/3 cambios en 3 iter); 2 lecciones en LessonStore.

## Catálogo de proveedores/modelos — fixes 2026-06-27 (prove-it en vivo)

Origen: investigación de 9 harnesses (memoria `harness-engineering-survey-2026-06-27`) reveló que Aider
leaderboard está congelado desde 2025-10 y nuestra config de proveedores tenía entradas desactualizadas.

- ✅ `groq_compound`: "compound-beta" → "groq/compound" (renombrado por Groq, litellm exige prefijo doble)
- ✅ `groq_qwen3`: qwen3-32b → qwen3.6-27b (más reciente, prove-it OK)
- ✅ **OPENROUTER_API_KEY renovada** (la anterior daba "User not found" 401 en completions reales — el
  listado /models no valida auth, por eso pasó desapercibido meses). 2 cuentas nuevas → account_pool.
- ✅ 3 proveedores OpenRouter nuevos (todos gratis, prove-it OK): `openrouter_qwen3_coder_free` (mismo
  modelo que nvidia_qwen3_coder de pago, GRATIS — ojo: rate-limited upstream con frecuencia, mantener
  el de pago como fallback), `openrouter_nemotron_ultra` (550B), `openrouter_hermes_405b` (rate-limited
  upstream también, modelo popular).
- ✅ 3 proveedores NIM nuevos L2 (prove-it OK): `nvidia_deepseek_v4_flash`, `nvidia_deepseek_v4_pro`
  (DeepSeek V4, confirmado vivo, SWE-bench ~80.6% según fuente secundaria sin verificar), `nvidia_mistral_medium`
  (Mistral Medium 3.5, mejor benchmark que Mistral Large 3 pese a ser más pequeño). `codestral-22b`
  probado y descartado (404 en nuestro tier NIM).
- Total: 20 proveedores (7 L1 gratis, 8 L2 pago con account_pool, resto L0). Suite 2382 verde.
- ⏸ **PENDIENTE (tarea diferida a propósito, no urgente)**: script de sync periódico
  (`scripts/model_catalog_sync.py`, mismo patrón que `mcp_sync.py`) que consulte `/models` de
  Groq+OpenRouter+NIM regularmente y detecte automáticamente altas/bajas/renombres — evitaría que esto
  vuelva a desactualizarse silenciosamente. Construir cuando surja el momento, no ahora.
- ✅ GLM-5.2 confirmado: aún no disponible gratis, solo de pago — no bloquea nada, `nvidia_glm` (5.1) se
  mantiene hasta que 5.2 aparezca en el tier accesible.
- ✅ **Técnica 13 (cascada de match tolerante, Aider)**: `AtlasCoder._reindent_tolerant_match` — fallback
  tras match exacto fallido: compara línea a línea ignorando whitespace inicial, si hay EXACTAMENTE una
  ventana que calza reaplica la indentación real del archivo sobre el replace. Fail-closed (0 o >1 → no
  aplica). 2 tests nuevos (reindent tolerado + ambiguo rechazado). Suite 2384 verde.
- ✅ **Lazo 4 — roles de modelo explícitos** (técnica 10, validada 4x independientemente: Continue.dev
  config.yaml, Cline Plan/Act, Cursor apply-model, Aider --architect): `Provider.roles: tuple[str,...]`
  (edit/apply/chat) etiquetado en los 20 proveedores según benchmarks reales investigados (DeepSeek V4→
  edit, Kimi K2.6→edit, groq_llama_70b→chat+apply, etc.) + `InferenceHub.infer_for_role(role, request)`:
  soft-preference, reordena providers del nivel pedido con el rol al frente sin descartar el resto — el
  fallback a L0 y al resto del nivel sigue intacto si todos los rol-etiquetados fallan (verificado con
  test dedicado). `AtlasCoder.code()` pide role="edit" en cada iteración. 4 tests nuevos en
  `TestInferForRole`, mypy limpio en inference_hub.py. Suite 2388 verde.
- ✅ **Técnica #1 — linter bloqueante** (patrón SWE-agent str_replace_editor): `AtlasCoder._is_valid_syntax`
  + `_write_with_lint_gate` — antes de aceptar una edición a un `.py`, verifica `ast.parse`; si rompe
  sintaxis, NO escribe (auto-revierte esa edición puntual, no todo el archivo) y loggea. Archivos no-.py
  no se verifican. 3 tests nuevos (rechaza syntax error, acepta edición válida, ignora no-.py).
- ✅ **Técnica #12/#19 — rutas protegidas** (Codex CLI rutas read-only / Cline "comandos destructivos
  siempre piden aprobación", adaptado a la arquitectura real de AtlasCoder: no ejecuta shell arbitrario,
  el riesgo es EDITAR donde no debe): `PROTECTED_PATH_SEGMENTS` (.git/.env/.ssh/secrets.env/.aws/.gnupg)
  + `_is_protected_path` — `code()` rechaza fail-closed ANTES de llamar al modelo si algún context_file
  toca una ruta protegida, sin excepción. 3 tests nuevos. Suite 2394 verde, mypy limpio (nuestro).
- ✅ **Técnica #14 — repo-map con PageRank** (patrón Aider, adaptado a stdlib `ast` en vez de tree-sitter —
  manía `stdlib-over-new-deps`, Atlas es Python puro): `src/atlas/core/repo_map.py` — `extract_symbols`
  (firmas de funciones/clases/métodos vía `ast`, sin cuerpo), `extract_references` (nombres usados),
  `_pagerank` (iteración de potencias manual, sin networkx, con personalización sesgada hacia
  `context_files`), `build_repo_map` (rankea archivos NO en foco por relevancia, respeta presupuesto de
  caracteres). Cableado en `AtlasCoder.code(repo_map_files=...)` — opt-in explícito (None = sin escaneo,
  no cambia comportamiento por defecto), construido una vez antes del bucle. 15 tests en `test_repo_map.py`
  + 2 en `test_atlas_coder.py`, mypy strict limpio en repo_map.py. Suite 2411 verde.
- ✅ **Técnica #18 — formato apply_patch** (patrón OpenAI Codex CLI, adoptado también por Cline SDK —
  2 fuentes independientes lo confirman más fiable que SEARCH/REPLACE): `src/atlas/core/patch_format.py`
  (nombre elegido para NO chocar con `ColdUpdateManager._apply_patch`, ya existente, cosa distinta) —
  gramática `*** Begin Patch/Add File/Update File/Delete File/Move to/End Patch`, envelope por-archivo
  en vez de SEARCH/REPLACE por-stream. `apply_update_hunk` reutiliza el mismo fail-closed de match único
  (técnica #3). Cableado en `AtlasCoder.code(edit_format="apply_patch")` — **aditivo, opt-in**: default
  sigue siendo `"search_replace"`, cero cambio de comportamiento sin pedirlo explícitamente. Reutiliza
  el linter bloqueante y las rutas protegidas ya construidas (mismas protecciones, formato distinto).
  13 tests en `test_patch_format.py` + 6 en `test_atlas_coder.py`, mypy strict limpio. Suite 2430 verde.
- ✅ **Técnica #4 — apply-model separado** (patrón Cursor/Continue/Aider architect/Cline Plan-Act, 4
  fuentes independientes): cierra el lazo abierto por el lazo 4 (rol `apply` etiquetado pero sin consumir).
  `_try_apply_model_fallback`: si un bloque SEARCH/REPLACE falla mecánicamente (no encontrado/ambiguo),
  delega en un modelo barato con `role="apply"` que reescribe el archivo completo dada la intención,
  en vez de gastar otra iteración entera del modelo caro. Acotado a UN solo `context_file` (evita
  explosión combinatoria si hay ambigüedad de a qué archivo pertenece). Reutiliza el linter bloqueante
  (técnica #1) antes de aceptar. `AtlasCoder.code(use_apply_model=True)` — aditivo, opt-in, default False
  = comportamiento anterior sin cambios. 4 tests nuevos (rescata bloque fallido, desactivado por defecto,
  se salta con >1 archivo, respeta el linter). Suite 2434 verde, mypy limpio (nuestro).
  **Cierra las 25 técnicas del harness survey con el único cambio de arquitectura grande completado.**
- 🧱 **#6 replanteado — experimento de eficacia AtlasCoder (2 intentos, ambos fallidos)**: se replanteó
  el alcance (el "clasificador" original violaría la invariante D2 de `AutonomousDecider`, "nunca LLM en
  el path de autorización") y se delegó a AtlasCoder mismo (`strategy=COUNCIL`) para medir su eficacia
  tras las 14 técnicas cableadas. Intento 1: `success=True` sin implementar nada (falso positivo — la
  suite existente no verificaba la feature nueva); corrompió texto de ejemplo no relacionado (arreglado).
  Intento 2 (con test que sí verifica la feature): falló honestamente, `stuck detector` abortó tras el
  modelo confundirse repetidamente usando texto de ejemplo del prompt como ancla SEARCH literal. En
  ambos casos, 0 cambios reales — los guardrails (#2, #3) contuvieron el fallo. 2 lecciones en LessonStore
  (`atlas_coder:sandbox_experiment_2026-06-27`). **Conclusión honesta**: AtlasCoder falla de forma segura
  ante features multi-pieza nuevas, no las resuelve — ese es su límite actual real.
- ✅ **#6 implementado directamente (por Claude, no delegado)**: `AtlasCoder._create_sandbox`/
  `_cleanup_sandbox`/`_sync_sandbox_back` + `code(sandbox=True)`. Aplica todo el bucle sobre una copia
  temporal aislada (`shutil.copytree` excluyendo .git/.venv/caches/data/workspace); `test_cmd` corre ahí
  (reutiliza `cwd=self._repo_root` ya existente, sin tocar esa línea); solo si `success=True` sincroniza
  `files_changed` de vuelta al repo real (`shutil.copy2`, maneja también archivos borrados en el sandbox
  vía `DeleteFileOp`); si falla, el repo real NUNCA se tocó (más fuerte que `revert_on_failure`, que sí
  necesita revertir porque escribe directo — ambos coexisten, `revert_on_failure` se salta cuando
  `sandbox_dir is not None` por ser redundante). Cleanup siempre corre (éxito o fallo), best-effort.
  `self._repo_root` se restaura siempre al valor original tras el run — no se filtra a llamadas
  posteriores del mismo `AtlasCoder`. Aditivo: `sandbox=False` por defecto, cero cambio de comportamiento.
  6 tests en `test_sandbox_mode.py`, mypy limpio (nuestro), suite 2440 verde.
  **Cierra formalmente las 25 técnicas del harness survey — 15/25 completadas, sesión terminada.**
- ✅ **LÍMITE DE ATLASCODER REBASADO** (2026-06-27, tras 5 intentos con diagnóstico de causa raíz entre
  cada uno): Atlas implementó una feature real él solo (`LessonStore.stats()`, sincronizada del sandbox al
  repo real, tests de verificación pasando, 2453 suite verde). Receta ganadora: `IncrementalCoder` (nuevo,
  `src/atlas/core/incremental_coder.py` — una pieza por incremento, secuencia cortada al primer fallo,
  sandbox por defecto) + `edit_format=apply_patch` + `strategy=COUNCIL` (L2) + test de verificación
  escrito antes y confirmado fallando + 3 fixes de causa raíz medidos en vivo:
  (a) parser: líneas en blanco dentro de hunks no traen prefijo (Kimi) — ahora contexto vacío;
  (b) `_apply_prefixless_insertion`: Kimi emite hunks SIN marcadores +/- — recuperación acotada
      (ancla=líneas que existen, inserción=las que no; solo sin +/-, ancla única, fail-closed);
  (c) sandbox + instalación editable: PYTHONPATH del sandbox debe preceder a site-packages o los tests
      importan el código real sin las ediciones (los tests fallaban siempre de forma invisible).
  También: tolerancia a reindentado en `apply_update_hunk` (técnica #13 extendida a #18) y placeholders
  inequívocos en `_INSTRUCTIONS_SEARCH_REPLACE` (el modelo copiaba el texto de ejemplo como ancla).
  Fallos de modelo medidos: Llama-70B corrompe delimitadores SEARCH/REPLACE ('>>>>>>> REPLACE' como
  separador central); L1 no reproduce líneas exactas ni en apply_patch. 1 lección-receta en LessonStore.
  ← SIGUIENTE: usar esta receta para cerrar el resto del backlog con Atlas construyendo y Claude auditando.
- ✅ **LOTE A-D con la receta** (2026-06-28, Atlas construyendo + Claude auditando/rematando):
  - **B (técnica #17, métricas parsed/applied): ATLAS SOLO, 3/3 incrementos** — `CoderResult.blocks_parsed/
    blocks_applied` + contadores en `_apply_edits` + wiring en `code()`. 48 min (L2 lento pero correcto).
    Único remate: indentación 3→4 espacios (estilo, no funcional). 3 tests verdes.
  - **A (retrievers temporal_decay/hybrid_temporal)**: Atlas falló 2 veces (archivo 340 líneas, funciones
    nuevas a nivel de módulo — reveló y se arregló OTRO bug del parser: líneas columna-0 sin prefijo
    cortaban el hunk). Rematada directamente. Los 4 tests deseleccionados de la suite AHORA PASAN —
    cero deselecciones por primera vez.
  - **C (técnica #15, lint feedback al modelo)**: inc1 de Atlas fue FALSO POSITIVO (success con files=[] —
    el test del incremento no ejercitaba su pieza; error de diseño MÍO del incremento, misma lección del
    experimento sandbox repetida). Rematada directamente: `_lint_rejections` acumulados en
    `_write_with_lint_gate` → inyectados en `prev_error` de la siguiente iteración.
  - **D (técnica #20, AGENTS.md jerárquico)**: Atlas falló (cambio de firma + lógica). Rematada
    directamente: `_build_institutional_section(context_files=)` descubre AGENTS.md en directorios
    ancestros del primer context_file (específico al final = mayor prioridad).
  - **Patrón de capacidad medido**: Atlas cierra incrementos con anclas cortas/únicas en archivos
    conocidos; falla con anclas largas, archivos grandes o cambios multi-sitio. Señal de falso positivo:
    success=True + files_changed=[]. Lección en LessonStore.
  - **Suite: 2466 verdes, 0 deselecciones, 0 fallos.** Técnicas harness survey: 18/25 cerradas
    (+#15,#17,#20). Restantes: #5 (priompt), #11 (reglas condicionales), #16 (git auto-commit),
    #21 (compactación), #23/#24 (decisiones Hermes del usuario).
- ✅ **AtlasCoder consulta LessonStore ANTES de actuar** (2026-06-28, respuesta a pregunta del usuario:
  "¿Atlas no podrá darse cuenta y corregir problemas antes de que ocurran?"). Hueco real cerrado: las
  lecciones se escribían tras fallar pero nadie las leía antes del siguiente intento. `AtlasCoder(...,
  lesson_store=, lesson_recaller=)` opt-in — reutiliza `_build_avoid_section` (ya existía para codegen,
  cero duplicación) para inyectar hasta 3 lecciones relevantes a la tarea como sección "Patrones a evitar"
  en el prompt, ANTES de llamar al modelo. Verificado en vivo: con threshold=0.3 (el default de
  LessonRecaller, 0.8, es demasiado estricto para StubEmbedder no-semántico — anotado, no arreglado),
  Atlas ya ve las 3 lecciones de esta sesión (incluida la del falso positivo C-1) al recibir una tarea
  similar. 3 tests nuevos.
- ✅ **Alarma automática de falso positivo** (mismo origen): `CoderResult.suspicious_no_op` — se marca
  True cuando `success=True` pero `files_changed=[]` (exactamente la forma del bug C-1, ahora detectada
  sin auditoría manual). `IncrementalCoder` la trata como fallo de secuencia — no avanza sobre una pieza
  que en realidad no se implementó. 2 tests nuevos (AtlasCoder + IncrementalCoder). Suite 2472 verde,
  mypy limpio (nuestro).
- ✅ **Embedder de LessonRecaller: StubEmbedder→default_embedder()** (2026-06-28, mismo tema). `default_embedder()`
  ya existía (gobernado por `ATLAS_EMBEDDER`, `FastEmbedEmbedder` semántico local vía fastembed sin red);
  `LessonRecaller.__init__` lo usaba hardcodeado a `StubEmbedder(dim=64)` en vez de respetarlo. Fix: 1 línea,
  aditivo (sin `ATLAS_EMBEDDER` en entorno, comportamiento idéntico — StubEmbedder). Activado
  `ATLAS_EMBEDDER=fastembed` en `.env` (fastembed ya instalado, 0.8.0, sin dep nueva). Verificado en vivo:
  con threshold=0.8 (default de LessonRecaller) el embedder semántico SIGUE sin matchear — hallazgo honesto:
  ese 0.8 está calibrado para el caso de uso ORIGINAL de LessonRecaller (casi-duplicados de ataques,
  similitud muy exigente), no para "relevancia temática de lección↔tarea". Documentado en el docstring de
  `AtlasCoder.__init__` (parámetro lesson_recaller): construir con threshold explícito ~0.35 para este caso
  de uso. Con eso, la lección más relevante puntuó 0.71 (antes 0.48 con StubEmbedder hash). 3 tests nuevos.
- ✅ **Modo enjambre real en ParallelCoder** (2026-06-28): bug crítico encontrado y corregido — antes,
  incluso un worker EXITOSO perdía sus cambios al borrar el git worktree (nunca sincronizaba de vuelta
  al repo real). `_sync_worker_result_back` (mismo contrato que `_sync_sandbox_back`) + pass-through de
  `**coder_kwargs` (edit_format, strategy, use_apply_model, lesson_store, etc. — mismo mecanismo que
  IncrementalCoder). `sandbox=` rechazado explícitamente en `ParallelCoder.run()` (redundante, cada
  worker ya está aislado en su worktree). 3 tests nuevos con repo git real.
- 🧱 **Enjambre real, 2 intentos, 0/4 éxitos** — técnicas #5/#11/#16/#21 lanzadas en paralelo con 4
  workers L2, cada uno con la tarea de crear UN archivo nuevo con CÓDIGO EXACTO ya escrito en la tarea
  (caso más fácil posible: transcribir, no diseñar). Intento 1 falló por bug propio (todos los workers
  reusaban el mismo provider por round-robin desde índice 0 en runs independientes — sin diversidad
  real). Intento 2, con diversidad corregida, **descubrió 2 modelos NIM MUERTOS**: `qwen/qwen3-coder-
  480b-a35b-instruct` (HTTP 410 Gone, "reached its end of life on 2026-06-11" — estaba muerto DESDE
  ANTES de que se "verificara" el 2026-06-26/27) y `z-ai/glm-5.1` (mismo 410). Retirados de
  `DEFAULT_PROVIDERS`. Además `deepseek-v4-flash`/`deepseek-v4-pro` cuelgan de forma consistente
  (timeout >45s, 2 intentos) — retirados también, catálogo L2 recortado de 8→4 proveedores vivos
  confirmados (`nvidia_llama_large`, `nvidia_kimi`, `nvidia_mistral_large`, `nvidia_mistral_medium`).
  Intento 3, con proveedores vivos y diversos: **0/4 de nuevo** — 2 workers atascados (stuck detector,
  ni un bloque aplicado), 2 aplicaron algo pero no pasó los tests (contenido perdido al borrarse el
  worktree, el sync-back solo ocurre en éxito final). **Marcador honesto: el enjambre no mejoró la
  eficacia sobre el modo secuencial — 0/4 incluso con el caso más favorable (transcribir código exacto).**
  Las 4 técnicas se implementaron directamente (mismo código que se le dio a Atlas en la tarea, ya
  verificado con TDD). 16 tests nuevos (4 por módulo) + 3 de wiring de `auto_commit` en AtlasCoder.
  Lección guardada en LessonStore. Suite 2497 verde, mypy limpio (nuestro).
- ✅ **TODAS las 25 técnicas del harness survey cerradas** (implementadas o descartadas con razón
  documentada — #23/#24 quedan como decisión pendiente del usuario sobre Hermes, no técnicas de código).
- 🔑 **ToolCoder — EL CAMBIO DE ARQUITECTURA QUE FALTABA** (2026-06-28, corrección DEL USUARIO: "si no
  se usa un arnés de verdad, ningún modelo hará nunca nada bien"). Diagnóstico validado: AtlasCoder era
  un arnés de COMPLETACIÓN DE TEXTO (prompt→blob→regex) que obligaba a los modelos a emitir formato
  perfecto a pulso; la infraestructura de TOOL-CALLING existía desde ADR-031 (InferenceHub.tools/
  tool_calls normalizados, AgenticExecutor con el bucle completo) pero el bucle de código no la usaba —
  se implementó la mitad textual/defensiva de la investigación de harnesses y se pospuso el motor.
  `src/atlas/core/tool_coder.py`: el modelo LLAMA read_file/str_replace/create_file con argumentos JSON
  validados por la API (la corrupción de delimitadores que mató 8/9 delegaciones NO PUEDE ocurrir);
  guardrails reutilizados como RESULTADOS ESTRUCTURADOS de tool (el modelo los ve y corrige, no warnings
  de log); lecciones de LessonStore inyectadas (factoría `with_default_lessons`, threshold 0.35 + fastembed).
  **Validación en vivo A/B, mismos modelos L2, mismo día**: completación de texto = 0/4 (incluso
  transcribiendo código exacto); tool-calling = **2/2 en 1 iteración cada una (8s y 30s), incluida una
  MULTI-PIEZA** (crear módulo nuevo + modificar registro existente — la clase de tarea que falló el 100%
  de las veces en toda la sesión). 8 tests unitarios + 2 pruebas en vivo. También:
  `AtlasCoder.with_default_lessons` (punto 4 — ninguna delegación futura puede olvidar las lecciones).
  Suite 2506 verde, mypy limpio. Lección-clave en LessonStore con crédito al usuario.
- ✅ **ToolCoder como motor de enjambre — re-medición confirmada** (2026-07-02). `ToolCoder.code()`
  gana `sandbox: bool = False` (mismo contrato que `AtlasCoder._create_sandbox/_sync_sandbox_back`,
  3 tests TDD nuevos). `ParallelCoder` gana `coder_factory: CoderFactory` (default = AtlasCoder, cero
  cambio de comportamiento); `_run_worker` ya no hardcodea el motor. `IncrementalCoder` funciona con
  `ToolCoder` por duck-typing sin cambios (verificado con y sin sandbox). **Enjambre real en vivo, 4
  workers con providers L2 distintos (llama_large/kimi/mistral_large/mistral_medium), 4 tareas nuevas
  e independientes en repo git aislado**: **4/4** (vs 0/4 del intento previo con AtlasCoder). Archivos
  verificados con contenido real (no `suspicious_no_op`) + suite del repo aislado 5/5 verde. Nota: el
  `level` de `ParallelCoder.run()` solo alimenta `discover_workers`, NO se reenvía a `coder.code()` —
  gap latente para cualquier motor con `level` explícito (ToolCoder), sorteado en el script de medición
  con un wrapper; no se tocó `parallel_coder.py` porque AtlasCoder no tiene parámetro `level` (rompería
  su firma). Suite completa 2509 verde, sin regresiones. Capa 0 y el ciclo de auto-construcción: CERRADOS.
- ✅ **Cierre de la lista "no probado" + cableado real** (2026-07-02, mismo día, orden por complejidad):
  1. **Gap de `level` arreglado** (`parallel_coder.py`): `_run_worker` reenvía `level` a `coder.code()`
     SOLO si el motor declara ese parámetro (`inspect.signature`) — ToolCoder lo recibe, AtlasCoder (sin
     `level` ni `**kwargs`) queda intacto. 2 tests nuevos.
  2. **ToolCoder cableado a `atlas code` CLI**: flag `--engine {atlas,tool}` en secuencial y `--parallel`.
     Default=`atlas` — decisión pasada por Cónclave (juez+lentes, decisión reversible): la muestra 4/4 de
     ToolCoder era de tareas fáciles-medias, insuficiente para flipar el default de producción sin la
     re-medición con tareas difíciles (punto 3 de esta lista). 3 tests CLI nuevos (`test_cli_code_engine.py`).
  3. **Re-medición con tareas MULTI-PIEZA difíciles** (registro de 338 líneas, "añade handler SIN borrar
     nada" — la condición exacta que hundía a AtlasCoder): reveló y arregló DOS bugs reales de ToolCoder
     antes de confirmar la victoria — (a) `TypeError` crudo sin capturar cuando un modelo manda un
     argumento no-string (`compile() arg must be str`), ahora error estructurado que el modelo corrige en
     el siguiente turno (2 tests); (b) **bug grave**: un modelo llamó `create_file` sobre el archivo
     existente de 338 líneas y lo dejó en 34 — EXACTAMENTE el modo de fallo que el usuario describió al
     principio de la sesión ("le pido pegar código y borran el archivo entero"), enmascarado porque la
     suite de verificación solo comprobaba el handler nuevo, no el resto del archivo. Fix: `create_file`
     sobre un archivo YA EXISTENTE con >10 líneas de contenido se RECHAZA fail-closed con error
     estructurado que sugiere `str_replace` (2 tests: rechaza sustancial, permite trivial). Tras el fix:
     **4/4 en la primera repetición limpia** (contenido verificado línea a línea, incluido el worker que
     antes crasheaba); repeticiones posteriores golpearon rate-limiting real de NVIDIA por repetir
     experimentos seguidos sobre la misma cuenta (2/4, 3/4) — CERO incidentes de destrucción de contenido
     en ninguna repetición tras el fix, los únicos fallos fueron 429/errores de proveedor, no del motor.
  4. **Costo/latencia**: sin instrumentación nueva — datos ya recogidos de las medidas anteriores.
     ToolCoder en tareas exitosas: 2.6s–140s (mediana ~9s, la cola larga es 1 provider con 3 iteraciones).
     AtlasCoder (dato de sesión previa, técnica B/lote A-D): 48 min para 3 micro-incrementos exitosos en
     L2, y 0/4 en las tareas multi-pieza comparables (nunca terminó, coste efectivamente desperdiciado).
  Suite completa 2518 verde tras todo el lote, mypy limpio en los 3 archivos tocados.
- ✅ **Paridad de features ToolCoder cerrada** (mismo día, tras el lote anterior): `repo_map_files` y
  `auto_commit` portados a `ToolCoder.code()` (mismo contrato que AtlasCoder, `build_repo_map`/
  `commit_changes` reutilizados sin duplicar lógica). `apply-model` fallback y `edit_format` alternativo
  quedan documentados como MOOT para ToolCoder — resuelven problemas específicos de la completación de
  texto (SEARCH/REPLACE mal aplicado, delimitadores corruptos) que no existen cuando el formato lo valida
  la API de tool-calling. 4 tests nuevos (`test_tool_coder_parity.py`). Suite 2522 verde.
- **Cónclave re-consultado sobre el flip de `--engine` default** con la paridad ya cerrada: **veredicto
  mantener `default=atlas`** — no por falta de evidencia de que ToolCoder gane (ya está clara: 4/4 fácil
  + 4/4 difícil tras arreglar 2 bugs reales), sino porque encontrar 2 bugs reales en la PRIMERA sesión
  seria de stress testing es señal de que la superficie de bugs de ToolCoder probablemente no está
  agotada — asimetría de volumen real (AtlasCoder: semanas de tareas variadas; ToolCoder: ~14
  invocaciones en un día) importa más que la tasa de éxito medida hasta ahora. `--engine tool` queda
  disponible y documentado para quien quiera la ganancia hoy; el flip se revisita cuando el dogfooding
  activo deje de encontrar bugs nuevos de esta clase, no en una fecha fija.
- **Queda SOLO lo que requiere decisión del usuario**: #23/#24 (Hermes Agent, ver arriba). El flip de
  `--engine` default queda como condición de señal (dogfooding sin bugs nuevos), no como bloqueo de
  decisión del usuario — recomendación del Cónclave documentada arriba. Todo lo demás de la lista de
  "no probado" quedó cerrado en esta sesión.
- ✅ **Decisión #1 (Hermes 4 modelos) resuelta**: `openrouter_hermes4_70b` añadido (L2, pago, prove-it
  en vivo OK). `hermes-4-405b` confirmado real pero bloqueado por falta de crédito en la cuenta
  OpenRouter — no añadido, queda como decisión de financiación del usuario. NIM verificado en vivo
  contra `/v1/models`: CERO modelos Hermes en nuestro tier (una fuente secundaria lo afirmaba, era
  incorrecta). Suite 2524 verde.

## Hermes Agent — auditoría/inventario (2026-07-02, solo lectura, sin código)

**CORRECCIÓN al contexto de esta auditoría** (2026-07-02, mismo día): Hermes Agent no era hipotético —
estuvo instalado y corriendo ~1 mes (may 2026) en el VPS como gemelo real de Atlas (ADR-026,
`HermesRestAdapter` ya construido en `src/atlas/hermes/hermes.py`). VPS dado de baja por alcance, no
por fallo. Detalle completo en memoria `hermes-vps-deployment-playbook-2026-05`.
- ✅ **Poda de las ~30 (18 confirmadas) ramas Hermes sin mergear** (deuda pendiente desde
  `session-2026-06-26-git-history-decisions`, grace period del graveyard F3 vencía 2026-07-21):
  revisadas todas — 17 eran scripts de despliegue VPS de un solo uso (cuotas de proveedores,
  systemd, rutas de instalación), 1 (`feat/hermes-twin-architecture`, ADR-026) ya estaba en `main`
  por otra vía. Ninguna contenía trabajo único no capturado. Resumen guardado en memoria (playbook de
  despliegue, por si se retoma el VPS), las 18 ramas remotas borradas (`git push origin --delete`).

Design doc: `docs/design/absorption_master_plan.md` (sección "Hermes Agent — deep audit").

- ✅ **Auditoría completa** vía subagente Explore sobre clon real (no doc-level): 109 tools catalogados
  por categoría, arquitectura de 15+ directorios top-level, gateway de 13 plataformas confirmado,
  sistema de memoria (SQLite+FTS5), modelo de delegación, integración MCP. Mapeado contra Atlas actual:
  5 capacidades genuinamente nuevas (gateway multi-plataforma, browser/computer-use, visión/imagen/
  video, smart home, ACP adapter, curador de lifecycle de skills), resto redundante o ya cubierto de
  forma más rigurosa (MCP propio ya cerrado, BwrapJail > `approval.py` de Hermes, ParallelCoder/
  IncrementalCoder > delegación de Hermes). Confirmado el diagnóstico del usuario: la delegación de
  Hermes NO es un orquestador completo (cita del propio hallazgo: "no external state store, no
  cross-job dependencies") — Atlas es arquitectónicamente más profundo ahí, no absorber esa pieza.
- ✅ **Decisión de alcance del gateway CERRADA vía Cónclave escalada completa** (trío Gemini+Kimi+
  Mistral, mismo día): veredicto **FAIL unánime** a la opción "expansión del rol de Atlas" — sin
  divergencia entre los 3 linajes, convergencia independiente en: rompe D2 en la práctica (mensajes
  no confiables llegarían directo al decisor), punto único de fallo entre subsistemas sin relación,
  fusión de identidad irreversible con exposición legal real (KYC en plataformas chinas), sin state
  store externo para persistencia por canal. **Decidido: PEER separado, nunca fusión** — Atlas
  invoca/es invocado (MCP como superficie natural), identidades nunca se funden.
- **Orden recomendado, actualizado**: (1) ✅ gateway — decisión cerrada, ver arriba; (2) browser/
  computer-use envuelto como tools MCP nuevas en el trunk propio, enrutado por BwrapJail/
  AutonomousDecider — SIGUIENTE candidato real; (3) patrón de lifecycle de skills para LessonStore/
  LessonPromoter (patrón, no código); (4) resto diferido.
- **Invariante explícita**: nada de Hermes se envuelve sin pasar por el decisor/jail propio de Atlas —
  su `approval.py` (pattern-matching) es más débil que el invariante D2 de `AutonomousDecider`.
- ✅ **Cross-audit Codex CLI / Cursor / Claude Agent SDK** (mismo día, petición del usuario: "lo mismo
  que con Hermes"). Codex CLI (código real, open source) + Claude Agent SDK (código real, open
  source; Claude Code mismo es cerrado, solo docs) + Cursor (solo docs/blogs, cerrado). Hallazgo
  cruzado 1: **los 3 confirman de forma independiente el invariante D2 de Atlas** (juicio LLM nunca en
  el path de autorización) — validación externa fuerte, no cautela idiosincrática. Hallazgo cruzado 2:
  **ninguno de los 3 tiene deliberación multi-modelo, routing multi-proveedor, ni memoria de lecciones
  con corroboración** — Atlas va por delante exactamente donde el usuario esperaba. **3 gaps concretos
  y accionables encontrados** (a diferencia de Hermes, que necesita decisiones de alcance primero):
  (1) `ToolCoder` no tiene NADA de `institutional_context_files`/AGENTS.md — se pasó por alto al
  "cerrar paridad" antes; `AtlasCoder` ya tiene descubrimiento jerárquico (técnica #20), confirmado
  2 veces más hoy (Codex `agents_md.rs`, Cursor AGENTS.md anidado); (2) `conditional_rules.py`
  (técnica #11) es código muerto — cero llamadores en `src/`, Cursor tiene el sistema de referencia
  maduro (4 modos de activación); (3) modo ensemble/best-of-N para `ParallelCoder` (Cursor: mismo
  task a N modelos, se queda el mejor) — hoy `ParallelCoder` solo hace el caso contrario (subtasks
  distintos a workers distintos). Documentado en `docs/design/absorption_master_plan.md` (sección
  "Codex CLI, Cursor, Claude Agent SDK — cross-comparison"). Sin código tocado, solo auditoría.
- ✅ **Los 3 gaps cerrados el mismo día** (TDD, cada uno verificado antes de implementar):
  (1) `ToolCoder._build_institutional_section` — mismo contrato que `AtlasCoder`, incluida la
  técnica #20 (descubrimiento jerárquico de AGENTS.md); 5 tests nuevos.
  (2) `conditional_rules.py` cableado en `_build_institutional_section` de AMBOS motores —
  `load_conditional_rule` reemplaza el `read_text()` crudo, filtra frontmatter `applies_to` sin
  cambiar comportamiento para archivos sin frontmatter (AGENTS.md/WORK_LEDGER.md actuales); 4 tests.
  (3) `ParallelCoder.run_ensemble(task, ..., n=3)` — misma tarea a N workers, gana el éxito con
  menos iteraciones; `WorkerResult.captured_files` captura contenido en memoria ANTES de destruir
  el worktree (sync_back=False) para poder aplicar solo el ganador sin conflictos de escritura
  entre intentos redundantes; 2 tests. Suite 2535 verde, mypy limpio.
- ✅ **(2) Browser/computer-use — hybrid landed** (2026-07-02, petición usuario: "usamos lo mejor
  de cada uno y tenemos un híbrido mejor que ninguno"). `BrowserTool` propio verificado en vivo
  (estaba dormido: tests excluidos por marker `computer_use` + Chromium sin instalar — no roto,
  solo sin ejercitar; 26/26 verdes una vez instalado). Añadido Microsoft Playwright MCP
  (`npx -y @playwright/mcp@latest`) como raíz externa del tronco — árbol de accesibilidad (no
  screenshots) → menos tokens, sub-100ms, 23 tools. Probado con un handshake MCP real (stdio,
  SDK oficial `mcp` de Python, ya en `.venv`) ANTES de tocar el catálogo — 23/23 tools listadas en
  vivo. Cableado puro por catálogo (`docs/design/mcp_catalog.yaml`, entrada `Playwright / WebApp
  Testing` → `status: verificado`), sin código de servidor nuevo — confirma que `trunk_children()`
  ya soportaba esto. **Gap de gobernanza cerrado en la misma pasada**: `CatalogEntry` no tenía
  forma de declarar tools de solo-lectura para raíces MCP EXTERNAS (`McpServerConfig.read_only_tools`
  — ADR-035 dec.5 — solo llegaba a raíces nuestras). Añadido `CatalogEntry.read_only_tools`
  (parseado del YAML) + threading en `trunk_children()`. Solo 5 tools marcadas directas
  (`browser_snapshot`, `browser_console_messages`, `browser_network_requests`,
  `browser_network_request`, `browser_take_screenshot`); el resto (`browser_click`/`browser_type`/
  `browser_fill_form`/`browser_run_code_unsafe`/etc.) sigue mutate/HITL por defecto — cumple la
  instrucción explícita del usuario ("directo para las de solo lectura, decisor solo si se añaden
  fill/click"). 4 tests nuevos (`test_mcp_catalog_structured.py`, `test_mcp_trunk_aggregator.py`),
  mypy limpio, verificado extremo a extremo contra el catálogo real. Desktop-control/scraping más
  allá de navegación — pendiente, no investigado todavía.
- ✅ **Gating anidado del trunk cerrado** (2026-07-02, mismo día — el usuario pidió resolverlo antes
  de seguir). DOS gaps reales confirmados EN VIVO contra el trunk corriente: (1) routing — el
  `TrunkAggregator` solo indexaba raíces nativas y NADA actualizaba `_owner`, así que
  `trunk_invoke("browser_snapshot")` daba `KeyError` (los externos eran inalcanzables por la vía
  corta); (2) gobernanza — el gate HITL del host mira el nombre EXTERNO (`trunk_invoke`), no el
  `tool=` interno, así que las lecturas anidadas caían a mutate/HITL. Fix: `TrunkAggregator` gana
  `refresh` (routing perezoso: spawnea hijos uno a uno vía `ensure_started` hasta encontrar al
  dueño del tool) e `is_read_only` (predicado ESTÁTICO desde config/catálogo — invariante D2, nunca
  juicio LLM); nueva tool `trunk_invoke_readonly` fail-closed (solo despacha lo declarado
  `read_only_tools` en la raíz dueña; el resto se rechaza con PermissionError) — marcada 'read' en
  `_TRUNK_READ_ONLY_TOOLS` (`trunk_manifest.py`) y regenerado `~/atlas/mcp_servers.json`. Probado
  E2E con proceso trunk fresco + Playwright real: navigate enruta (perezoso OK), snapshot readonly
  pasa (árbol de accesibilidad real devuelto), click por vía readonly RECHAZADO. 3 tests nuevos.
- ✅ **Barrido OSS self-hosted — 10 candidatos evaluados** (lista del usuario): veredictos en
  `docs/design/absorption_master_plan.md` (sección "Self-hosted OSS sweep"). ABSORBER: Crawl4AI
  (biblioteca Python, responde directo al hilo de scraping pendiente) + Stirling PDF (candidato al
  catálogo, servicio Docker, promover solo tras prove-it local). PEER: Open WebUI (frontend humano),
  Maxun (app no-code, Crawl4AI cubre lo absorbible). SKIP: Dify/Langflow (solapan la identidad de
  Atlas — mismo error de categoría que el gateway rechazado por el Cónclave), OpenHands (ya cubierto
  por el harness survey). DIFERIDO: Supabase (sin problema de state-store multi-dispositivo hoy),
  Coolify (solo si vuelve el VPS — habría evitado los 18 fix-commits de systemd de mayo). Hallazgo
  lateral: Vercel agent-browser (~200-400 tokens/página) y patrón Playwright CLI (~4x menos tokens
  que su MCP) — a evaluar POR MEDICIÓN cuando aterrice el hilo scraping/desktop.
- ✅ **Crawl4AI absorbido** (2026-07-02, respuesta directa al hilo scraping pendiente). `CrawlerTool`
  (`src/atlas/tools/crawler.py`) + tool `web_crawl` cableada al loop agéntico (read,
  `UNTRUSTED_READERS` → wrap automático ADR-037). Gobernanza igual que `BrowserTool`: SSRF Bridge +
  bloqueo de red privada + Merkle. **Hazard real detectado y evitado** (verificado con `pip download`
  + inspección de wheel, no asumido): `crawl4ai` fija `unclecode-litellm==1.81.13` — se instala bajo
  el MISMO nombre de import `litellm/` que nuestro litellm real (1.89.0, del que depende
  `InferenceHub`) — un `pip install` normal lo habría sustituido en silencio. Aislado en
  `.venv-scraping` (mismo patrón que `redteam`, documentado en `pyproject.toml` + `.gitignore`),
  invocado por subprocess (`_crawl4ai_worker.py`, sin imports de `atlas`). Probado en vivo 2 veces
  (github.com real + servidor HTTP local en tests E2E `computer_use`). 9 tests nuevos
  (`test_crawler.py`), mypy limpio, suite completa verde. **Límite real pendiente de decisión**:
  `SSRFBridge` es allowlist (no blocklist) — la instancia compartida de `BrowserTool`/`CrawlerTool`
  solo permite ~20 dominios de infraestructura hoy, así que scraping a sitios arbitrarios
  mencionados por el usuario fallaría hasta decidir política de ampliación (detalle en
  `docs/design/absorption_master_plan.md`, sección "Crawl4AI absorbido").
- ✅ **SSRFBridge — allowlist ampliada** (decisión del usuario: "allowlist curada más amplia"). 7
  dominios de referencia técnica añadidos (github.com, huggingface.co, en.wikipedia.org,
  stackoverflow.com, arxiv.org, docs.python.org, readthedocs.io) — curados uno a uno, no wildcard.
  7 tests nuevos con resolución DNS real (no mockeada), 34/34 verdes.
- 🔄 **Desktop-control — alcance ampliado por el usuario y slice 1 (GUI) cerrado** (2026-07-02). El
  usuario pidió las 3 piezas (GUI + ficheros fuera del proyecto + invocar Claude Code), en orden de
  riesgo creciente. **Slice 1 (GUI) cerrado**: `computer-control-mcp` cableado al catálogo contra
  `Xvfb :99` (display VIRTUAL dedicado, nunca el `:0` real de la sesión). **Segundo hazard de
  dependencias real** (mismo patrón que Crawl4AI, verificado con `pip download`): fija
  `mcp[cli]==1.13.0` — pin exacto del MISMO SDK del que depende el propio tronco de Atlas (hoy
  1.28.0); instalarlo en el venv principal habría degradado el SDK MCP de Atlas 15 versiones.
  Aislado en `.venv-desktop`. Probado en vivo end-to-end contra el trunk real: `get_screen_size`
  devuelve 1280x1024 (confirma que tocó Xvfb, no el display real); `click_screen` rechazado por
  `trunk_invoke_readonly` (solo 4 tools de lectura pura declaradas de las 15 totales). Modo "display
  real controlado" pendiente (necesita su propio diseño de gating antes de implementar).
- ✅ **Manía nueva: delegar progresivamente en Atlas** (petición explícita del usuario 2026-07-03:
  "más debemos delegar en atlas... conoceremos su alcance real"). Aplicada de inmediato al slice 2.
- ✅ **Slice 2 (ficheros fuera del proyecto) — cerrado, MAYORMENTE delegado a `atlas code --engine
  tool`**. `ExternalFsBridge` (`src/atlas/security/external_fs_bridge.py`, mismo patrón que
  `SSRFBridge` pero para filesystem — fail-closed sin `extra_roots`, resuelve símlinks/`../` ANTES de
  comparar) + tool `read_external_file` cableada en las 4 capas (`agentic_helpers.py`/
  `agentic_executor.py`/`gate_f_executor.py`/`orchestrator.py`, mismo patrón que `web_crawl`).
  **Primer dato real medido sobre el techo de ToolCoder** (detalle en memoria
  `feedback-delegate-to-atlas-progressively`): converge fiable en 1 archivo con patrón exacto a
  copiar (bridge+tests, y 3 de los 4 archivos de wiring — 1 iteración cada uno); falla en coordinar
  4 archivos de una vez (10 turnos sin converger) y se degrada en un archivo grande con 2 métodos
  nuevos en una pasada (quedó a medias, terminado a mano — 25 líneas mecánicas). Mitigación que
  funcionó: 1 llamada por archivo con test aislado. Suite completa verde tras cierre.
- ✅ **Manía nueva: Claude Code es un plus, no una dependencia** (usuario 2026-07-03: "si pago Claude
  Code genial de lo contrario atlas debe ser igual o mejor"). Slice 3 nunca debe convertirse en
  requisito de arranque de Atlas.
- ✅ **Slice 3 (Claude Code como sub-tool) — cerrado**. Bloqueo real de auth encontrado y resuelto:
  `claude -p` (no-interactivo) da 401 con sesión OAuth normal — confirmado DENTRO y FUERA del
  sandbox (no es artefacto del entorno); esta sesión corre como proceso `claude` orquestado por
  Claude Desktop (`--resume <id> --permission-prompt-tool stdio`), que gestiona el OAuth de forma
  distinta a una invocación suelta. Solución: `claude setup-token` (token de 1 año ligado a la
  suscripción, sin API key de pago-por-uso nueva) — guardado en
  `~/.config/atlas-mcp/secrets.env` como `CLAUDE_CODE_OAUTH_TOKEN`. **Incidente de seguridad real
  durante el proceso**: el token quedó expuesto en el chat 3 veces (dos por acción del usuario
  contra mi recomendación explícita, una por un bug de formato — espacio embebido de un salto de
  línea del terminal al copiar visualmente). Mitigado con un método de captura sin copia visual
  (`claude setup-token | tee archivo` + extracción por script) para evitar que se repita. Recomendado
  rotar el token cuando se retome. `ClaudeCodeTool` (`src/atlas/tools/claude_code_tool.py`) delegado
  a `atlas code --engine tool` en 1 iteración (mismo patrón que `CrawlerTool`, reutiliza
  `ExternalFsBridge` del slice 2 para acotar `cwd`) — verificado en vivo contra el CLI real (no
  mockeado): lee un fichero real correctamente, coste real medido ($0.24-$0.40 por tarea trivial con
  `claude-opus-4-8` por defecto — dato operativo a vigilar). Cableada como tool `invoke_claude_code`,
  clasificada **mutate/HITL siempre** (nunca inline) por el coste y alcance reales de delegar en un
  segundo agente completo. Suite completa verde.
- ✅ **Stirling PDF absorbido** (2026-07-03, segundo candidato del barrido OSS). Desplegado real vía
  Docker (`frooodle/s-pdf`), bindeado solo a `127.0.0.1:8090` — 2 intentos de despliegue inseguros
  bloqueados correctamente por el guardrail (desactivar su seguridad interna, exponer a 0.0.0.0).
  **Fricción de auth real documentada**: su API usa JWT bearer en `localStorage`, no la cookie de
  sesión — resuelto automatizando login real vía Playwright + `fetch()` en el propio contexto del
  navegador para generar la API key, guardada en `secrets.env` como `STIRLING_PDF_API_KEY` (2
  intentos de escritura intermedia bloqueados por "Credential Materialization" antes del método
  correcto). `StirlingPdfTool` (multipart a mano, sin deps nuevas) cableada como tool
  `manipulate_pdf`, mutate/HITL, reutiliza `ExternalFsBridge`. Probado en vivo (rotar PDF real, 200
  OK). **Tercer dato sobre el techo de ToolCoder**: primera vez que falló DOS veces seguidas sin
  escribir NADA (ni parcial) — módulo y tests escritos a mano. Contenedor Docker manual, sin systemd
  todavía (igual que Xvfb :99).
- ✅ **Medición real de token-cost Playwright MCP** (2026-07-03, no por claim de blog). Handshake MCP
  real contra 3 páginas de complejidad distinta: docs.python.org (~2984 tokens), lista de preguntas
  de Stack Overflow (~16724 tokens), artículo largo de Wikipedia (~135210 tokens) + coste fijo de
  ~3919 tokens de las 23 definiciones de tool en cada request. El claim del blog ("~2-5KB/snapshot")
  solo se sostiene para páginas simples — contenido denso puede costar 10-100x más. No se instaló
  Vercel agent-browser para comparar por presupuesto de tiempo — queda como siguiente medición si se
  retoma.
- ✅ **Modo "display real controlado" — infraestructura lista, sin activar** (2026-07-03). Nueva
  entrada de catálogo `computer-control-mcp-real-display` (`DISPLAY=:0`), deliberadamente `candidato`
  (NO `verificado` — no se cablea al trunk, verificado con `trunk_children()`) hasta que exista un
  caso de uso concreto; todas sus tools quedan mutate/HITL (sin `read_only_tools`) por diseño. No se
  probó en vivo contra el display real (habría movido el ratón/teclado de la sesión real sin razón).
- ✅ **Patrón de lifecycle de skills (Hermes curator.py) — estudio cerrado, sin código** (2026-07-03,
  como se pidió: patrón, no import). Verificado en el código real: `Lesson` no tiene NINGÚN campo de
  lifecycle (ni status, ni contador de uso, ni last_recalled_at); `corroborated` es un gate de una
  sola vez en creación, no telemetría continua. `LessonRecaller.recall()`/`recall_all()` es el punto
  natural donde se engancharía un futuro `recall_count`/`last_recalled_at`. NO implementado a
  propósito — el volumen real de lecciones hoy (seedeadas a mano) no justifica el lifecycle todavía;
  sería sobre-ingeniería sin masa crítica de datos que gestionar.

## Perfeccionar autoconstrucción + Cónclave + MCP (2026-07-03, plan `/home/ronin/.claude/plans/fizzy-mapping-otter.md`)

Mandato del usuario: "perfeccionar, mejorar, optimizar todo lo mejor posible" en los 3 frentes,
usando dos pasadas de `/autobuild` **sin Opus** (Sonnet en planner/impl/auditor), cerrando con
auditoría final Cónclave + Opus como maestro. 3 Explore agents en paralelo confirmaron que MCP
ya estaba cerrado en lo esencial (solo quedaba el embedder, sin lazo de autobuild); el trabajo
real de autobuild cayó en auto-construcción y Cónclave.

- ✅ **Front A — auto-construcción CERRADO**: `SelfBuildRunner` (`src/atlas/core/
  self_maintenance/self_build_runner.py`) conecta backlog→ToolCoder→ColdUpdateManager
  (`origin="self_audit"` SIEMPRE, invariante CVE-HITL G0.8 intacto: nunca auto-aplica). Auditor
  Sonnet: PASS. 2 bugs reales encontrados EN VIVO y arreglados: (1) targets-directorio rompían
  ToolCoder (`_expand_targets`), (2) intentos fallidos dejaban residuos sin revertir
  (`_revert_new_changes`, confirmado con git repo real en test). Demo real contra `f2-6a`: 2
  intentos, ambos fallaron HONESTAMENTE (uno por Ollama local, otro por tests reales que no
  pasaron) sin proponer nada indebido ni ensuciar el repo — resultado aceptable según el plan.
- ✅ **Front B — Cónclave v2 CERRADO**: bug real confirmado y arreglado (`synthesis_recorder`
  nunca se pasaba en `code_cycle.py`/`atlas_coder.py` — los veredictos del trío nunca se
  destilaban en LessonStore). v2.0.5 fallback por-linaje real (US→groq_llama_70b,
  CN→groq_qwen3, confirmados vivos; EU sin fallback, hueco documentado honestamente, no
  fabricado). v2.1 debate por rondas opt-in (`rounds=1` default = comportamiento previo intacto;
  nunca cuelga, corta ante fallo a mitad de ronda). v2.2 diferido tal como decidió el plan.
  Auditor Sonnet: PASS. 53 tests nuevos.
- ✅ **Front C — MCP CERRADO**: default de `default_embedder()` cambiado stub→fastembed
  (verificado antes: store real con 0 registros, sin datos que migrar). Hallazgo real: el
  propio `LessonRecaller` ya documentaba que su threshold=0.8 dejaba la memoria "prácticamente
  inconsultable" con el stub — el cambio cierra un bug de usabilidad real, no solo optimiza.
  Test que demuestra la mejora con un parafraseo sin solapamiento léxico (fastembed encuentra
  la lección, stub score más bajo para el mismo caso).
- Suite completa verde en cada cierre (2592→2602→2604 passed). Ledgers efímeros de cada front en
  `.autobuild/ledger-*.md`.
- ✅ **Auditoría final — Cónclave real + Opus maestro — CERRADA.** `convene_for_decision()` real
  (no simulado) sobre el conjunto agregado de los 3 fronts: **FAIL unánime 3/3** (Gemini/Kimi/
  Mistral, todos BLOCKING/MAJOR). Un agente Opus, como maestro, verificó cada objeción contra el
  código real (no contra el resumen) — análisis objeción-por-objeción: 1 error factual real de
  Mistral (confundió el cambio de embedder de Front C con el invariante HITL de Front A, que son
  mecanismos disjuntos — el embedder no pasa por `ColdUpdateManager` en absoluto); 3-4 objeciones
  genéricas/hipotéticas o fuera del alcance de lo cerrado hoy (hueco EU ya conocido de antes,
  "Sonnet-sobre-Sonnet" refutado porque el veredicto lo emite el TRÍO no Sonnet, "podría romperse
  en un refactor futuro" aplicable a cualquier invariante); 2 reales-pero-ya-documentadas (n=1 en
  la demo de auto-construcción, snapshot puntual de 0-datos); **1 genuinamente accionable**:
  `fastembed` descarga su modelo ONNX sin pin de hash en el primer uso (hallazgo real de Kimi,
  el docstring de `FastEmbedEmbedder` afirmaba "ni red" — inexacto, corregido).
  **Veredicto del maestro: el trabajo SE QUEDA, con 2 arreglos baratos** (no revertir nada):
  (1) docstring de `FastEmbedEmbedder`/comentario de `pyproject.toml` corregidos para reflejar
  honestamente la descarga de red en primer uso + cómo optar por `ATLAS_EMBEDDER=stub` si hace
  falta evitarla; (2) test de regresión explícito
  `test_tier1_auto_apply_rejects_self_audit_origin` — el invariante CVE-HITL ya era código
  fail-closed real, pero solo tenía cobertura de test para `origin='manual'`, no para
  `'self_audit'` específicamente (el origin que usa `SelfBuildRunner`) — ahora tiene red de
  seguridad explícita, no solo lectura de código. Ambos arreglos aplicados, verificados
  (25 tests en `test_cold_update_manager.py`, suite completa verde). **Manía aplicada**: "retar
  al trío" — no se aceptó el FAIL mecánicamente ni se descartó; se verificó objeción por objeción
  contra el código real y se corrigió al trío donde sobre-afirmó.

## SP-A — mesa de trabajo compartida (2026-07-03) — CERRADO

Ítem huérfano desde el 26 de junio (`WORK_LEDGER.md` histórico): bloqueado por
`mcp-audit-six-primitives` (el MCP no exponía Resources), bloqueo que se cerró esa misma
sesión pero nadie volvió a mirar el ítem tras eso. Retomado a petición explícita del usuario
tras preguntar por qué, a estas alturas, no todos los agentes/subagentes comparten
automáticamente memoria+contexto+herramientas.

`workbench://manifest` (`src/atlas/mcp/workbench_resources.py`, nuevo + registro en
`trunk_server.py::build_trunk_server()`/`serve()`) — agrega catálogo+lecciones+backlog+memoria
en un único Resource MCP, mismo patrón exacto que `catalog_resources.py`. Aditivo/fail-soft
(si falta cualquier fuente, no rompe el arranque). `backlog_summary()` nuevo en `backlog.py`.
Delegado en parte a un subagente Sonnet (piezas puras + tests, convergió limpio en 1 pasada);
cableado en `trunk_server.py` hecho directo por tocar un archivo ya muy trabajado hoy. Probado
en vivo con handshake MCP real contra un tronco fresco: catálogo 733 items, backlog 30 reales
(top-1 pendiente = `f2-6a`, el mismo item que se intentó auto-construir en el Front A de hoy),
lecciones 0, memoria 0. 22 tests nuevos, mypy limpio, suite completa 2616 passed.

**Límite real investigado y documentado, no fingido resuelto**: la tool `Agent`/`Task` que uso
para despachar subagentes NO tiene ningún parámetro para darle acceso a un servidor MCP al
subagente que spawnea (verificado en su esquema real) — es una limitación de la superficie de
la tool, fuera de mi control. Mitigación práctica adoptada: leer `workbench://manifest` yo
mismo antes de delegar y pegar el resumen relevante en el prompt del subagente, en vez de
asumir herencia automática. Detalle en `docs/design/absorption_master_plan.md`, sección "SP-A".

## Desconexión real de memoria/lecciones — investigado y arreglado (2026-07-03, mismo día)

El usuario pidió profundizar en por qué el manifiesto SP-A mostraba 0 lecciones/0 memoria en
vez de asumirlo. Hallazgo real, verificado (no imaginado): **hay un daemon vivo de verdad**
(`atlas serve`, PID 5117, corriendo desde el 2 de julio, 2939 entradas Merkle reales, ciclos de
self-audit hoy mismo) — pero **5 convenciones de ruta distintas para "el mismo" LessonStore**,
sin fuente única de verdad. La única con datos reales: `<repo>/workspace/lessons` (usada por
AtlasCoder/ToolCoder, 8 lecciones reales con contenido genuino). El propio self-audit del
Orchestrator (`maintenance_facade.py`) apuntaba a `<ATLAS_HOME>/memory/lessons` — **directorio
que ni siquiera existía** — el daemon vivo nunca había visto las lecciones que su propio motor
de codificación generó. `scripts/seed_lessons.py` y mi propio cableado de SP-A apuntaban a otras
2 rutas más, también vacías.

**Unificado a `<repo_root>/workspace/lessons`** en los 3 sitios de producción
(`maintenance_facade.py`, `trunk_server.py`, `seed_lessons.py`; los scripts de `redteam/` se
dejaron intactos, aislamiento deliberado del servicio vivo, correcto por diseño). Verificado en
vivo: `workbench://manifest` ahora reporta **11 lecciones reales** (8 + 3 sembradas), no 0.

**Segundo hallazgo, más profundo**: hay DOS sistemas de memoria paralelos —
`SqliteMemoryIndex`/MCP (vacío, usa `default_embedder()`) vs `KuzuVectorStore` (grafo real, el
que usa de VERDAD el Orchestrator en Gate D, activo en producción vía
`ATLAS_PIPELINE_GATE_D=1` confirmado en `.env`). Gate D **hardcodeaba `StubEmbedder()`**
(`orchestrator.py::enable_gate_d_pipeline()`), ignorando el cambio de default de Front C.
Verificado ANTES de tocar: `approved_patterns`/`error_registry` (únicos consumidores reales del
vector store) estaban vacíos — sin vectores dim=64 reales que perder. Arreglado a
`default_embedder()`. `KuzuVectorStore._verify_dim()` es fail-closed (nunca corrompe
silenciosamente) — requiere reiniciar el daemon vivo para tomar efecto; **no se reinició sin
preguntar** (acción sobre un servicio en producción).

**Efecto colateral encontrado y arreglado en el mismo pase**: el cambio de embedder de Gate D
hacía que la suite de tests que activa ese pipeline cargara el modelo ONNX real en cada test
(57s solo `test_orchestrator_pipeline_d.py`, antes instantáneo). Añadido `ATLAS_EMBEDDER=stub`
a la fixture `autouse` de aislamiento de entorno ya existente en `tests/conftest.py` (mismo
patrón que las demás variables ya aisladas) — 57s→6.2s. Suite completa: 2616 passed, **más
rápida que antes** (144s vs 172s), mypy limpio.

**Pendiente, decisión del usuario**: reiniciar `atlas serve` (PID 5117) para que Gate D tome el
nuevo embedder. Detalle completo en `docs/design/absorption_master_plan.md`.

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
  - ✅ 2.3 evaluación honesta (autobuild 2026-06-24: benchmark anti-leak + 10 tests; **LongMemEval_S n=500 k=5: cosine=0.294, hybrid=0.356, temporal=0.294** — hybrid +21%, knowledge-update +100%; baseline en `docs/reference/reports/longmemeval_s_baseline_2026-06-26.json`) · ⬜ 2.4 envenenamiento (parcial)
  - ⬜ 2.5 fuga entre usuarios/tenancy · ✅ 2.6 (mitad tratable; clasificador automático = muro 1c registrado) · ✅ 2.7 cold-start (conceptual)

## Línea activa: copia digital (RecordingDecider → TwinDecider → reducción HITL)

Design doc: `docs/superpowers/specs/2026-06-25-recording-decider-design.md`

- ✅ **Slice 1 — RecordingDecider** (2026-06-26): wrapper transparente del Decider Protocol.
  `decision_record.py` (DecisionRecord + DecisionSink + JsonlDecisionSink + InMemoryDecisionSink) +
  `recording_decider.py` (best-effort, firewall D por construcción, decider_version=code-hash) +
  cableado opt-in `ATLAS_DECISION_LOG=<path>` en `make_decider`. 15 tests, mypy strict, 2355 verdes.
  Invariantes verificados: transparencia (3 tipos), record_id==action_hash, best-effort, firewall D,
  sin API de lectura, decider_version estable, opt-in/out.
- ✅ **Slice 1b — MemoryDecisionSink** (2026-06-26): sink de producción. Fernet+shred+merkle+ProvenanceWriteGate.
  Split A verificado en test: shred del rationale deja features intactas (merkle sobrevive).
  ATLAS_DECISION_LOG=memory:<db>. 9 tests, mypy strict, 2364 suite verdes. Commit real: `059bf54`.
  NOTA git (2026-06-26): existe `cd01791` con el MISMO mensaje pero contenido = regeneración YAML de catálogo
  (mal etiquetado por confusión de `chore/mcp-sync`), NO el código decider. Decidido NO reescribir historia
  (ni rebase ni resubida desde cero): hay remoto real + 426 commits + tags paper/gates + ~30 ramas Hermes sin
  mergear; coste/beneficio pésimo y contradice la tesis de procedencia verificable. Detalle en
  [[session-2026-06-26-git-history-decisions]]. Poda auditada de las ~30 ramas Hermes: ✅ HECHA
  2026-07-02, ver sección "Hermes Agent — auditoría/inventario" arriba.
- ✅ **Slice 2 — record_human_verdict** (2026-06-27, G0.9): `RecordingDecider.record_human_verdict(action_hash_val, verdict)` — guarda la resolución humana de un RequiresHuman como `kind="human_resolution"` en el sink, atable al record original. Best-effort.
- ✅ **Slice 3 — TwinDecider shadow** (2026-06-27, G0.9): `TwinDecider` wraps any Decider + corpus sink. `ShadowPredictor` (mayoría por kind/mutating/reversible, warmup MIN_CORPUS_SIZE=30). `ShadowAccuracyLog` acumula hits/total. Veredicto del inner NUNCA alterado (firewall D). 15 tests, mypy limpio.

## Línea activa: capacidades usables (catálogo → routing) — NUEVA 2026-06-26

Design: `docs/design/design_catalog_enrichment.md`. Memoria: [[capability-routing-structural]] · [[adopt-real-not-shell]].
Origen: el modelo no usa lo propio (MCP/skills/prompts) porque la autoselección es probabilística, no
determinista (solo un hook/router lo fuerza). Fundación = hacer el catálogo USABLE (hoy 700+ = solo
nombres), luego enrutarlo a la fuerza. 3 ejes ortogonales: purpose(afirmado)/signal(prior popularidad)/
status(verificación) — nunca confundir.

- ✅ **Pieza 1 — enriquecer** — CONSTRUIDO + auditado + **MERGEADO a main** (2026-06-26).
  `enrichment.py` (rellena purpose-afirmado + signal de la fuente, `status` INTACTO, idempotente) +
  `scripts/mcp_enrich.py` + 16 tests. Reusa HttpApiSource+SSRFBridge (0 deps). Suite 2340 verde, auditor
  Opus PASS (SSRF probado con inyección). 554 entradas enriquecibles (--offline). Gap declarado: sub-ítems
  de awesome-lists y caracterización de prompts FUERA de Pieza 1.
- ⬜ **Pieza 2 — trial-en-jaula per-kind + escáneres adoptados** ← SIGUIENTE. Rompe la serpiente-cola
  (candidato→verificado). Estado graduado: candidato → probado-en-jaula (funciona+CONTENIDO, sin red) →
  verificado-confiado (escáner + uso/humano). Escáneres por-primitivo ADOPTADOS (envolver, no forkear:
  `adopt-real-not-shell`; candidatos: Invariant mcp-scan, Snyk agent-scan). Barrido por saneamiento
  graduado (candidato rancio → cuarentena → delete, NUNCA de una pasada). Defensa = CONTENCIÓN (jaula) +
  detección (escáner adoptado), no un antivirus propio (no-existe).
- ⬜ **Pieza 3 — routing hook** `UserPromptSubmit` que consume el catálogo ya enriquecido/verificado
  (consumo determinista). El más fácil, el último (necesita 1 y 2).

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
- ✅ **#1 Resources del catálogo CONSTRUIDO** (spec `docs/superpowers/specs/2026-06-25-catalog-resources-design.md`):
  `catalog_resources.py` (builder puro: `manifest_json` con 4 ejes + summary + `fresh`-hash · `item_detail`
  por kind/name; 8 tests) + 2 resources aditivos en `trunk_server.py` (`catalog://manifest` +
  `catalog://item/{kind}/{name}`; test in-process FastMCP con mcp 1.28 en `.venv`). mypy strict limpio. Los
  tools `trunk_catalog/find/kinds` siguen intactos. Backlog `catalog-resources-mcp` done.
  ⚠️ **Push de subscriptions NO incluido** (decide-with-facts: FastMCP high-level no expone `resources/updated`;
  existe solo en el Server low-level). Entregado `fresh`-hash para change-detection; push = follow-up
  `catalog-resources-live-subscriptions` (pendiente). wire-before-claim: no se fingió.
- ✅ **#2 Prompts para skills CONSTRUIDO**: en `build_trunk_server`, cada skill servido se registra TAMBIÉN
  como Prompt MCP nativo (`add_prompt`/`Prompt.from_function`), descubrible por el cliente sin tool-call; cuerpo
  cargado perezosamente vía `skill_store.get`. Aditivo a `list_skills`/`get_skill`. Test in-process
  (list_prompts ⊇ skills, get_prompt = contenido). mypy strict limpio.
- 🔄 **CIERRE DEL MCP en curso** (decisión usuario: 6 primitivos + Tasks). `trunk_capabilities.py`:
  ✅ **Completion** (autocompletado catálogo/skills) · ✅ **Logging+Progress** (`trunk_selfcheck`) ·
  ✅ **Elicitation** (`trunk_confirm`, hook HITL) · ✅ **Sampling** (`trunk_reason`, base SP-B) ·
  ✅ **Roots** (`trunk_list_roots`). 6 tests vía harness in-memory (cliente real), mypy strict.
  Client-features = capacidad lista; consumidor pleno = SP-E. Spec
  `docs/superpowers/specs/2026-06-25-mcp-close-primitives-design.md`.
  ✅ **LOTE C**: push-subscriptions REAL (subscribe/unsubscribe + seam publish `trunk_notify_catalog_changed`;
  el cliente recibe `resources/updated`, 7º test). Watcher AUTOMÁTICO diferido (`mcp-subscriptions-auto-watcher`,
  necesita low-level loop). Tasks ⏸ VERIFICADO sin soporte SDK (solo tipos) → se construye CON SP-E
  (`mcp-tasks-extension`); es el motor del loop async.
- ✅ **MCP CERRADO** (decisión usuario): 6 primitivos + Completion/Logging/Progress + subscriptions. Lo único
  fuera = lo que honestamente depende del workflow (Tasks) o de consumidor en caliente (auto-watcher).
  **PRÓXIMO según la estrategia del usuario: el workflow Dynamic (SP-E) → capacidad de auto-construir de Atlas.**
- 🔵 **Hallazgo extra (investigado)**: hay MÁS que 6 primitivos (Completion/Resource-templates/Subscriptions/
  Logging/Progress) Y se EXPANDEN vía **Extensions** (`atlas/...`, opt-in, aditivas). Oficiales: **Tasks**
  (async largo → loop autónomo/SP-E) y **MCP Apps** (UI HTML iframe → mesa SP-A). Detalle en el audit doc.
  → **PRÓXIMAS ACCIONES posibles**: #2 Prompts para skills · embedder local (`memory-mcp-local-embedder`) ·
  push-subscriptions del catálogo · explorar Tasks/MCP-Apps para SP-E/SP-A.
- 🔄 **Hallazgo embeddings (investigado)**: memory MCP corre sobre `StubEmbedder(dim=64)` (hash, no semántico).
  `LiteLLMEmbedder` ya existe y NO es Gemini-locked. Pero API hospedada = lock-in (usuario lo rechaza con razón).
  Respuesta universal = modelo LOCAL in-process (BGE-M3/Qwen3-0.6B/EmbeddingGemma-300M/MiniLM). Trade-off:
  dep pesada + descarga vs stub cero-deps. → backlog `memory-mcp-local-embedder` (prio-2, DEPENDE del audit).
- ⏸ **Visión larga (registrada, NO empezada — cada una su spec→plan cuando toque)**:
  - SP-B **regulador de tokens**: conoce gasto, sube/baja consumo según dificultad (atada al modelo), acelera lo
    fácil, cuida lo difícil.
  - SP-C **memoria al máximo**: trust-scoring, FTS/híbrido, grafo temporal tipado, recall verbatim-sin-resumen
    (anti-alucinación, lección Hermes), user-modeling. ✅ **Ladrillo 1 HECHO: embedder local semántico** —
    `FastEmbedEmbedder` (fastembed/ONNX, SIN torch; extra opcional `[embeddings]`; modelo multilingüe
    paraphrase-MiniLM-L12-v2 dim 384). `default_embedder()` por env `ATLAS_EMBEDDER=fastembed` (opt-in;
    default stub; fail-closed). Cableado en memory_server + MemoryTrunk. Verificado EN VIVO (test semántico
    español verde).
    ✅ **Ladrillos 2-3 HECHOS (autobuild 4 fases, commit b688721, auditor PASS):** retrieval **híbrido**
    (FTS5 léxico OPT-IN default-OFF + recall_lexical bm25 + rrf_fuse; crypto-shred del plaintext FTS
    verificado en vivo) y **temporal** (recall_temporal as_of + recencia, determinista/auditable) + andamio
    de ablación en `eval_memory_benchmark` (modos cosine/hybrid/temporal). 46 tests, mypy strict, 0 deps.
    **Hallazgo empírico:** el corpus sintético NO discrimina (3 modos idénticos → confirma que hace falta
    LongMemEval); demo dirigida: TEMPORAL gana claro (as_of reconstruye el pasado), HÍBRIDO marginal sobre
    fastembed → medir en LongMemEval, no asumir. Ver [[memory-program-conclave-verdict]].
    **Programa de memoria SENTENCIADO por el Cónclave** (enjambre 6 agentes + trío, 2026-06-25): MEDIR
    primero (LongMemEval_S) = go/no-go · decay NO (rompe auditabilidad+GDPR) · invención reencuadrada (sin
    PBFT-sobre-borrado) · derivar-usuario solo si auditable. Atlas adelante en verificable+borrado-auditable,
    detrás en temporal/híbrido/medición. NOTA: la sesión paralela añadió `kuzu>=0.11` (graph DB) → infra para
    el grafo temporal tipado cuando se aborde. Siguientes: LongMemEval (el harness ya está listo), trust-scoring.
  - SP-D — ✅ **slice 1 SPEC'd** (`docs/superpowers/specs/2026-06-25-recording-decider-design.md`):
    `RecordingDecider` (graba decisiones para el corpus de la copia digital), con las 4 correcciones del
    Cónclave (split features/rationale, schema+versión-decider, shadow-medible, firewall-sensibilidad) y el
    principio de SUSTRATO UNIFICADO. NO construido aún. Ver [[conclave-recordingdecider-blindspots]],
    [[atlas-unified-substrate-principle]].
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
