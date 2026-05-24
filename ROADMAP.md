# ATLAS — Hoja de Ruta

> Estado actual: **Gate F IN PROGRESS** (F1/F2/F3 MVP + Orchestrator routing; suite local 509/509 green, mypy limpio).
> Siguiente: **real host smoke + ADR-013b/seal de Gate F**.

---

## Gates Cerrados

| Gate | Estado | Tag | Descripción |
|------|--------|-----|-------------|
| A | ✅ SEALED | — | Visión, entidades y principios fijados. |
| B | ✅ COMPLETE | — | Core local funcional (102 tests baseline). |
| C | ✅ COMPLETE | `v0.2-gate-c` | Hermes-VPS en Hetzner CPX22 + Tailscale + Telegram bot + REST HMAC. 147 tests. |
| D | ✅ COMPLETE | `v0.3-gate-d` | InferenceHub real (LiteLLM), KuzuDB vector+graph, MemoryDistiller, capability tokens, Time-Travel, Ghost Replay, PII Surrogate, SLM Classifier, pipeline integrado opt-in. 368 tests. |
| E | ✅ COMPLETE | `v0.4-gate-e` | ADR-002 sealed (bare metal + venv), Dashboard web (FastAPI+Jinja2, localhost:7331), Voz (Whisper STT + Piper TTS). 449 tests. |

Cada Gate tiene su documento de cierre en `docs/gate_*_seal.md`.

---

## Gate F — IN PROGRESS

Computer-use + Editor integration + Frontend.

Plan operativo: [`docs/gate_f_plan.md`](docs/gate_f_plan.md).
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

### F3 — eBPF / seccomp (capa de seguridad final)
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

### F4 — eBPF / seccomp (capa de seguridad final)
- Compilar restricciones de syscalls directamente en el kernel.
- Alternativa: seccomp profiles con Docker si eBPF no es viable en el hardware actual.

### F5 — ColdUpdateManager (self-improvement protocol)
- Snapshot completo → generar N+1 → ejecutar tests → si mejoran métricas, proponer swap vía Telegram.
- HITL obligatorio (confirmación humana).

---

## Historial de Sesiones

Las sesiones de implementación detalladas (prompts, decisiones, blockers) se documentan en `docs/sessions/` o en los mensajes de commit. Este archivo es solo un checklist de estado.

> Regla: Cuando un Gate se cierra, se actualiza este archivo, se crea tag, y se escribe `docs/gate_X_seal.md` en el mismo commit.
