# CANONICAL_WORK_ORDER_AFTER_ZIPS — Phase H

Este es el único orden válido de trabajo tras el cierre de los 3 ZIPs.
Sustituye cualquier lectura informal de "seguimos con Phase 17" o
"seguimos con Pixel Perfect" basada solo en que el número sigue al 16.

## 1. Ya cerrado

- ZIP1 (`atlas_os_build_pack_v1`) — CLOSED_WITH_PARKED_ITEMS
- ZIP2 (`atlas_fable5_handoff_v1`) — CLOSED_WITH_PARKED_ITEMS
- ZIP3 (`atlas_product_os_liquid_ui_pack_v1`) — CLOSED_WITH_PARKED_ITEMS
- F0-F4, F7-F10, F15, F16 — IMPLEMENTED (evidencia código+test+doc)
- Conflict Table #11 (Gate A / autoridad de la Constitución) — RESOLVED vía
  ADR-067 (2026-07-11, esta actualización)

## 2. Cerrado con ítems parkeados

- **Fase 5 — Visual Orchestrator Territory** (ZIP1) — PARKED vía ADR-066
- **Fase 6 — Coding+Research Territories** (ZIP1) — PARKED vía ADR-066
- **17 sectores restantes** de 22 (ZIP3) — PARKED, backlog F17+
- **~48 motores backend no implementados** (MCP Gateway, Webhook Manager,
  Sandbox Executor, Computer Use Adapter, etc., ZIP3) — PARKED, backlog F17+
- **Presence Engine, Liquid Workbench runtime** (ZIP3) — PARKED, backlog F17+
- **51 pantallas de UI nativa** (ZIP3 design/) — PARKED, sujeto a D11
- **Reclasificación de ~26 entradas `status: propuesto`** en
  `docs/INDEX.yaml` con contenido ya implementado — PARKED, requiere juicio
  caso por caso (Gap 4 de `PHASE_1_14_BACKFILL_PLAN.md`)

## 3. Qué debe backfillearse antes de Pixel Perfect

**Nada de código.** Un backfill DOCUMENTAL obligatorio antes de que
"Pixel Perfect" pueda siquiera scopearse con sentido:
**OPERATOR_DECISION_POINT_01 — decidir si D11 se reabre** (¿el shell actual
se convierte en la superficie nativa final, o se construye una superficie
nueva desde cero?). Sin esa decisión, cualquier trabajo de "Pixel Perfect"
sobre `ui/atlas-shell` sería pulir un arnés que la propia Fase 15 decidió
NO pulir — sería repetir el error que esta auditoría existe para prevenir.
Esta decisión es del operador, no de la IA (ver Phase J pregunta 11).

## 4. Qué debe backfillearse antes de F17

**Nada bloqueante.** Nota importante: **"F17" no está definido en ningún
ZIP, ADR o doc de continuación** — no es un fichero, es solo "el número
que sigue a F16". Antes de que "F17" signifique algo ejecutable, alguien
(el operador) tiene que definir su alcance. Candidatos NO obligatorios
listados en la sección 7.

## 5. Qué NO debería implementarse nunca porque está superseded

- Tauri como shell de escritorio v1 (ADR-059 lo diferido, no lo prohíbe
  para siempre — pero no es el camino elegido hoy)
- React Flow / Cytoscape / Sigma para el grafo (d3-force es la decisión
  vigente, ADR-059)
- Los 10 ADRs propuestos 0001-0010 de ZIP1 tal cual están escritos
  (digeridos, no re-adoptar literalmente)
- Los 56 ADRs propuestos de ZIP3 tal cual están escritos (digeridos en
  ADR-060 a ADR-065)
