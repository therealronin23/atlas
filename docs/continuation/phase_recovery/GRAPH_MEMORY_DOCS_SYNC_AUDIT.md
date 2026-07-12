# GRAPH_MEMORY_DOCS_SYNC_AUDIT — Phase Recovery

Inspeccionado: `src/atlas/memory/` (16 módulos del núcleo preexistente),
`memory/` (raíz del repo — seeds de `SystemContextLoader`, sin relación con
los packs), `MEMORY.md` de Claude Code (`/home/ronin/.claude/projects/
-home-ronin-proyectos-atlas-core/memory/`), `docs/INDEX.yaml` (3254 líneas,
555 referencias a rutas `docs/handoff/*`), `WORK_LEDGER.md`,
`docs/design/atlas_ecosystem_map.md`, grafo Kuzu / tronco de conocimiento.

## Hallazgo principal: cero acoplamiento entre la capa Atlas OS (F15/F16) y
   el grafo/memoria del núcleo — por diseño, no por omisión

`src/atlas/fabric/` y `src/atlas/business/` (F15/F16) tienen **cero
imports** de `atlas.memory` o de nada relacionado con Kuzu/grafo
(`grep -rn "import atlas\.\(memory\|graph\)" src/atlas/fabric/
src/atlas/business/` → 0 resultados, verificado en esta sesión). Esto
coincide EXACTAMENTE con el hueco ya documentado en
`docs/continuation/phase15/WHAT_WAS_NOT_IMPLEMENTED.md`: "un `BusinessEntity`
promovido queda en `$ATLAS_HOME/business_core/`, no se escribe
automáticamente en el índice de memoria." No es un descubrimiento nuevo de
esta auditoría — es una confirmación independiente de que ese documento no
mentía.

## Clasificación de conceptos F1-F16 por dónde viven

| Concepto | Solo en ZIP | En docs | En memoria (Claude Code) | En grafo (Kuzu) | En código | En tests | Duplicado | Obsoleto pero vivo |
|---|---|---|---|---|---|---|---|---|
| Event Canon / Event Kernel | — | `docs/decisions/adr/adr_058*.md` | Sí (`atlas-os-foundation-2026-07-10.md`) | No aplica (no es código fuente) | `src/atlas/events/*` | Sí | No | No |
| UI Shell / arnés | — | ADR-059, `ui/atlas-shell/README.md` | Sí | No aplica | `ui/atlas-shell/src/*` | Sí (build) | No | No |
| Integration Fabric / PolicyEngine | pack 3 solamente para el resto de motores nombrados | `docs/continuation/phase15/*` | Sí (`atlas-os-phase15-*.md`) | No aplica | `src/atlas/fabric/*` | Sí | No | No |
| Business Core | pack 3 | `docs/continuation/phase15/*` | Sí | No aplica | `src/atlas/business/*` | Sí | No | No |
| Gate Engine (F16-2) | — (invención propia, no del pack) | ADR-063 | Sí (`atlas-os-phase16-*.md`) | No aplica | `src/atlas/fabric/gates.py` | Sí | No | No |
| Gmail connector | pack 3 (`AI_PROVIDER_REGISTRY.md` menciona conectores en general, no Gmail específico) | ADR-065 | Sí | No aplica | `src/atlas/fabric/connectors/gmail.py` | Sí | No | No |
| **Visual Orchestrator (F5)** | **Sí, SOLO en el ZIP/docs/handoff** | `17_PHASES_ROADMAP.md`, `EPICS_AND_TASKS.md` (`status: propuesto`) | **No** — nunca se guardó memoria sobre esto | No | **No existe** | **No existe** | No | **Sí — sigue "propuesto" en INDEX.yaml sin que nadie lo haya revisitado** |
| **Coding+Research Territories (F6)** | **Sí, SOLO en el ZIP/docs/handoff** | ídem | **No** | No | **No existe** | **No existe** | No | **Sí, igual que F5** |
| 22 sectores completos (pack 3 pide 22, hay 5) | pack 3 | `WHAT_WAS_NOT_IMPLEMENTED.md` (ya honesto) | No hay memoria dedicada a esto | No | Solo 5 sectores en `fixtures/sectors/` | `tests/test_os_registries.py` cubre los 5 | No | No — ya está documentado como hueco conocido, no obsoleto-oculto |
| ~40 motores de `backend/*.md` no implementados (MCPGateway, WebhookManager, CRMCoreEngine, etc.) | pack 3 | `WHAT_WAS_NOT_IMPLEMENTED.md` (lista parcial, ampliada en la auditoría 2026-07-11) | No | No | No | No | No | No — documentado honestamente |

