# T2.1 — Mission Console fase VIVA (plan de arranque para sesión fresca)

**Para el driver que lea esto**: el operador quiere ponerse a fondo con la
UI/UX. Esta es la ola. NO hay dependencias pendientes: T0 está cerrado
(sucesión viva), el daemon produce misiones/receipts reales, y el grafo se
re-sella solo. La secuencia "T2 después de T1" del plan maestro §5 se
adelanta por criterio de la doctrina §2.5 (el operador NO programa: cada
semana sin consola es él pegando textos entre 200 IAs) — cambio de secuencia,
no de alcance.

## Lo que YA existe (verificado 2026-07-17, no asumir que falta)

- `ui/atlas-shell/` — Vite/React (ADR-059), **1.930 líneas de TSX reales**,
  `node_modules` instalado, scripts `dev`/`build`/`preview`.
- Componentes: `MissionConsole.tsx` (458), `LivingGraph.tsx` (465),
  `AutobuildLedger` (236), `HarnessPanel` (195), `UniversalBar`,
  `RealityPanel`, `MemoryVault`, `Timeline`, `EventInspector`,
  `ExecutionPipeline`, `App.tsx` (291).
- **No son mocks**: `src/core/api.ts` hace `fetch` real contra la API
  (`api.health/graph/events/reality/memorySummary/connectors/permissions`) y
  `connectEventsWs` abre WebSocket de eventos.
- Backend: `src/atlas/api/server.py` (bridge read-only 7341 — JAMÁS meter el
  Orchestrator dentro: corrompe Merkle, memoria atlas-os-foundation).

## Lo que NO se sabe (primer trabajo de la ola: MEDIR, no suponer)

El API server no estaba corriendo el 2026-07-17, así que **nadie ha visto esta
UI viva recientemente**. Antes de diseñar nada:

1. Arrancar API + `npm run dev` (vía preview_start, jamás Bash para servers).
2. Inventario honesto por componente: ¿pinta datos reales, vacío, o revienta?
   Tabla `componente → estado → causa` con evidencia (consola/red/captura).
3. Solo entonces decidir qué se arregla, qué se rehace y qué sobra.

Regla: es EVOLUCIÓN de la consola existente, no reescritura (decisión sellada,
plan maestro §4). Si un componente estorba, se jubila con motivo escrito.

## El objetivo de la ola (evidencia observable)

**El operador aprueba una misión real de la ruta dorada desde la pantalla**,
sin tocar texto ni terminal, y el receipt queda en Merkle. Ese es el corte:
ni más features ni menos.

## Estándar obligatorio (doble skill, sellado)

- `frontend-design:frontend-design` — dirección estética con carácter; los 9
  mockups JARVIS del operador son la referencia. Nada de "AI slop".
- `agent-skills:frontend-ui-engineering` — composición, WCAG 2.1 AA, estados
  loading/empty/error, responsive 320-1440.
- Implementación: Sonnet (economía sellada). Fable/Opus: criterio y auditoría.

## Riesgos conocidos (premortem corto)

- **Reescribir por impulso estético**: 1.930 líneas funcionando valen más que
  un lienzo en blanco bonito. Medir primero (§"Lo que NO se sabe").
- **UI que miente**: si un panel no tiene datos reales, debe decir "sin datos"
  — jamás pintar un placeholder que parezca vivo. Es la disciplina de
  honestidad del proyecto aplicada a píxeles.
- **Meter escritura en el bridge read-only**: la aprobación necesita un camino
  de escritura; diseñarlo por la ruta dorada (aprobación registrada), NO
  abriendo el bridge. Decisión N2 → Cónclave al llegar ahí.

## Después de esta ola

T2.2 (Knowledge view sobre el grafo Kuzu: comunidades navegables — las tools
`graph_communities`/`graph_semantic_neighbors` ya existen) y T2.3 (Visual
Orchestrator, ADR-066).
