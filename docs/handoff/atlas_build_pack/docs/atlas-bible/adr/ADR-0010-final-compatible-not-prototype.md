# ADR-0010-final-compatible-not-prototype

## Title

Build final-compatible version

## Status

Accepted

## Context

Atlas corre el riesgo de derivar hacia productos conocidos: chat, IDE, dashboard, workflow builder o wrapper de herramientas externas.

## Decision

Se construyen slices pequeños, pero compatibles con la arquitectura final.

## Consequences

- La implementación debe respetar esta decisión.
- Cualquier desviación requiere nuevo ADR.
- El agente constructor debe revisar este ADR antes de modificar arquitectura relacionada.

## Validation

La decisión se valida durante Gates y revisión de fase.
