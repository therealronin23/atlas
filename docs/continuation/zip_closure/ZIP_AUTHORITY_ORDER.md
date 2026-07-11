# ZIP_AUTHORITY_ORDER — Phase B

Verificado contra evidencia real (no asumido por default). El orden
sugerido por el mandato se confirma con una precisión: **repo real y ADRs
están AL MISMO NIVEL** (los ADRs son el registro formal de decisiones ya
tomadas sobre el repo, no una capa separada por encima), y por debajo de
ambos, los 3 ZIPs ordenados por qué tan directamente alimentaron lo que
existe hoy.

## Jerarquía de autoridad (verificada)

### Nivel 1 — Evidencia viva del repo (código + tests)

`src/atlas/`, `ui/atlas-shell/`, `schemas/*.schema.json`, `tests/test_os_*.py`.
**Autoridad máxima.** Si un ZIP o un doc contradice el código real, gana el
código — con una excepción: si el código contradice un ADR vigente sin
ninguna nota de migración, es una señal de drift a investigar, no
automáticamente "el código tiene razón".

### Nivel 1 (empate) — ADRs vigentes + WORK_LEDGER.md

`docs/decisions/adr/adr_058` a `adr_066`, `WORK_LEDGER.md`. Documentan POR
QUÉ el código real es como es. Verificado: cada decisión técnica de peso
(Vite en vez de Tauri, d3-force en vez de React Flow, PolicyEngine sobre
checklist de 10 gates) tiene un ADR real citable — no hay ninguna decisión
mayor sin ADR de respaldo.

### Nivel 2 — `atlas_product_os_liquid_ui_pack_v1.zip` (constitución de producto)

- **Rol**: fuente primaria de F15/F16, el 100% del código de
  `src/atlas/fabric/` y `src/atlas/business/` deriva de este pack.
- **¿Puede sobreescribir docs posteriores?**: No — es anterior a F15/F16, y
  F15/F16 ya lo interpretaron, adaptaron y en 6 casos rechazaron
  explícitamente (`WHAT_WE_REJECT_FROM_FABLE.md`). El pack es la propuesta;
  el código+ADR-060/061/062/063/065 son la decisión final.
  Contradicciones nuevas → gana el repo (Nivel 1).
- **¿Histórico solamente?**: No del todo — 26/95 schemas y 26/74 motores
  siguen siendo la referencia activa de diseño para lo YA construido, y
  `tasks/DO_NOT_DO.md` sigue citándose como el guardarraíl más concreto de
  los 3 packs (verificado en `PROMPT_TASK_ASSIMILATION_REPORT.md`).
- **¿Contiene trabajo pendiente?**: Sí — 480 de 506 ficheros describen
  producto NO construido (17 sectores, UI nativa, ~48 motores backend,
  Presence Engine, Liquid Workbench runtime). Es trabajo de producto futuro
  (F17+), no una obligación de esta sesión.
- **¿Contiene instrucciones superseded?**: Sí — 16 ficheros marcados
  `SUPERSEDED` en `PACK_MANIFEST_atlas_product_os_liquid_ui_pack_v1.md`
  (56 ADRs propuestos digeridos en 5 ADRs reales).

### Nivel 3 — `atlas_fable5_handoff_v1.zip` (handoff/historia de implementación)

- **Rol**: la fuente MÁS seguida al arrancar Atlas OS — Phase 0-4 de este
  pack coincide 1:1 con F0-F4 del repo real (evidencia fuerte, ver
  `PACK_MANIFEST_atlas_fable5_handoff_v1.md`).
- **¿Puede sobreescribir docs posteriores?**: No — es anterior al pack 3 y
  fue explícitamente revisado y parcialmente absorbido por él
  (`FABLE_LAST_OUTPUT_ANALYSIS.md` del pack 3 lo cita línea por línea).
- **¿Histórico solamente?**: Mayormente sí — su propósito (arrancar F0-F4)
  está cumplido. `UIUX_FINAL_SPEC.md` de este pack SÍ sigue vigente en
  espíritu (los 13 componentes reales de `ui/atlas-shell/` lo implementan
  con fidelidad), pero su estatus de "final" quedó superseded por la
  decisión D11 de F15 (el shell es arnés, no UX final) — ver Phase D.
- **¿Contiene trabajo pendiente?**: Menor — `SOTA_RESEARCH_PROTOCOL.md`
  pide cobertura de investigación más amplia de la que existe hoy en
  `docs/research/` (gap documental menor, no bloqueante).
- **¿Contiene instrucciones superseded?**: `UIUX_FINAL_SPEC.md` (estatus
  "final" superseded por D11), nombres de ficheros de continuidad (pide
  `ARCHITECTURE_DECISIONS_INDEX.md`, el repo real usa `DECISION_REVIEW.md`
  — variante de nombre, no de contenido).

### Nivel 4 — `atlas_os_build_pack_v1.zip` (semilla técnica más antigua)

- **Rol**: blueprint arquitectónico y contratos de schema más tempranos.
  Confirmado como la base de los 4 schemas raíz (`event`, `node`, `edge`,
  `adapter`) y del patrón de fixtures.
- **¿Puede sobreescribir docs posteriores?**: No.
- **¿Histórico solamente?**: Sí, con una excepción activa: `04_EVENT_CANON.md`
  sigue siendo la referencia válida para los 50+ tipos de evento (verificado
  contra `schemas/event.schema.json` — coincide, "CONFIRMADO SANO" en el
  manifiesto de Fase 2).
- **¿Contiene trabajo pendiente?**: Sí — **el único trabajo pendiente
  concreto y nombrado de los 3 ZIPs**: Fase 5 (Visual Orchestrator
  Territory) y Fase 6 (Coding+Research Territories) de
  `17_PHASES_ROADMAP.md`. Ver Phase C.
- **¿Contiene instrucciones superseded?**: Sí — 10 ADRs propuestos
  (0001-0010) nunca entraron al árbol real de decisiones; superseded por
  ADR-058/059/063/065.

## Resumen de la jerarquía verificada

```
Nivel 1 (empate): código+tests real  ==  ADRs vigentes + WORK_LEDGER.md
Nivel 2:  atlas_product_os_liquid_ui_pack_v1.zip   (constitución de producto, F15/F16)
Nivel 3:  atlas_fable5_handoff_v1.zip               (handoff F0-F4, mayormente cumplido)
Nivel 4:  atlas_os_build_pack_v1.zip                (semilla técnica, F0-F1 cumplido, F5/F6 pendiente)
```

Esto confirma el orden sugerido por el mandato con un ajuste: ADRs y
WORK_LEDGER no están "debajo" del repo real, están al mismo nivel porque
son inseparables — un ADR sin el código que describe no tiene autoridad, y
el código sin su ADR pierde trazabilidad de por qué es como es. Ninguno
manda sobre el otro.
