# ATLAS — Hoja de Ruta

> Estado actual: **Gate I COMPLETE** (2026-05-25) — `atlas serve` 24/7, health JSON, systemd.
> Gates H + debt closure: `v0.7-gate-h`, `v0.7.1-debt-closure`. Siguiente: ADR-025, ADR-024, fleet.

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

## Historial de Sesiones

Las sesiones de implementación detalladas (prompts, decisiones, blockers) se documentan en `docs/sessions/` o en los mensajes de commit. Este archivo es solo un checklist de estado.

> Regla: Cuando un Gate se cierra, se actualiza este archivo, se crea tag, y se escribe `docs/gate_X_seal.md` en el mismo commit.
