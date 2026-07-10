# ADR-0001-atlas-cognitive-operating-environment

## Title

Atlas is a cognitive operating environment

## Status

Accepted

## Context

Atlas corre el riesgo de derivar hacia productos conocidos: chat, IDE, dashboard, workflow builder o wrapper de herramientas externas.

## Decision

Atlas se define como entorno operativo cognitivo, no como chat, IDE o dashboard.

## Consequences

- La implementación debe respetar esta decisión.
- Cualquier desviación requiere nuevo ADR.
- El agente constructor debe revisar este ADR antes de modificar arquitectura relacionada.

## Validation

La decisión se valida durante Gates y revisión de fase.