## ¿Está sincronizado el grafo/memoria con F1-F16?

**No aplica en el sentido que la pregunta original asume.** El grafo Kuzu del
repo (`atlas-graph`, `project_graph.py`, `callgraph_to_kuzu.py`) indexa
**código fuente y su estructura de imports** (nodos=módulos/funciones,
aristas=imports/llamadas), no "conceptos de fase". Por diseño, todo el
código real de F1-F16 (fabric/, business/, events/, api/, ui/atlas-shell)
SÍ está dentro del árbol que el grafo indexa (no hay exclusión especial), así
que aparecerá automáticamente en la próxima regeneración del grafo
(`maintenance_project_graph_tick`, gateada por HEAD). No hay un "grafo de
producto" separado que debiera reflejar sectores/objetivos/gates — esos
viven como fixtures+schemas, correctamente.

La memoria de Claude Code (sistema separado, en
`~/.claude/projects/-home-ronin-proyectos-atlas-core/memory/`) SÍ tiene
entradas dedicadas para cada fase real (F0-F4 vía `atlas-os-foundation-
2026-07-10.md`, F15 vía `atlas-os-phase15-*.md`, F16 vía
`atlas-os-phase16-*.md`) — **pero no tiene ninguna entrada para F5/F6**,
porque nunca sucedieron. Esto es correcto, no un gap: no se debe memorizar
trabajo que no existe.

## Docs vs. INDEX.yaml — desviación real encontrada

`docs/INDEX.yaml` tiene 555 líneas que contienen la cadena `docs/handoff` —
correspondiente a ~270+ entradas reales de los 3 packs (cada entrada ocupa
~4-5 líneas YAML: path/type/status/verified). Todas las entradas de
`atlas_build_pack/docs/atlas-bible/*` y de `atlas_product_os_liquid_ui_pack_v1/*`
inspeccionadas en esta sesión están en `status: propuesto` — **ninguna fue
promovida nunca a `vigente`**, ni siquiera las que SÍ se implementaron
(p.ej. `POLICY_ENGINE.md`, cuyo contenido real vive en
`src/atlas/fabric/policy.py` y está commiteado, probado y en uso). Esto es
una desviación real de higiene documental: el índice no distingue "pack
completamente sin ejecutar" (F5/F6) de "pack cuyo contenido ya se
implementó y debería re-etiquetarse". No es grave (no hay drift de
estructura, `docs_index_audit.py` seguiría pasando), pero es honesto
señalarlo como mejora de Fase 9 (backfill), no ignorarlo.

## Duplicados

Ninguno encontrado. No hay dos sistemas paralelos implementando el mismo
concepto de F1-F16 (a diferencia del hallazgo histórico de
`memory-lessons-disconnection-2026-07-03` sobre LessonStore, que es un tema
distinto y ya resuelto, del núcleo, no de Atlas OS).

## Veredicto de esta fase

No hay drift oculto entre grafo/memoria/docs para lo que SÍ se implementó
(F0-F4, F7-F10, F15-F16): código, tests, ADRs y memoria de sesión están
consistentes entre sí. El único "desincronizado" real es documental y
esperado: ~270 entradas de `docs/handoff/atlas_product_os_liquid_ui_pack_v1/`
y ~19 de `atlas_build_pack/` siguen en `status: propuesto` sin
re-clasificar tras la implementación parcial, y F5/F6 no tienen ninguna
huella fuera del ZIP/docs/handoff porque genuinamente nunca se ejecutaron.
