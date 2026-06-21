# ADR-046 — Backend de ejecución de workers (Capa 3)

Fecha: 2026-06-13 · Estado: aceptado (núcleo) · Contexto: ADR-045,
`docs/direction_2026-06-12_construir_hacia_arriba.md` §3.

## Decisión

`core/swarm_backend.py`: substrato **general** de ejecución. `WorktreeManager`
gestiona worktrees git desechables (reusa el patrón de ColdUpdate);
`WorktreeWorker` (conforma el Protocol `Worker` de ADR-045) corre en un
worktree aislado, produce un diff, lo valida ahí y emite `Artifact(PATCH)`.

El worker de mantenimiento es la **primera instancia concreta**, no el sistema:
el mismo backend sirve a workers de seguridad (ADR-043), research, codegen de
feature, etc. Cada dominio es un `produce_diff` + un verificador distintos.

## Modelo de aislamiento (decidido con el usuario)

Síntesis de "proceso separado" (opción 3) + "coordinador único escritor"
(opción 1):

- El enjambre corre como **proceso separado** sobre **un** `ATLAS_HOME` aislado.
- El **coordinador es el único escritor Merkle** (capa 3). Los workers son
  **productores puros**: worktree desechable, sin HOME ni Merkle propios.
- **Auditabilidad por worker** vía la dimensión `worker_id` sobre la cadena
  única — no N cadenas (una cadena ordenada es mejor para time-travel que N
  que habría que fusionar).
- **Rollback** por tres vías sin HOME por worker: worktrees desechables
  (descartar = rollback instantáneo), nada aterriza en main sin ColdUpdate
  (fallo confinado al worktree), y la cadena Merkle + TimeTravel dan replay.

## Reconciliación a lo vivo (decidido con el usuario)

La 1 es el conducto, la 2 es política del decider sobre el subconjunto seguro:

- Cada entrada ACEPTADA del blackboard → propuesta ColdUpdate → seam del decider.
- El decider auto-aplica solo lo reversible + bajo riesgo + suite verde +
  dentro del dominio del envelope (con validación-post-apply y rollback de
  ColdUpdate, undo en RevertRegistry). El resto queda como propuesta.
- **Arranca en propuesta-solo.** El auto-apply se gana cuando la primera
  semana aburrida demuestre que el verificador no tiene punto ciego
  (`audit_sample`). Autonomía por evidencia, no por defecto.

## Decisiones y porqués

| # | Decisión | Elegida | Porqué |
|---|---|---|---|
| 1 | Aislamiento de worker | git worktree detached desechable | reusa ColdUpdate; no toca rama viva ni Merkle |
| 2 | Escritor | solo el coordinador | elimina el problema N-escritores de raíz |
| 3 | Auditoría por worker | dimensión `worker_id`, no N cadenas | una cadena ordenada > N para time-travel |
| 4 | teardown | guard que nunca borra el root, prune tras remove | un worktree mal calculado no puede tocar el repo |
| 5 | Generalidad | `Worker` Protocol + callables inyectados | un backend para todos los dominios, no uno por dominio |
| 6 | Alcance | librería; sin lanzar el enjambre real | el "3 workers una semana" es operativo, no de una sesión |

## Diferido (ver `docs/backlog.md`)

- Cableado real `produce_diff` (cascada/transform) y `validate` (ValidationRunner
  en el worktree).
- Reconciliación entrada-aceptada → propuesta ColdUpdate → decider.
- `audit_sample` que **re-ejecuta** la suite sobre la muestra (hoy solo
  selecciona).
- Primer enjambre operativo (3 workers, una semana).
- **Bug encontrado en el audit**: ColdUpdate no hace teardown del worktree en
  estado terminal → 365 worktrees huérfanos acumulados por el loop autónomo.
