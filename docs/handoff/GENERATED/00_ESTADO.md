<!-- GENERADO por atlas handoff 2026-07-23T16:18:38.103790+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

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
    como fallback (ya declarado en `custom_providers`, sin usar). CAVEAT sin
    verificar en vivo: un intento anterior con Groq falló por límite de
    contexto/TPM de la cuenta on-demand — necesita que el operador mande un
    mensaje real y confirme.
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
