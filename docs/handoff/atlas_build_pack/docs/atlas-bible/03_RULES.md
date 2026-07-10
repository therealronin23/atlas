# 03 — Reglas de Construcción

## Regla 1 — Event-first

La UI nunca debe depender directamente de funciones internas del backend. La UI reacciona a eventos.

## Regla 2 — Simulator-first

Antes de conectar backend real, cada vista debe funcionar con eventos simulados.

## Regla 3 — Final-compatible desde el día 1

No construir prototipos desechables. Construir piezas pequeñas pero compatibles con la arquitectura final.

## Regla 4 — Graph is operational

Cada nodo del Living Knowledge Graph debe poder tener acciones reales: abrir, inspeccionar, ejecutar, conectar, auditar, bloquear, archivar.

## Regla 5 — Chat is not the center

El chat puede existir como consola o modo de conversación, pero nunca debe ser la arquitectura principal.

## Regla 6 — Framework boundaries

LangGraph, CrewAI, React Flow, Tauri, Slint, Aider, Claude Code y Codex son intercambiables. Atlas no lo es.

## Regla 7 — Visible trust

Toda acción relevante debe mostrar riesgo, confianza, estado, fuente y auditoría.

## Regla 8 — Human agency

El usuario debe poder pausar, aprobar, rechazar, editar plan, inspeccionar, revertir o pedir explicación.

## Regla 9 — No hidden autonomy

Atlas puede automatizar, pero no debe operar con efectos externos significativos sin política explícita.

## Regla 10 — Continuity as moat

La importación y análisis de conversaciones externas es diferenciador estratégico. No relegarlo a plugin menor.
