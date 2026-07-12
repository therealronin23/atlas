# ADR-0005-tauri-react-renderer-v1

## Title

Tauri + React renderer v1

## Status

Accepted

## Context

Atlas corre el riesgo de derivar hacia productos conocidos: chat, IDE, dashboard, workflow builder o wrapper de herramientas externas.

## Decision

El primer shell usa Tauri + React + TypeScript por velocidad y ecosistema visual.

## Consequences

- La implementación debe respetar esta decisión.
- Cualquier desviación requiere nuevo ADR.
- El agente constructor debe revisar este ADR antes de modificar arquitectura relacionada.

## Validation

La decisión se valida durante Gates y revisión de fase.
