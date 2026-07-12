# GRAPH_MEMORY_DOC_SYNC_CLOSURE — Phase G

Reutiliza y re-verifica (no re-deriva desde cero) los hallazgos de
`docs/continuation/phase_recovery/GRAPH_MEMORY_DOCS_SYNC_AUDIT.md`
(sesión de Phase Recovery, mismo día), reencuadrados específicamente para
el cierre de los 3 ZIPs.

Inspeccionado de nuevo: `src/atlas/memory/`, `memory/` (raíz, seeds de
`SystemContextLoader`), `MEMORY.md` de Claude Code, `docs/INDEX.yaml`
(3319 líneas tras la última regeneración), `WORK_LEDGER.md`,
`docs/design/atlas_ecosystem_map.md`, grafo Kuzu.

## Clasificación por concepto de ZIP (docs / memoria / grafo / código / tests / missing / stale / duplicado / superseded)

| Concepto | ZIP origen | En docs | En memoria (Claude Code) | En grafo (Kuzu) | En código | En tests | Missing | Stale | Duplicado | Superseded |
|---|---|---|---|---|---|---|---|---|---|---|
| Event Canon / Event Kernel | ZIP1 (schema) + ZIP2 (bridge) | Sí (ADR-058) | Sí | No aplica (indexa código, no conceptos) | Sí | Sí | No | No | No | No |
| UI Shell / arnés | ZIP1 (arquitectura) + ZIP2 (spec final) | Sí (ADR-059) | Sí | No aplica | Sí | Sí (build) | No | No | No | Parcial — estatus "final" superseded por D11, contenido no |
| Integration Fabric / PolicyEngine | ZIP3 | Sí (`phase15/*`) | Sí | No aplica | Sí | Sí | No | No | No | No |
| Business Core | ZIP3 | Sí | Sí | No aplica | Sí | Sí | No | No | No | No |
| Gate Engine (F16-2) | Invención propia (no de ningún ZIP) | Sí (ADR-063) | Sí | No aplica | Sí | Sí | No | No | No | No |
| Gmail connector | ZIP3 | Sí (ADR-065) | Sí | No aplica | Sí | Sí | No | No | No | No |
| **Visual Orchestrator (Fase 5, ZIP1)** | ZIP1 | Sí, pero solo en `docs/handoff/` (`status: propuesto`) + ADR-066 (parking, nuevo) | **No hasta esta auditoría** — cerrado ahora vía la memoria de esta sesión | No | No | No | **Sí (código)** | **Sí (`status: propuesto` desde ingestión, nunca revisitado hasta ahora)** | No | No — PARKED, no superseded |
| **Coding+Research Territories (Fase 6, ZIP1)** | ZIP1 | ídem | ídem | No | No | No | Sí (código) | Sí (mismo patrón) | No | No — PARKED |
| 22 sectores (ZIP3 pide 22, hay 5) | ZIP3 | Sí (`WHAT_WAS_NOT_IMPLEMENTED.md`, ya honesto) | No hay memoria dedicada | No | Solo 5 sectores | Sí (los 5) | Sí (17 sectores) | No | No | No |
| ~48 motores backend no implementados (MCP Gateway, Webhook Manager, CRM/ERP Core separados, etc.) | ZIP3 | Sí (parcial, ampliado en esta auditoría) | No | No | No | No | Sí | No | No | Parcial (CRM/ERP Core: superseded por decisión de datos-no-clases, ver Conflict Table #9) |
| `docs/INDEX.yaml` entradas de pack (~290 entre ZIP1+ZIP3) | ZIP1, ZIP3 | Sí, todas `status: propuesto` | No aplica | No aplica | N/A (son entradas de índice, no código) | N/A | No | **Sí — ~26 apuntan a contenido YA implementado y siguen en `propuesto`** | No | No |

## ¿Está sincronizado el grafo con los 3 ZIPs?

**No aplica en el sentido literal.** El grafo Kuzu (`atlas-graph`,
`project_graph.py`) indexa código fuente y su estructura de imports, no
"conceptos de ZIP". Todo el código real derivado de los 3 ZIPs
(`fabric/`, `business/`, `events/`, `api/`, `ui/atlas-shell/`) SÍ está
dentro del árbol que el grafo indexa por defecto — no hay exclusión
especial ni necesidad de sincronización manual. Confirmado sin cambios
desde la auditoría de Phase Recovery de esta misma sesión previa.

## ¿Está sincronizada la memoria (Claude Code) con los 3 ZIPs?

**Parcialmente, y correctamente así.** Hay entradas de memoria dedicadas
para todo lo IMPLEMENTED (foundation F0-F4, Fase 15, Fase 16, y ahora
Phase Recovery + este cierre de ZIPs). **No hay memoria para Fase 5/6**
porque nunca sucedieron — correcto, no se debe memorizar trabajo
inexistente.

## ¿Están sincronizados los docs con los 3 ZIPs?

**Sí en estructura (INDEX.yaml no tiene huérfanas ni sin-indexar), no en
clasificación fina.** La desviación real y ya conocida: ~26 entradas de
`docs/INDEX.yaml` correspondientes a specs de ZIP1/ZIP3 cuyo contenido SÍ
se implementó siguen en `status: propuesto` en vez de reclasificarse.
Ver Conflict Table #12 — PARKED, requiere sesión dedicada de juicio caso
por caso, no ejecutado aquí (mismo motivo que en Phase Recovery: riesgo
medio de clasificar mal si se hace en bloque).

## Duplicados

Ninguno encontrado entre los 3 ZIPs y el código real. Los 3 ZIPs SÍ se
duplican ENTRE SÍ parcialmente (mismo contenido general de Fase 0-4 en
ZIP1 y ZIP2, con numeración distinta) — ya cubierto en
`CROSS_ZIP_CONFLICT_TABLE.md` #1-#3, no es un duplicado de código/docs
reales, es fragmentación de fuente.

## Conceptos "solo-ZIP" (nunca llegaron a docs/memoria/grafo/código fuera del propio ZIP)

Visual Orchestrator (Fase 5), Coding+Research Territories (Fase 6), 17
sectores restantes, ~48 motores backend no implementados, 51 pantallas de
UI nativa, Presence Engine, Liquid Workbench runtime. Todos documentados
como tal en `WHAT_WAS_NOT_IMPLEMENTED.md` (pre-existente) y en los cierres
ZIP1/ZIP3 de esta sesión — ninguno es un descubrimiento nuevo, todos están
ahora formalmente cerrados (PARKED o pendiente-no-bloqueante F17+).

## Veredicto final de esta fase

- **Docs sincronizados**: Sí, estructuralmente (`docs_index_audit.py
  --strict` limpio). Con una desviación de clasificación fina conocida y
  parkeada (26 entradas `propuesto`→posible reclasificación futura).
- **Memoria sincronizada**: Sí — cada concepto implementado tiene entrada;
  ningún concepto no-implementado tiene entrada falsa.
- **Grafo sincronizado**: Sí, por diseño (indexa código, no fases).
- **Conceptos aún solo-en-ZIP**: Fase 5/6 (ahora PARKED con ADR-066), 17
  sectores, ~48 motores, UI nativa, Presence Engine, Liquid Workbench
  (todos backlog F17+, ya documentados).
- **Conceptos duplicados/obsoletos-pero-vivos**: Ninguno en código. La
  única "obsolescencia viva" real es documental: `status: propuesto` sin
  actualizar para contenido ya implementado (INDEX.yaml, 26 entradas).