- `CRM_CORE_ENGINE`/`ERP_CORE_ENGINE` como clases Python separadas
  (decisión: datos/vistas, no clases — ver Conflict Table #9)

## 6. Qué debe quedarse parkeado (no implementar ahora, no borrar)

Igual que la lista de la sección 2 — todos los ítems parkeados permanecen
parkeados hasta decisión explícita del operador que los reabra.

## 7. Cuál es la siguiente fase exacta

```
NEXT:
ZIP_BACKFILL_01 — registrar los 8 documentos nuevos de
docs/continuation/zip_closure/ en docs/INDEX.yaml
(scripts/docs_index_audit.py --write) y re-validar --strict.
Mecánico, riesgo nulo, ya permitido por el mandato (Phase I).

THEN:
OPERATOR_DECISION_POINT_01 — el operador debe elegir EXACTAMENTE uno o
varios de los siguientes ítems nombrados antes de que cualquier
implementación nueva continúe. Ninguno es obligatorio; ninguno está
pre-aprobado.
```

## 8. Qué fases vienen después de eso

Candidatos nombrados exactamente (ninguno "continuar después", todos con
nombre propio):

| Nombre exacto | Qué es | Depende de |
|---|---|---|
| ~~`GATE_A_CONSTITUTION_CLOSURE_01`~~ | **CERRADO (2026-07-11)** — ADR-067 "Atlas Constitution Authority": la Constitución vive distribuida en AGENTS.md + ecosystem_map + ADRs vigentes + `00_ATLAS_PRODUCT_CONSTITUTION.md` (ZIP3); no se crea `docs/atlas-master/`. Conflict Table #11 → RESOLVED | — |
| `INDEX_RECLASSIFICATION_01` | Reclasificar caso-por-caso ~26 entradas `propuesto`→estatus correcto en INDEX.yaml | Nada — ejecutable ya, si el operador lo prioriza |
| `GATE_ENGINE_GENERALIZATION_01` | Generalizar `src/atlas/fabric/gates.py` más allá de Business Core activation | Nada — candidato ya identificado en F16 |
| `POLICYENGINE_V1_CONVERGENCE_01` | Convergencia total PolicyEngine↔evaluador v1 (ADR-062 dejó capabilities conocidas sin converger del todo) | Nada |
| `PIXEL_PERFECT_SCOPE_DECISION` | Decidir si se reabre D11 y bajo qué alcance — **es una decisión, no una implementación** | `OPERATOR_DECISION_POINT_01` |
| `VISUAL_ORCHESTRATOR_REOPEN_DECISION` | Decidir si se reabre ADR-066 (Fase 5/6) y bajo qué alcance | `OPERATOR_DECISION_POINT_01` |
| `GMAIL_LIVE_TOKEN_EXERCISE_01` | Ejercitar `GmailReadOnlyConnector.list_messages()` en vivo | Un `GMAIL_OAUTH_TOKEN` real suministrado explícitamente por el operador |
| `F17_SCOPE_DEFINITION` | Definir qué es "F17" formalmente (hoy no existe en ningún ZIP/ADR) | `OPERATOR_DECISION_POINT_01` |

## 9. Qué trabajo es seguro para dynamic workflow

`ZIP_BACKFILL_01` (ejecutado), `GATE_A_CONSTITUTION_CLOSURE_01` (ejecutado,
ver ADR-067), `INDEX_RECLASSIFICATION_01` (con verificación humana del
resultado, riesgo medio de juicio pero mecánica de ejecución segura),
`GATE_ENGINE_GENERALIZATION_01` (fase de implementación dirigida a Sonnet,
planificación a Opus).

## 10. Qué trabajo necesita revisión del operador

`PIXEL_PERFECT_SCOPE_DECISION`, `VISUAL_ORCHESTRATOR_REOPEN_DECISION`,
`F17_SCOPE_DEFINITION`, `GMAIL_LIVE_TOKEN_EXERCISE_01` (requiere que el
operador aporte la credencial), `INDEX_RECLASSIFICATION_01` (revisión
final antes de commit, por el riesgo de clasificar mal).

## 11. Qué trabajo requiere Cónclave/revisión de seguridad

`POLICYENGINE_V1_CONVERGENCE_01` (toca el evaluador de permisos — límite
de seguridad, requiere Cónclave antes de mergear cualquier cambio de
comportamiento del evaluador fail-closed). `VISUAL_ORCHESTRATOR_REOPEN_
DECISION` y `PIXEL_PERFECT_SCOPE_DECISION` si su resultado implica nueva
superficie de ejecución (canvas que ejecuta workflows = nueva superficie
de riesgo, ameritaría Cónclave en el momento en que se scopee, no ahora).

## NO EMPEZAR hasta que este orden lo diga explícitamente

- F17 (no definido — ver `F17_SCOPE_DEFINITION`)
- Pixel Perfect (bloqueado por `PIXEL_PERFECT_SCOPE_DECISION`)
- Expansión de Gmail / nuevos conectores reales
- Nuevas verticales de sector
- Visual Orchestrator / Coding+Research Territories (bloqueado por
  `VISUAL_ORCHESTRATOR_REOPEN_DECISION`, ADR-066 sigue vigente)
