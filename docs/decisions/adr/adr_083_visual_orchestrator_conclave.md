# ADR 083: Visual Orchestrator Conclave (T2.3)

**Status:** Accepted  
**Date:** 2026-08-03  
**Supersedes:** ADR 066  

## Contexto

El ítem `t2-3-visual-orchestrator-reopen-scope` del backlog exigía la reapertura del debate arquitectónico alrededor de la Fase 5 (Visual Orchestrator, un canvas tipo n8n para componer Workflows Dinámicos de forma visual). Anteriormente, el ADR-066 había aparcado (parked) esta fase esperando a que la superficie de UI nativa de Atlas fuera elegida y se estabilizara.

Ahora que hemos consolidado Flutter como el stack de UI oficial (T2.1 Mission Console Dedicated App) y hemos implementado con éxito la vista del grafo de conocimiento (T2.2 Knowledge View Native), se requiere decidir formalmente si incluimos un editor de nodos (canvas interactivo) en esta iteración.

## Decisión

**Se decide mantener el Visual Orchestrator en estado "parked".**

El stack de Flutter permite la creación de UI complejas y Custom Painters, lo que en teoría soporta la construcción de un canvas. Sin embargo:
1. Construir o integrar una librería de Canvas drag & drop interactivo para nodos introduce una complejidad desproporcionada que puede desestabilizar la Mission Console que apenas ha nacido.
2. Atlas se encuentra en una etapa donde la autonomía (F2.6 / Mission Loop) es mucho más crítica que la orquestación manual-visual de procesos. Los Dynamic Workflows ya son enrutados eficientemente por los agentes bajo demanda.
3. El enfoque inmediato debe permanecer en alcanzar la T3 (Capacidad universal de operación) sin distraer recursos en herramientas visuales complejas para workflows.

Por ende, este ADR supersede formalmente al ADR-066 y extiende el estado de hibernación de la Fase 5.

## Consecuencias

- No se introducirán dependencias de canvas (como react-flow, o equivalentes en Flutter) en esta ola de desarrollo.
- La interfaz visual se enfocará exclusivamente en el monitoreo pasivo-aprobatorio (Mission Console) y la navegación (Knowledge Graph).
- **Próxima fecha/condición de revisión:** Al finalizar la implementación de la T3 (Operador universal), si los Workflows Dinámicos crecen en complejidad al punto en que los operadores humanos no pueden depurarlos sin una herramienta visual dedicada.
