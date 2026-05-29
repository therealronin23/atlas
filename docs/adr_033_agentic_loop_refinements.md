# ADR-033 — Refinamientos del loop agéntico suspendible

- Status: **Accepted** (2026-05-30) — implementado sobre ADR-032
- Módulos: `src/atlas/core/orchestrator.py`, `src/atlas/core/contracts.py`
- Depende de: ADR-032 (loop suspendible + HITL inline), ADR-031 (loop agéntico)

## Contexto

ADR-032 hizo el loop agéntico **suspendible/reanudable**: ante una herramienta
mutante de host, el loop serializa su estado, pasa a `AWAITING_APPROVAL` y un
humano lo aprueba después. Funciona, pero ADR-032 dejó cuatro cosas
explícitamente **fuera de alcance (MVP)**:

1. Expiración automática de loops suspendidos abandonados.
2. Auto-aprobación por allowlist para mutaciones de bajo riesgo.
3. Aprobación parcial (aprobar unas mutaciones del lote y denegar otras).
4. Streaming de progreso del loop al humano.

Con el flujo base ya probado (8 tests en verde), estos cuatro refinamientos
quitan fricción y cierran agujeros operativos sin tocar las invariantes de
seguridad. Este ADR los recoge.

## Decisión

| # | Tema | Elección | Razón |
|---|------|----------|-------|
| 1 | **Loops abandonados** | `sweep_expired_suspensions(ttl)` cancela loops cuyo `agentic_state.created_at` supera el TTL. Opt-in vía `ATLAS_AGENTIC_SUSPENSION_TTL`; ausente/<=0 → no-op | No reintroducir un scheduler; el barrido se invoca desde el tick de `serve` o a mano. Seguro por defecto (desactivado) |
| 2 | **Auto-aprobación** | `set_agentic_auto_approve(tools)` / env `ATLAS_AGENTIC_AUTO_APPROVE`. Una mutación corre inline (con clearance) **solo** si está en la allowlist **y** `task.sensitivity != "high"`. Allowlist vacía por defecto | Confianza explícita y revocable. No vive en `governance.json` (regla 3): es sesión, no política persistida. Sensibilidad alta nunca se salta el humano |
| 3 | **Aprobación parcial** | `approve_pending(..., approve_only=[ids])`. Solo esas `tool_call` del lote se ejecutan; el resto recibe denegación sintética `{"denied": true, "reason": "human_partial"}` y el loop reanuda | El humano puede dejar pasar lo seguro de un turno y frenar lo dudoso, sin abortar todo. `None` → lote entero (compat ADR-032) |
| 4 | **Progreso en vivo** | Nuevo `EventType.AGENTIC_PROGRESS` emitido por iteración con `{task_id, iteration, tool, summary}` (summary truncado a 200 chars) | Dashboard/Telegram siguen el razonamiento sin esperar al resultado final. Reusa el EventBus existente, cero superficie nueva |

## Invariantes que NO cambian

- **Clearance**: toda mutación (auto-aprobada o no) pasa por
  `mark_confirmed("task:<id>")` antes de ejecutarse; el AtlasExecutor sigue
  siendo el único que autoriza.
- **Auditoría**: una mutación auto-aprobada emite `task.auto_approved` en la
  cadena Merkle (`auto: true`) — nunca hay ejecución silenciosa. El barrido por
  TTL emite `task.suspension_expired`.
- **Presupuesto**: `iterations` sigue persistiendo a través de suspensiones
  (ADR-032 dec.9); ni auto-aprobar ni aprobación parcial regalan iteraciones.
- **Seguro por defecto**: allowlist vacía y TTL desactivado → comportamiento
  idéntico a ADR-032.

## Flujo (auto-aprobación + progreso)

```
loop corriendo
  └─ modelo pide [read_x, editor_write]   (editor_write en allowlist, task low)
       ├─ read_x        → ejecuta YA → AGENTIC_PROGRESS(iter, read_x)
       └─ editor_write  → auto-approved:
            ├─ merkle: task.auto_approved (auto=true)
            ├─ mark_confirmed("task:id")
            ├─ ejecuta mutación (auditada) → AGENTIC_PROGRESS(iter, editor_write)
            └─ resultado al messages, el loop NO se suspende
  └─ reinyecta y sigue hasta respuesta final
```

## Compatibilidad

- **ADR-032 puro** (allowlist vacía, sin `approve_only`, TTL off): los 8 tests
  de `test_orchestrator_mutating_loop.py` siguen pasando sin cambios.
- **`approve_pending` legacy**: la firma gana kwargs opcionales
  (`approve_only`); las llamadas existentes (`approved`, `abort`) no cambian.
- **Consumidores del EventBus**: `AGENTIC_PROGRESS` es un tipo nuevo; quien no
  se suscribe no se entera.

## Fuera de alcance

- Persistencia de la allowlist de auto-aprobación entre reinicios (es sesión).
- Aprobación parcial con re-ordenación (se respeta el orden del lote).
- Scheduler propio para el barrido TTL (se invoca externamente).

## Tests

`tests/test_orchestrator_agentic_refinements.py`:
- `test_auto_approved_mutation_runs_inline`
- `test_auto_approve_blocked_for_high_sensitivity`
- `test_empty_allowlist_still_suspends` (compat)
- `test_env_configures_auto_approve_allowlist`
- `test_partial_approval_executes_only_selected`
- `test_sweep_expired_suspension_cancels_loop`
- `test_sweep_noop_when_ttl_disabled`
- `test_agentic_progress_event_emitted`
- `test_auto_approved_mutation_audited_in_merkle`
