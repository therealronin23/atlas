# ATLAS — Hoja de Ruta

> Estado actual: **v0.12.0** — Gates A–I sellados + arquitectura twin Atlas↔Hermes
> viva (ADR-026..029) + block memory estilo Letta (ADR-030) + loop agéntico de
> tool-calls (ADR-031). 695 tests verdes. Última sincronización: 2026-05-29.
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

### Post-F — eBPF / seccomp (future hardening)
- Compilar restricciones de syscalls directamente en el kernel.
- Alternativa: seccomp profiles con Docker si eBPF no es viable en el hardware actual.

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

Detalle del twin en `docs/adr_026..029`; block memory en `docs/adr_030_block_memory.md`.

- **Twin operativo**: Hermes (Nous Research, VPS Hetzner) delega a Atlas vía
  `/api/exec/intent`; Atlas devuelve resultados auditados. Bot Telegram
  `@GodAtlas_bot` como front conversacional.
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
- ✅ **E2E twin (lado Atlas)** — SELLADO. `scripts/twin_e2e_smoke.py` (in-process,
  ATLAS_HOME aislado) y `tests/test_exec_api.py::test_intent_grounds_git_log_not_hallucination`
  prueban el circuito Hermes→Atlas `/api/exec/intent` con grounding real
  (git.log devuelve commits reales, sin alucinación) + auditoría Merkle.
  Pendiente solo el tramo Telegram→Hermes en vivo (`--live <url>` cuando los
  servicios estén arriba); el lado Atlas ya no puede regresionar en silencio.
- **Tools mutantes dentro del loop** — v1 solo expone lectura + block memory.
  Browser/editor siguen por `AWAITING_APPROVAL`; meterlos en el loop requiere
  HITL inline (futuro).

### Upstream / externos
- **`mcp_serve` roto** (Hermes upstream, `hermes_cli/mcp_config.py:748`,
  `ModuleNotFoundError`). Issue redactado, pendiente de publicar.

### Infra / operación
- **SSD SanDisk SD8SNAT** — `UDMA_CRC_Error_Count=24` (errores de enlace SATA,
  no de medio). Disco SANO (PASSED, 0 reasignados). Vigilar; si reaparece el
  `errors=remount-ro`, reasentar conector. journald ya persistente.

### Roadmap previo (todavía válido)
- Flota / Atlas Box (`docs/atlas_box_architecture.md`, `docs/fleet_security_plan.md`).
- Hermes webhook; ColdUpdate v2.
- eBPF / seccomp hardening (Post-F).

---

## Historial de Sesiones

Las sesiones de implementación detalladas (prompts, decisiones, blockers) se documentan en `docs/sessions/` o en los mensajes de commit. Este archivo es solo un checklist de estado.

> Regla: Cuando un Gate se cierra, se actualiza este archivo, se crea tag, y se escribe `docs/gate_X_seal.md` en el mismo commit.
