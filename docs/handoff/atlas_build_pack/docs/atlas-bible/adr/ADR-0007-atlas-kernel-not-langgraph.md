# ADR-0007-atlas-kernel-not-langgraph

## Title

Atlas Kernel is not LangGraph

## Status

Accepted

## Context

Atlas corre el riesgo de derivar hacia productos conocidos: chat, IDE, dashboard, workflow builder o wrapper de herramientas externas.

## Decision

LangGraph puede ejecutar grafos, pero Atlas mantiene kernel/event canon propio.

## Consequences

- La implementación debe respetar esta decisión.
- Cualquier desviación requiere nuevo ADR.
- El agente constructor debe revisar este ADR antes de modificar arquitectura relacionada.

## Validation

La decisión se valida durante Gates y revisión de fase.
