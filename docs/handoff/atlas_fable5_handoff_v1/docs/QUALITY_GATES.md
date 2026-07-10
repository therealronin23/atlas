# Atlas OS — Quality Gates

## Gate A — Architecture Coherence

Pasa si:

- Hay Constitución.
- Hay Non-goals.
- Hay Architecture Map.
- Hay ADRs.
- No contradice visión.

## Gate B — Event First

Pasa si:

- Hay event schema.
- Hay fixtures.
- La UI consume eventos.
- Backend bridge emite eventos.

## Gate C — Cognitive Surface

Pasa si:

- Living Graph renderiza WorldState.
- Pipeline reacciona a eventos.
- Timeline registra eventos.
- Universal Bar crea intents.

## Gate D — Control Plane

Pasa si:

- Control Center existe.
- Integration Fabric existe.
- Connectors tienen permisos y estado.
- Personalización existe.
- Security Center existe aunque sea básico.

## Gate E — Governance

Pasa si:

- Acciones peligrosas requieren Gate.
- Permissions Matrix existe.
- Hay audit events.
- Hay risk labels.

## Gate F — Continuation

Pasa si:

- CONTINUATION_STATE.md actualizado.
- NEXT_AI_INSTRUCTIONS.md actualizado.
- Tests documentados.
- Próximos tickets claros.

## Gate G — No Prototype Trap

Falla si:

- Solo hay UI mock sin datos.
- No hay schemas.
- No hay eventos.
- No hay docs de continuidad.
- No se puede ejecutar nada.
