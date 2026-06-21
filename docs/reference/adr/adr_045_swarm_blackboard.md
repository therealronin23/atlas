# ADR-045 — Enjambre sobre blackboard (Capa 3)

Fecha: 2026-06-13 · Estado: aceptado (núcleo) · Contexto:
`docs/direction_2026-06-12_construir_hacia_arriba.md` §3,
`docs/roadmap_mythos_2026-06-13.md`, ADR-041, ADR-042.

## Decisión

`core/swarm.py`: N workers coordinados por **artefactos verificables**, no por
contexto compartido. Cada worker produce un `Artifact`; nada aterriza en el
`Blackboard` sin pasar por el `UniversalVerifier` (capa 1). Ley del blackboard:
sin `Evidence` PASS, no se acepta — el rechazo se registra igual (rastro de
auditoría, no descarte silencioso).

El `SwarmCoordinator` asigna **envelopes** (dominio, presupuesto, expiración) y
decide políticas, no acciones: los workers actúan, el coordinador acota y
audita por muestreo. Reusa la `CostLedger` de la capa 2 para coste por
resultado verificado.

## Decisiones y porqués

| # | Decisión | Elegida | Porqué |
|---|---|---|---|
| 1 | Coordinación | por artefactos en el blackboard, no por estado compartido | un decisor que aprueba cada acción es el cuello de botella (HITL con otro nombre); las capas se mantienen desacopladas |
| 2 | Ley del blackboard | aceptar solo `Evidence` PASS; registrar el rechazo | misma ley de capa 1/4: nada sube sin verificación; el rechazo es evidencia |
| 3 | Envelope | política del decider (dominio/presupuesto/expiración), inmutable | el decider decide políticas; el gasto se contabiliza fuera (coordinador) |
| 4 | Presupuesto | unidades ordinales de tier, vía `CostLedger` (capa 2) | las capas componen; el coste del intento = productor + verificación |
| 5 | Aislamiento real | responsabilidad del backend del worker, tras la interfaz `Worker` | el coordinador no comparte estado; worktree/proceso es del worker |
| 6 | Auditoría | por muestreo determinista (`audit_sample`) + Merkle | revisar todo sería el cuello de botella; el muestreo + cadena basta |
| 7 | **Alcance de esta iteración** | **librería de coordinación; sin lanzar worktrees/procesos reales** | el "3 workers una semana" es operativo, no de una sesión; en tests, workers fake |

## Diferido explícitamente

- **Backend real de worker** (worktree git por worker + ejecución aislada) →
  pieza propia; conecta con el `MerkleWriterLock` (cada worker escribe en su
  propio HOME aislado, no en la cadena viva).
- **Primer enjambre operativo**: 3 workers de mantenimiento del repo, una
  semana sin intervención — el listón falsable de la dirección §3.
- **Cableado de capa 4**: los workers cargan lecciones (`avoid_pattern`) antes
  de producir; cada rechazo del blackboard se promociona a Lesson.

## Composición de capas (lo que esta capa demuestra)

`SwarmCoordinator` no inventa verificación ni contabilidad: consume
`UniversalVerifier` (capa 1) y `CostLedger` (capa 2). El blackboard habla
`Evidence`. La capa 3 es coordinación pura sobre las dos de abajo — exactamente
lo que el roadmap predijo ("las capas 2 y 3 consumirán este seam").
