# ADR-032 — Tools mutantes dentro del loop agéntico (HITL inline)

- Status: **Accepted** (2026-05-29) — implementado, 8 tests + suite completa (708) en verde
- Módulos: `src/atlas/core/orchestrator.py`, `src/atlas/governance/permission_profile.py`
- Depende de: ADR-031 (loop agéntico), Gate F (browser/editor + AWAITING_APPROVAL)

## Contexto

El loop agéntico (ADR-031) es **síncrono y totalmente autónomo**: cuando el
modelo pide una herramienta, `_dispatch_agentic_tool` la ejecuta en el acto,
reinyecta el resultado y vuelve a llamar, hasta `max_iters=5`. Por eso v1 solo
expone herramientas **de lectura** + auto-edición de block memory: nada que
mute el host puede correr sin que un humano lo vea primero.

Las herramientas mutantes de host (browser `navigate/click/fill`, editor
`write/run/apply_diff/open`) viven en un flujo **separado y asíncrono**: el
Orchestrator pone la tarea en `AWAITING_APPROVAL`, la persiste a disco, y un
humano la aprueba después vía CLI/API/Telegram (`approve_pending`), que
concede el clearance (`mark_confirmed("task:<id>")`) y ejecuta.

Resultado hoy: el modelo **no puede actuar dentro de un razonamiento**. Si en
mitad de un loop decide "edita este archivo", no hay forma de hacerlo sin
abortar el loop y abrir una tarea aparte que pierde todo el contexto del
razonamiento.

El nudo es la **impedancia temporal**: el loop es síncrono (segundos), la
aprobación HITL es asíncrona (minutos/horas). No se puede bloquear dentro del
loop esperando a un humano. La única salida correcta es **suspender** el loop,
persistir su estado completo, y **reanudarlo** cuando llegue la aprobación.

## Decisión

Convertir el loop en **suspendible/reanudable**. Cuando el modelo invoca una
herramienta mutante, el loop serializa su estado a la tarea pendiente, pasa a
`AWAITING_APPROVAL` y notifica; al aprobar, el loop se reanuda exactamente
donde quedó, ejecuta la mutación y sigue.

| # | Decisión | Elección | Razón |
|---|----------|----------|-------|
| 1 | Quién pausa | El propio loop, al detectar en `tool_calls` una tool clasificada como mutante | El modelo no decide si pausa; lo decide la política (PermissionProfile), igual que hoy |
| 2 | Clasificación read/mutante | Reusar `PermissionProfile` (ya sabe qué es observacional vs mutante en Gate F) | Una sola fuente de verdad de riesgo; no duplicar listas |
| 3 | Estado a persistir | `messages` (conversación OpenAI completa), `tools_used`, `iterations`, y el/los `tool_call` pendientes de aprobar | El `messages` array **es** la memoria del loop; sin él no se puede reanudar |
| 4 | Dónde se persiste | En el registro de pending approval existente (`<task_id>.json`), bajo una clave nueva `agentic_state` | Reusa flock, replace atómico y resume ya probados (`approve_pending`) |
| 5 | Granularidad de aprobación | Si un turno trae varias tool_calls: ejecutar las **de lectura en el acto**, y agrupar **todas las mutantes del turno** en una sola aprobación | Menos fricción HITL; el humano ve el lote completo de mutaciones de ese paso |
| 6 | Semántica de DENY | Inyectar un resultado sintético `{"denied": true, "reason": "human"}` como `tool` message y **reanudar** el loop | Presión estilo MemGPT: el modelo re-planifica en vez de crashear (coherente con decisión 9 de ADR-031) |
| 7 | Cancelar del todo | Verbo explícito (deny con flag `abort=true`, o segundo deny) → `CANCELLED` | Da salida limpia si el humano no quiere que el modelo reintente |
| 8 | Clearance | Al aprobar, `mark_confirmed("task:<id>")` **antes** de ejecutar la mutante, igual que `approve_pending` hoy | El AtlasExecutor sigue siendo el único que autoriza; el loop no se salta capabilities |
| 9 | Presupuesto de iteraciones | `iterations` persiste y cuenta **a través** de suspensiones; el tope total sigue siendo `max_iters` | Una suspensión no regala iteraciones extra ni reinicia el contador |
| 10 | Auditoría | `task.suspended` (nuevo) + `task.approval` (existe) + `tool.invoked` (existe) en Merkle | Regla 1: el ciclo pausa→aprueba→ejecuta queda en la cadena |
| 11 | Notificación | Reusar el canal de approvals actual (CLI `atlas pending`/`approve`, API, Telegram) | Cero superficie nueva; el humano ya sabe aprobar tareas |
| 12 | Concurrencia | Reusar el flock por `task_id` de `approve_pending` | Evita doble-reanudación |
| 13 | Deps | Ninguna nueva | Regla 6 |

