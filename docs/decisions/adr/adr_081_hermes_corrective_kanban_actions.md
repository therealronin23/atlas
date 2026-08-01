# ADR-081 — Escrituras correctivas de Hermes gobernadas por el Decider

- **Estado**: aceptado (decisión del operador 2026-08-01: "Hermes debe
  autocorregirse con tus correcciones y ayuda", con la escritura explícitamente
  detrás del decider — ver dossier de la sesión)
- **Fecha**: 2026-08-01
- **Contexto previo**: ADR-070 (retiro del canal REST legado de Hermes) y P10
  (*"Hermes propone, Atlas decide"*). El 2026-08-01 se cableó `diagnostics`/
  `repair` en `KanbanBridge` (sólo lectura y reparación de índices fail-closed).
  Ese cableado descubrió 5 hallazgos vivos en el tablero real que ninguna
  acción permitida puede corregir: una tarea `stranded_in_ready` de 564 h y dos
  `repeated_failures`.

## Decisión

Se añaden `unblock`, `edit` y `reassign` como acciones **propuestas**, nunca
ejecutadas sin paso por el `Decider` (`src/atlas/core/decider/decider.py`,
ADR-040). Cada propuesta se construye como
`DecisionAction(kind="hermes.kanban.correction", sensitivity="high",
mutating=True, descriptor=<verbo>)`.

`sensitivity="high"` no es una elección de implementación: la guardia
constitucional `enforce_constitutional_verdict` (decider.py:64) convierte
CUALQUIER `Allow` sobre sensibilidad alta en `RequiresHuman`, sin que ninguna
implementación de `Decider` pueda anularlo (regla #4). Es la misma guardia que
protege el resto de mutaciones del sistema — no se inventa un gate nuevo, se
reutiliza el único que ya existe.

**Invariante**: `KanbanBridge.propose_correction()` PROPONE. Nunca invoca
`self.run(verbo, ...)` salvo que el veredicto sea `Allow` — que con
`sensitivity="high"` sólo puede llegar si una implementación de Decider futura
declara explícitamente esa clase de acción autónoma seguramente retirable de
`RequiresHuman` (dirección declarada por el propio módulo: *"RequiresHuman
puede retirarse de clases de acción que demuestren autonomía segura"*, nunca
de sensibilidad alta salvo esa retirada explícita).

Toda propuesta —ejecutada, pendiente o denegada— escribe un receipt Merkle
(`hermes.correction.proposed` / `.pending` / `.denied` / `.applied`) en la
misma cadena que el resto de Atlas, con el mismo disciplinado de
`self._log()` que ya usa `KanbanBridge.run()`.

## Alcance de las 3 acciones

- **`unblock`**: retira el bloqueo de una tarea `stuck_in_blocked` — el caso
  de las 2 tareas de servidor con 198 h de antigüedad. Reversible: `hermes
  kanban block` la vuelve a bloquear.
- **`edit`**: corrige `title`/`body`/`assignee`. Reversible: el CLI de Hermes
  versiona el histórico de la tarea (`show --json` expone `events`).
- **`reassign`**: mueve el `assignee` de una tarea `stranded_in_ready` o con
  `repeated_failures`. Reversible: mismo mecanismo que `edit`.

Ninguna de las tres borra ni archiva una tarea. `archive`/`gc` siguen fuera de
`ALLOWED_KANBAN_ACTIONS` — irreversibles o destructivas, no entran por esta ADR.

## Evidencia

1. `src/atlas/core/decider/decider.py:64` — `enforce_constitutional_verdict`,
   la guardia que hace inevitable `RequiresHuman` para `sensitivity="high"`.
2. `src/atlas/core/orchestrator_parts/agentic_executor.py:358-365` — patrón ya
   en producción: `RequiresHuman` no ejecuta, encola la mutación pendiente.
3. Tablero real (2026-08-01, `hermes kanban diagnostics --json`): 1 `critical`
   (`stranded_in_ready`, 564 h), 2 `error` (`repeated_failures`), 2 `warning`
   (`stuck_in_blocked`, 198 h) — el motivador concreto de esta ADR.
4. `tests/test_hermes_corrective_actions.py` — TDD, RED verificado antes del
   código de producción: ningún veredicto salvo `Allow` invoca `self.run()`.

## Consecuencias

- `ALLOWED_KANBAN_ACTIONS` gana `unblock`, `edit`, `reassign` — pero SÓLO
  accesibles vía `propose_correction()`, nunca vía `run()` directo sin
  decisor. Un caller que invoque `run("unblock", ...)` a pelo sigue permitido
  por la allowlist pero salta el gate: se documenta como uso indebido, no se
  bloquea a nivel de `run()` para no duplicar la responsabilidad del decisor
  en dos sitios (ADR-040: el decisor es el ÚNICO seam).
- Con `ATLAS_DECIDER=human` (default) o `hybrid`, las 3 acciones SIEMPRE
  quedan `RequiresHuman`: el operador aprueba cada corrección explícitamente.
  No hay autocorrección silenciosa mientras el decisor sea humano.
- Un tick de mantenimiento puede PROPONER correcciones sobre los patrones ya
  detectados por `diagnostics` (p.ej. `stuck_in_blocked` → propuesta de
  `unblock`), pero el tick nunca ejecuta: sólo genera la propuesta y la
  persiste para revisión.

## Reversión

Revertir el commit que añade `propose_correction()` y las 3 acciones a
`ALLOWED_KANBAN_ACTIONS` restaura el estado previo (Hermes sigue
diagnosticándose, Atlas sigue sin poder corregir). No hay migración de datos:
los receipts Merkle son puramente aditivos.
