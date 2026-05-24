# ATLAS — Hoja de Ruta

> Estado actual: **Gate E COMPLETE** (tag `v0.4-gate-e`, suite 449/449 green, mypy limpio).
> Siguiente: **Gate F**.

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

## Gate F — PENDING

Computer-use + Editor integration + Frontend.

### F1 — Computer-use con Playwright
- Browser automation con Playwright (navegar, rellenar formularios, screenshots).
- Loop visual: screenshot → VLM (Gemini free / LLaVA local) → describe → Atlas decide acción.
- Todo pasa por SSRF Bridge.
- Tests con páginas estáticas locales.

### F2 — Integración Cursor/VS Code
- `src/atlas/tools/editor.py`: open_project, apply_diff, run_task.
- Flujo: `atlas task "crea componente React"` → Atlas planifica → genera código → aplica via editor → abre Cursor.

### F3 — eBPF / seccomp (capa de seguridad final)
- Compilar restricciones de syscalls directamente en el kernel.
- Alternativa: seccomp profiles con Docker si eBPF no es viable en el hardware actual.

### F4 — ColdUpdateManager (self-improvement protocol)
- Snapshot completo → generar N+1 → ejecutar tests → si mejoran métricas, proponer swap vía Telegram.
- HITL obligatorio (confirmación humana).

---

## Historial de Sesiones

Las sesiones de implementación detalladas (prompts, decisiones, blockers) se documentan en `docs/sessions/` o en los mensajes de commit. Este archivo es solo un checklist de estado.

> Regla: Cuando un Gate se cierra, se actualiza este archivo, se crea tag, y se escribe `docs/gate_X_seal.md` en el mismo commit.