## Flujo

```
loop corriendo
  └─ modelo pide tools [read_x, editor.write]
       ├─ read_x            → ejecuta YA, resultado al messages
       └─ editor.write      → MUTANTE:
            1. messages += pending tool_call
            2. task.agentic_state = {messages, iterations, tools_used, pending:[editor.write]}
            3. task → AWAITING_APPROVAL, persist <id>.json, notifica
            4. [el loop RETORNA — no bloquea]
  ...minutos después...
approve_pending(id, approved=True)
  ├─ mark_confirmed("task:id")
  ├─ rehidrata agentic_state
  ├─ ejecuta editor.write (auditada) → resultado al messages
  └─ REANUDA el loop (infer con messages) hasta respuesta final o nueva pausa
```

## Compatibilidad

- **Tools de lectura y block memory**: sin cambios. Siguen corriendo inline; el
  loop solo se suspende ante una tool **mutante**.
- **Loop sin mutantes**: idéntico a ADR-031 (una o varias iteraciones, sin
  persistencia de estado). La rama de suspensión es *dead code* si el modelo no
  pide mutaciones.
- **Flujo AWAITING_APPROVAL actual de Gate F** (tareas mutantes directas, no
  dentro de un loop): intacto. El nuevo `agentic_state` es una clave **opcional**
  del mismo registro; las aprobaciones sin ella se comportan como hoy.
- **Backward-compat de `approve_pending`**: si `agentic_state` está ausente →
  ruta clásica (ejecuta la tarea mutante única). Si está presente → ruta de
  reanudación de loop.

## Consecuencias

- El modelo puede **planear y actuar** en un único razonamiento (leer → decidir
  → mutar → verificar), con un humano en el bucle solo en el punto de mutación.
- Atlas pasa de "te dice qué hacer" a "lo hace, con tu visto bueno inline".
- `task.result` gana trazas de cuántas pausas hubo y qué se aprobó/denegó.
- Coste: el registro de pending crece (lleva el `messages` array). Aceptable;
  se borra al cerrar la tarea.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Estado de loop abandonado (humano nunca aprueba) | `created_at` en `agentic_state`; barrido/expiración opt-in (fuera de MVP, anotado) |
| `messages` con PII persistido a disco | Ya se redacta antes de reinyectar (ADR-031 dec. 6); persistimos la versión redactada |
| Reanudación tras reinicio del servicio | El estado vive en disco (`<id>.json`); `approve_pending` ya lo rehidrata sin proceso vivo |
| El modelo abusa pidiendo mutaciones en bucle | El tope `max_iters` persiste a través de suspensiones (dec. 9) |
| Doble aprobación / carrera | flock por task_id (dec. 12) |

## Fuera de alcance (MVP)

- Expiración automática de loops suspendidos (solo se anota `created_at`).
- Políticas de auto-aprobación por tipo de mutación (allowlist "confiable").
- Aprobación parcial (aprobar unas mutaciones del lote y denegar otras): MVP
  aprueba/deniega el lote del turno entero.
- Streaming de progreso del loop al humano mientras está suspendido.

## Plan de implementación (incremental, todo con tests)

1. **Clasificador de tool**: helper en PermissionProfile/Orchestrator que dado
   un nombre de tool del loop diga `read | mutate`. Test unitario.
2. **Serialización de `agentic_state`**: extender el registro de pending +
   load/save. Test de round-trip (incluye `messages`).
3. **Suspensión**: en el loop, al ver una mutante → persistir + `AWAITING_APPROVAL`
   + retornar. Test: el loop retorna sin ejecutar la mutante y deja la tarea
   pendiente con estado.
4. **Reanudación**: rama en `approve_pending` que detecta `agentic_state`,
   ejecuta la mutante con clearance, reinyecta y continúa el loop. Test E2E:
   suspende→aprueba→termina; suspende→deniega→re-planifica.
5. **Auditoría**: `task.suspended` en Merkle + asserts de cadena.
6. **Tope de iteraciones a través de suspensiones**: test que un loop que se
   suspende 2 veces no excede `max_iters` total.

## Tests (objetivo)

`tests/test_orchestrator_mutating_loop.py`:
- `test_read_tool_runs_inline_no_suspension`
- `test_mutating_tool_suspends_loop_to_awaiting_approval`
- `test_approve_resumes_loop_and_executes_mutation`
- `test_deny_injects_pressure_and_model_replans`
- `test_deny_abort_cancels_task`
- `test_iteration_budget_persists_across_suspension`
- `test_agentic_state_roundtrip_survives_restart` (sin proceso vivo)
- `test_merkle_chain_records_suspend_approve_execute`
