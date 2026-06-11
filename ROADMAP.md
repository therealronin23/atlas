# ATLAS — Hoja de Ruta

> Estado actual: **v0.12.0** — Gates A–I sellados + arquitectura twin Atlas↔Hermes
> viva (ADR-026..029) + block memory estilo Letta (ADR-030) + loop agéntico de
> tool-calls (ADR-031) + loop suspendible con HITL inline para mutaciones
> (ADR-032) + refinamientos del loop: auto-approve allowlist, aprobación
> parcial, barrido TTL y traza de progreso (ADR-033), cableados a CLI/serve/
> Telegram/dashboard + endurecimiento del subprocess de ejecución: no-new-privs,
> rlimits fsize/nproc/nofile y sesión aislada (ADR-034) + modelo de amenazas y
> hoja de murallas (ADR-036) + frontera de contenido no confiable, P0
> (ADR-037) + gate de adopción Atlas Sentinel fail-closed (ADR-038) + cliente MCP
> con registro dinámico add/remove en caliente (ADR-035 dec.3). Decomposición del
> orchestrator: 6 slices mecánicas + núcleo recursivo (`AgenticExecutor`)
> extraídos. 943 tests verdes + mypy 0.
> Última sincronización: 2026-06-04.
>
> **En curso:** ADR-039 (agente de auto-mantenimiento) — slices 1-3 landed
> (Scout read-only + Analyst dual-LLM/corroboración + wire propuesta→adopción
> vía el seam del decisor); slices 4+ (cron, descubrimiento externo, deps,
> codegen) en diseño. ADR-040 (decisor central + human-ON-the-loop) COMPLETO.
>
> **Cabos abiertos consolidados:** ver sección [Pendientes](#pendientes--cabos-abiertos)
> al final. Este es el único documento que mantiene la lista viva de "qué falta".

---

## Gates Cerrados

| Gate | Estado | Tag | Descripción |
|------|--------|-----|-------------|
| A | ✅ SEALED | — | Visión, entidades y principios fijados. |
| B | ✅ COMPLETE | — | Core local funcional (102 tests baseline). |
| C | ✅ COMPLETE | `v0.2-gate-c` | Hermes-VPS en Hetzner CPX22 + Tailscale + Telegram bot + REST HMAC. 147 tests. |
| D | ✅ COMPLETE | `v0.3-gate-d` | InferenceHub real (LiteLLM), KuzuDB vector+graph, MemoryDistiller, capability tokens, Time-Travel, Ghost Replay, PII Surrogate, SLM Classifier, pipeline integrado opt-in. 368 tests. |
| E | ✅ COMPLETE | `v0.4-gate-e` | ADR-002 sealed (bare metal + venv), Dashboard web (FastAPI+Jinja2, localhost:7331), Voz (Whisper STT + Piper TTS). 449 tests. |
| F | ✅ COMPLETE | `v0.5-gate-f` | Computer-use con BrowserTool, EditorTool, VisionLoop conservador, Orchestrator routing, approval states y smoke real de host. 509 tests. |
| G | ✅ COMPLETE | `v0.6-gate-g` | Operacionalización local: Hermes-VPS restaurado, GitHub synced, approvals persistentes CLI, Telegram autorizado y smoked. 513 tests. |
| H | ✅ COMPLETE (MVP) | `v0.7-gate-h` | Síntesis auditada H1–H6: ResultAuditor, receipts, rebuild, fail-safe, meta-gov, env sensor. |
| I | ✅ COMPLETE (MVP) | `v0.8-gate-i` | Servicio 24/7: `atlas serve`, health, OfflineMonitor+Telegram, optional dashboard/thermal. |

Cada Gate tiene su documento de cierre en `docs/gate_*_seal.md`.

---

## Gate F — COMPLETE

Computer-use + Editor integration + Frontend.

Plan operativo: [`docs/gate_f_plan.md`](docs/gate_f_plan.md).
Seal: [`docs/gate_f_seal.md`](docs/gate_f_seal.md).
ADR-013b: [`docs/adr_013b_computer_use.md`](docs/adr_013b_computer_use.md).
Plan maestro de absorción/forking selectivo:
[`docs/absorption_master_plan.md`](docs/absorption_master_plan.md).
Readiness bare-metal: [`docs/gate_f_real_world_readiness.md`](docs/gate_f_real_world_readiness.md).
Arquitectura Atlas Box/flota: [`docs/atlas_box_architecture.md`](docs/atlas_box_architecture.md),
[`docs/fleet_security_plan.md`](docs/fleet_security_plan.md).
Notas de producto no legales:
[`docs/product_strategy_notes.md`](docs/product_strategy_notes.md).
Notas futuras Gate H:
[`docs/gate_h_resilience_plan.md`](docs/gate_h_resilience_plan.md).

### F1 — Computer-use con Playwright
- Browser automation con Playwright (navegar, rellenar formularios, screenshots): scaffold implementado en `src/atlas/tools/browser.py`.
- Loop visual: screenshot → VLM (Gemini free / LLaVA local) → describe → Atlas decide acción.
- Todo pasa por SSRF Bridge.
- Tests con páginas estáticas locales: implementados en `tests/test_browser.py`.
- DONE: logging Merkle de acciones browser.
- DONE: policy explícita para allowlist local/extra mediante `allow_private_network=True`.

### F2 — Integración Cursor/VS Code
- `src/atlas/tools/editor.py`: open_project, apply_diff, run_task scaffold implementado.
- Flujo: `atlas task "crea componente React"` → Atlas planifica → genera código → aplica via editor → abre Cursor.
- Tests implementados en `tests/test_editor.py`.
- DONE: read/write/apply_diff/run_task enrutados por PermissionProfile + AtlasExecutor + MerkleLogger.
- DONE: `run_task` elimina `shell=True` del path publico y usa comando estructurado allowlisted.
- DONE: tests negativos de rutas y comandos bloqueados.

### F3 — VisionLoop conservador
- F3 visual loop MVP: `src/atlas/tools/computer_use/vision_loop.py` propone acciones tipadas desde screenshot y fuerza aprobación para acciones mutantes.
- Tests: `tests/test_vision_loop.py`.

### F4 — Orchestrator routing
- `src/atlas/core/orchestrator.py` enruta comandos explícitos `browser`, `editor`
  y `vision`.
- Acciones observacionales (`editor read`, `browser screenshot/extract`,
  `vision propose`) pueden ejecutarse directamente.
- Acciones mutantes (`browser navigate/click/fill`, `editor write/run/apply_diff/open`)
  quedan en `AWAITING_APPROVAL` y se ejecutan solo via `approve_pending`.
- Tests: `tests/test_orchestrator_gate_f.py`.

### Post-F — endurecimiento del subprocess (ADR-034) ✅ parcial
- ✅ HECHO: no-new-privs (`prctl`), rlimits `FSIZE`/`NPROC`/`NOFILE` añadidos a
  `AS`/`CPU`/`CORE`, y `start_new_session=True` (sesión aislada). Stdlib-only,
  `src/atlas/security/process_hardening.py`, 6 tests.
- ⏳ PENDIENTE: filtrado de syscalls vía seccomp-bpf — exige dep nueva
  (`pyseccomp`/`libseccomp`, choca con regla 6) y validación con tooling de
  kernel no disponible en local. Hook dejado en `apply_in_child`.

### Gate G/H candidate — ColdUpdateManager (self-improvement protocol)
- Snapshot completo → generar N+1 → ejecutar tests → si mejoran métricas, proponer swap vía Telegram.
- HITL obligatorio (confirmación humana).

---

## Gate G — COMPLETE

Operational readiness: make the sealed Gate F capabilities usable from local
operations without losing state between commands.

- DONE: Hermes-VPS restored on CPX22; Tailscale reachable; `scripts/hermes_smoke.py` PASS.
- DONE: GitHub `main` and tag `v0.5-gate-f` pushed.
- DONE: CLI pending approvals persist on disk.
- DONE: `atlas pending` and `atlas approve <task_id>` implemented.
- DONE: Telegram token configured locally in `.env`.
- DONE: Telegram chat authorization discovered via `/start`; `TELEGRAM_CHAT_ID` configured locally; outbound Telegram smoke PASS.

---

## Post-Gate-I — Observabilidad, ColdUpdate y arquitectura Twin

Trabajo posterior al sellado de los Gates A–I. No abre Gates nuevos; son ADRs
que extienden el runtime sellado.

| ADR | Estado | Descripción |
|-----|--------|-------------|
| ADR-024 | ✅ SEALED (MVP) | Observability/logging v2. |
| ADR-025 | ✅ SEALED (MVP) | ColdUpdateManager (self-improvement, HITL). |
| ADR-026 | ✅ Accepted | Arquitectura twin Atlas (laptop) ↔ Hermes-Agent (VPS). |
| ADR-027 | ✅ Accepted | `/api/exec/intent` — Hermes delega intents a Atlas (HMAC). |
| ADR-028 | ✅ Accepted | Twin kanban bridge Atlas→Hermes (SSH). |
| ADR-029 | ✅ Accepted | `/api/exec/audit` (reverse-audit) + búsqueda FTS5. |
| ADR-030 | ✅ Accepted | Block memory estilo Letta/MemGPT (core memory siempre-en-contexto). |
| ADR-031 | ✅ Accepted | Loop agéntico de tool-calls (grounding factual + auto-edición de blocks). |
| ADR-032 | ✅ Accepted | Loop agéntico suspendible/reanudable: HITL inline para tools mutantes de host. |
| ADR-033 | ✅ Accepted | Refinamientos del loop: auto-approve allowlist, aprobación parcial, barrido TTL de loops abandonados, evento `agentic.progress`. |
| ADR-034 | ✅ Accepted | Endurecimiento del subprocess de ejecución: `PR_SET_NO_NEW_PRIVS`, rlimits `FSIZE`/`NPROC`/`NOFILE` + sesión aislada. seccomp como hook futuro. |
| ADR-036 | ✅ Accepted | Modelo de amenazas y hoja de murallas defensivas priorizada (anclado en CoSAI/NSA/CSA + CVEs reales). |
| ADR-037 | ✅ Accepted | Frontera de contenido no confiable (muralla P0): procedencia, envoltura de datos externos y taint que anula auto-approve post-ingesta. Slice 1. |

Detalle del twin en `docs/adr_026..029`; block memory en `docs/adr_030_block_memory.md`.

- **Twin operativo**: Hermes (Nous Research, VPS Hetzner) delega a Atlas vía
  `/api/exec/intent`; Atlas devuelve resultados auditados. Bot Telegram
  `@GodAtlas_bot` como front conversacional.
  **⏸️ PAUSADO (2026-06-11):** el VPS Hetzner fue dado de baja. Pausa limpia:
  sin `HERMES_BASE_URL` el adapter degrada a mock, y con `ATLAS_HERMES_LOCAL=1`
  (activo en el `.env` de producción) las tareas `DELEGATE_HERMES` se ejecutan
  en local en vez de pudrirse en la `OfflineQueue` (`hermes.local_takeover` en
  Merkle). `HERMES_API_KEY` se conserva en el `.env`: es el fallback HMAC de
  `pending_store` para firmar approvals. **Reabrir cuando:** Hermes se levante
  en otro host (basta restaurar `HERMES_BASE_URL` y quitar el flag).
- **Block memory**: bloques etiquetados con límite de caracteres, siempre
  inyectados al contexto antes del archival. Mutación vía CLI `atlas blocks` y
  API; auto-edición por el modelo **diferida** (necesita loop agéntico de
  tool-calls, ver Pendientes).
- **Endurecimiento Merkle** (commit dc497c7): `MerkleLogger.append` con
  `flock` exclusivo + relectura de hash desde disco + `fsync`; `session.started`
  fuera de `Orchestrator.__init__` (el CLI one-shot ya no escribe al arrancar).
  Validado en el crash del 2026-05-29: cadena íntegra (528 records) pese a
  apagado sucio.

---

## Pendientes / Cabos abiertos

> Lista viva consolidada (la que antes no existía en ningún sitio). Actualizar
> aquí cuando algo se cierre o aparezca.

### Funcionales
- ✅ **Grounding factual** — RESUELTO (ADR-031). Loop agéntico de tool-calls:
  el modelo consulta git/fs/status/blocks reales en vez de alucinar. El routing
  por keywords de `_execute_task` se mantiene como fast-path determinista.
- ✅ **Auto-edición de block memory por el modelo** — RESUELTO (ADR-031).
  El modelo edita sus bloques vía `edit/append_memory_block` dentro del loop;
  `BlockLimitExceeded` se le devuelve como presión (resume), no como crash.
- ✅ **E2E twin Telegram→Hermes→Atlas** — SELLADO EN VIVO (2026-05-29). Mensaje
  real al bot `@GodAtlas_bot` → Hermes delega `/api/exec/intent` → Atlas aterriza
  `git.log` contra el repo real → el bot muestra los commits reales. Cadena Merkle
  íntegra (547/547). Cubierto por `scripts/twin_e2e_smoke.py` (+ `--live <url>`) y
  `tests/test_exec_api.py::test_intent_grounds_git_log_not_hallucination`.
- ✅ **Grounding git apuntaba al directorio equivocado** — RESUELTO (commit
  `3f4f5d1`). El smoke en vivo destapó que `_run_git_*` corría en el workspace
  `~/atlas` (NO es repo git) → toda pregunta git devolvía `fatal`. Fix: `git -C
  <ATLAS_REPO_ROOT>` con SEC-01 endurecido (solo el repo propio, solo subcomandos
  read-only). Atlas es ahora **inmune** a que el intent traiga un path erróneo.
- ✅ **Hermes atribuía ruta incorrecta en su prosa** — RESUELTO (commit `d835231`,
  2026-05-29). Diagnóstico real: NO era `SOUL.md`/memories (limpios). Para
  preguntas de commits el modelo solo delega `git.log` y nunca lee `atlas status`,
  así que no tenía la ruta en contexto: primero copiaba el literal del skill
  (`/home/ronin/atlas`) y, al borrarlo, **confabulaba** uno nuevo
  (`/home/rocio/Atlas-OS`). Cadena de fixes: (1) `git -C <repo_root>` (3f4f5d1);
  (2) `repo_root` en `AtlasStatus` (81b1cf7); (3) skill del VPS con 0 literales de
  ruta + regla "no nombrar ruta"; (4) **fix de raíz**: todo resultado git incluye
  `repo_root` y `_stringify_tool_result` lo expone como línea de procedencia, así
  el gemelo tiene la verdad en el output y no inventa. Verificado en vivo: el bot
  cita `/home/ronin/proyectos/atlas-core` correctamente.
- ✅ **Tools mutantes dentro del loop** — IMPLEMENTADO (ADR-032). El loop
  agéntico es ahora **suspendible/reanudable**: cuando el modelo pide una tool
  mutante de host (browser/editor) el loop serializa su estado completo
  (`messages`, `iterations`, `tools_used`, mutaciones pendientes) en el registro
  de pending approval bajo `agentic_state`, pasa a `AWAITING_APPROVAL` y notifica
  por el canal de approvals existente. Al aprobar, `approve_pending` rehidrata el
  estado, ejecuta la mutación con clearance (`mark_confirmed`) y **reanuda** el
  loop exactamente donde quedó. DENY sin abort inyecta una denegación sintética
  y reanuda (presión MemGPT → re-planifica); con `abort=True` → `CANCELLED`. El
  presupuesto `max_iters` persiste a través de suspensiones. El estado vive en
  disco → sobrevive reinicios del servicio. Las tools de lectura + block memory
  siguen corriendo inline (sin cambios). Auditado en Merkle (`task.suspended` +
  `task.approval` + `tool.invoked`).
  📐 [`docs/adr_032_mutating_tools_in_loop.md`](docs/adr_032_mutating_tools_in_loop.md)
  Status: **Accepted**. 8 tests dedicados (`tests/test_orchestrator_mutating_loop.py`)
  + suite completa (708) en verde, mypy limpio.
- ✅ **Refinamientos del loop suspendible** — IMPLEMENTADO (ADR-033). Cierra los
  cuatro ítems que ADR-032 dejó fuera de MVP: (1) `sweep_expired_suspensions(ttl)`
  cancela loops abandonados (opt-in `ATLAS_AGENTIC_SUSPENSION_TTL`, off por
  defecto); (2) allowlist de auto-aprobación (`set_agentic_auto_approve` / env
  `ATLAS_AGENTIC_AUTO_APPROVE`) — mutaciones de bajo riesgo corren inline con
  clearance y auditadas (`task.auto_approved`), salvo sensibilidad alta; (3)
  aprobación parcial vía `approve_pending(..., approve_only=[ids])` ejecuta un
  subconjunto del lote y deniega el resto con presión sintética; (4) evento
  `EventType.AGENTIC_PROGRESS` por iteración para dashboard/Telegram. Seguro por
  defecto: allowlist vacía + TTL off → comportamiento idéntico a ADR-032.
  Cableado a superficies: `atlas serve` barre loops expirados en su tick
  (`ATLAS_AGENTIC_SWEEP_S`); `atlas approve --only/--abort` + `atlas sweep` +
  `atlas pending` con mutaciones; Telegram `on_agentic_progress` (opt-in) y
  `/pending` enriquecido; dashboard `GET /api/agentic/progress`.
  📐 [`docs/adr_033_agentic_loop_refinements.md`](docs/adr_033_agentic_loop_refinements.md)
  Status: **Accepted**. 9 tests de motor (`tests/test_orchestrator_agentic_refinements.py`)
  + 8 tests de superficie (`tests/test_adr033_surfaces.py`) + suite completa (725)
  en verde.

### Upstream / externos
- ✅ **`mcp_serve` roto** — CERRADO localmente (sin acción nuestra posible).
  Hermes upstream `NousResearch/hermes-agent`, `hermes_cli/mcp_config.py:748` hace
  `from mcp_serve import run_mcp_server` pero el módulo top-level `mcp_serve` no se
  empaqueta → `ModuleNotFoundError`. Reproducido en vivo en VPS (hermes-agent
  0.15.0, Py3.14, pip install, NO NixOS → distinto de #22110). Causa raíz = misma
  clase que el refactor #14590 (top-level modules → `hermes_agent/`). Issue
  publicado upstream: `NousResearch/hermes-agent#34871`.
  **Reabrir cuando:** upstream publique fix → subir el pin de `hermes-agent` y
  reverificar en el VPS.

### Infra / operación
- ✅ **SSD SanDisk SD8SNAT** — CERRADO (monitorizado, sin acción de código).
  `UDMA_CRC_Error_Count=24` (errores de enlace SATA, no de medio). Disco SANO
  (SMART PASSED, 0 reasignados). journald persistente. **Reabrir cuando:**
  reaparezca `errors=remount-ro` o el contador suba → reasentar el conector SATA.

### Decomposición del god-object (auditoría H1/H2)
- ✅ **`orchestrator.py` 3.120 → 2.007 LOC** (−36 %). 7 colaboradores mecánicos
  (TaskPersistence, GitReadTools, gate_f_parser, agentic_helpers, GateFExecutor,
  ApprovalManager, HybridClassifier) **+ el núcleo recursivo** extraídos. El loop
  agéntico suspendible (ADR-031/032/033/037) vive en
  `core/orchestrator_parts/agentic_executor.py` (sesión dedicada): movido
  bit-a-bit, lee colaboradores del host en tiempo de llamada para paridad exacta.
  897 tests + mypy 0. Ver `docs/plan_orchestrator_decomposition.md`.

### Roadmap previo
- ✅ **Hermes webhook** — HECHO. `HermesWebhookHandler` (HMAC + online/offline →
  EventBus), montado en el dashboard/API. 21 tests (`tests/test_hermes_webhook.py`).
- ✅ **ColdUpdate v2** — HECHO. `ColdUpdateManager` (propose/validate/approve/
  apply/rollback en worktree git aislado) + CLI `atlas update *`. ADR-025,
  6 tests (`tests/test_cold_update_manager.py`).
- ✅ **Endurecimiento del subprocess (Post-F, ADR-034)** — HECHO en lo factible
  con stdlib: no-new-privs, rlimits `FSIZE`/`NPROC`/`NOFILE`, sesión aislada.
  6 tests (`tests/test_process_hardening.py`).
- ✅ **seccomp-bpf (filtrado de syscalls)** — CERRADO como limitación aceptada
  (ADR-034 dec.6). Exige dep nueva (`pyseccomp`, choca con regla 6) + tooling de
  kernel no disponible en local. Hook ya dejado en `apply_in_child`. **Reabrir
  cuando:** se adopte `pyseccomp` (decisión explícita contra regla 6) o aparezca
  un entorno con el tooling de kernel disponible.
- ✅ **Flota / Atlas Box** (`docs/atlas_box_architecture.md`,
  `docs/fleet_security_plan.md`) — CERRADO como diferido: diseño aceptado,
  despliegue bloqueado por hardware. **Reabrir cuando:** llegue el hardware de
  despliegue.
- 🟢 **Cliente MCP + murallas defensivas** — PLAN MAESTRO en
  `docs/plan_mcp_y_murallas_defensivas.md`. Anclado en literatura (CaMeL
  arXiv:2503.18813, arXiv:2601.17548, CoSAI, NSA, CSA). Ciclo **cerrado**:
  ADR-035 (cliente MCP + registro dinámico add/remove en caliente), ADR-036
  (threat model/murallas), ADR-037 (frontera de contenido no confiable, P0),
  ADR-038 (gate de adopción "Atlas Sentinel", fail-closed) ya en `main`.
- 🟢 **ADR-039 — Agente de auto-mantenimiento** — **COMPLETO (slices 1-7 + lazo autónomo)**
  (`docs/adr_039_self_maintenance_agent.md`). Pipeline Scout→Analyst dual-LLM→
  Proposer→seam decisor→Executor. Tres fuentes de descubrimiento (registry
  autoritativo, deps PyPI, community con corroboración obligatoria) + dos proposers
  (DepProposer, CodegenProposer) sobre seams reusados (ColdUpdate, add_server).
  **Lazo autónomo cerrado (2026-06-04):** el scheduler notifica propuestas **y** las
  enruta al ``MaintenanceAdopter`` vía el seam del decisor (ADR-040). Bajo
  ``HumanDecider`` (default) → "requiere aprobación humana", paridad HITL; bajo
  autónomo/híbrido → adopta reversible. El punto de decisión es el decisor
  intercambiable, no un botón hardcodeado. El ``AtlasServiceRunner`` arranca el cron
  cuando ``ATLAS_MAINTENANCE_SCHEDULER=1`` (off por defecto); ``ATLAS_DECIDER``
  controla el nivel de autonomía. Auditoría Merkle en cada seam.
  **Slice 1 — Scout read-only (LANDED):** `MaintenanceScout` en
  `core/self_maintenance/scout.py`. Colector por inyección de dependencias que
  reusa las primitivas read-only existentes (`health_report`, `GitReadTools`,
  `ErrorRegistry`); deriva señales de deuda deterministas (cadena Merkle,
  emergency/governance, thermal, hermes, backlog offline/aprobaciones, fallos
  recientes, git sucio) → `ScoutReport` auditado en Merkle. No muta ni propone.
  Accessor `Orchestrator.maintenance_scout()`.
  **Desvío consciente del slice 1 del ADR:** el ADR descubre candidatos
  *externos* (registry MCP + arxiv, egress, `UNTRUSTED_READERS`, contenido no
  confiable); esta entrega es un Scout *interno* de salud/deuda — sin red ni
  ingesta untrusted, aún más pequeño. El Scout externo (con gate de corroboración
  + dual-LLM) entra en slices siguientes.
  **Slice 2 — Analyst dual-LLM + gate de corroboración (LANDED):**
  `MaintenanceAnalyst` en `core/self_maintenance/analyst.py`. Toma un
  `McpCandidate` tipado (lo que un Scout externo emitirá) y aplica separación
  datos/control (CaMeL, ADR-037 §D3): el processing-LLM digiere la prosa NO
  confiable (`wrap_untrusted`) → `TypedSummary` acotado; un gate determinista
  *fail-closed* admite solo si ≥1 fuente `authoritative` coincide en nombre+versión
  (los foros nunca corroboran, solo surgen señal); el control-LLM redacta riesgos
  viendo únicamente campos tipados, nunca la prosa. Salida: `McpProposal` tipada
  con cadena de evidencia, auditada en Merkle, o `None` si no corrobora.
  `format_proposal` renderiza el mensaje HITL (qué/por qué/riesgos/procedencia)
  **sin envío**. Sin auto-apply: el wire aprobación→`add_server` es slice 3.
  Inferencia mockeada en tests (hub falso enrutado por `task_id`, sin LLM real).
  **Slice 3 — wire propuesta → adopción (LANDED):** `MaintenanceAdopter` en
  `core/self_maintenance/adopter.py`. Cierra el lazo end-to-end: traduce una
  `McpProposal` corroborada → `McpServerConfig` + `Task` con intención anclada al
  nombre del server, y delega en `Orchestrator.adopt_mcp_server` (que ya consulta
  el decisor ADR-040 + `add_server` en caliente + `register_undo` reversible).
  **El adopter no decide** — el "botón HITL" es una implementación más del
  decisor (rumbo human-ON-the-loop): bajo `HumanDecider` el seam exige aprobación
  y nada se adopta; bajo autónomo/híbrido con intención anclada, adopta y deja el
  undo (`remove_server`). Reuso puro: ninguna máquina de aprobación nueva.
  Accessor `Orchestrator.maintenance_adopter()`. Resultado auditado en Merkle
  (`adopter_adopt`: adopted/not_adopted). E2E con orquestador real (Autonomous
  adopta + undo; Human → requiere aprobación, sin `add_server`).
- ✅ **ADR-040 — Decisor central + human-ON-the-loop** — COMPLETO (6 slices,
  `docs/adr_040_decider_human_on_the_loop.md`). Seam único
  `decide(action,intent,ctx)->Allow|Deny` (sin `Escalate` bloqueante) que
  des-dispersa los 4 call-sites de aprobación del orchestrator. s1 seam
  `Decider`+`HumanDecider`; s2 enrutado de los 4 call-sites con paridad bit-a-bit;
  s3 `action_hash` + telemetría no bloqueante D7; s4 `AutonomousDecider`
  (invariantes deterministas, sin LLM ni humano); s5 `HybridDecider` (high→humano,
  resto→autónomo) + flip `ATLAS_DECIDER`; s6 invariante de reversibilidad +
  `RevertRegistry` + `Orchestrator.revert(action_hash)`. Default sigue `human` →
  cero cambio de conducta hasta el flip.
  **Captura reversible — CERRADO:** `_consult_decider` devuelve
  `(verdict, action_hash)` y los 4 call-sites lo desempaquetan. Dos productores
  forward gobernados por el seam son los únicos que declaran `reversible=True`:
  `Orchestrator.adopt_mcp_server` (undo `MCP_SERVER` vía `remove_server`) y
  `Orchestrator.execute_reversible_code` (undo `SNAPSHOT` OMEGA vía
  `restore_snapshot`). Tras una ejecución con undo real registran
  `register_undo(action_hash, …)`; `revert(action_hash)` cierra el ciclo. El resto
  de call-sites sigue `reversible=False` → en `autonomous` se deniegan (fail-safe
  invariante 4 intacto). E2E verde con `ATLAS_DECIDER=autonomous`.
- ✅ **`AgenticExecutor`** — núcleo recursivo de ejecución extraído tras las 6
  slices mecánicas del orchestrator (`core/orchestrator_parts/agentic_executor.py`).
  El loop de tool-calls suspendible (ADR-031/032/033/037) —
  `drive`↔`resume`↔`_suspend`↔dispatch más `execute_local_safe`— se movió
  **bit-a-bit**: el executor guarda el `Orchestrator` host y lee sus colaboradores
  en tiempo de llamada (preserva swaps de `host._mcp`/`_agentic_auto_approve` en
  tests). Los helpers puros y predicados (`_agentic_tool_*`, `_wrap_untrusted`,
  `_is_agentic_auto_approved`, `sweep_expired_suspensions`, `_stringify_tool_result`)
  se quedan en el host. orchestrator.py 2.272→2.007 LOC. Paridad: 897 tests +
  mypy 0. Ver `docs/plan_orchestrator_decomposition.md`.

---

## Historial de Sesiones

Las sesiones de implementación detalladas (prompts, decisiones, blockers) se documentan en `docs/sessions/` o en los mensajes de commit. Este archivo es solo un checklist de estado.

> Regla: Cuando un Gate se cierra, se actualiza este archivo, se crea tag, y se escribe `docs/gate_X_seal.md` en el mismo commit.
