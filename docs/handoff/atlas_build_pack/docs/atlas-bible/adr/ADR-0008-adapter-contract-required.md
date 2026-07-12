# ADR-0008-adapter-contract-required

## Title

Adapter Contract required

## Status

Accepted

## Context

Atlas corre el riesgo de derivar hacia productos conocidos: chat, IDE, dashboard, workflow builder o wrapper de herramientas externas.

## Decision

Toda integración externa debe declarar permisos, riesgo, schemas, auditoría y failure modes.

## Consequences

- La implementación debe respetar esta decisión.
- Cualquier desviación requiere nuevo ADR.
- El agente constructor debe revisar este ADR antes de modificar arquitectura relacionada.

## Validation

La decisión se valida durante Gates y revisión de fase.
