# PHASE_1_14_BACKFILL_PLAN — Phase Recovery

No hay "Fase 11-14" que rellenar (ver `PHASE_SOURCE_INDEX.md`: nadie las
definió). Los huecos reales encontrados son otros, y este plan cubre
TODOS los huecos reales identificados en las Fases 3-7 de esta auditoría,
clasificados por si son backfill seguro (documental/mecánico) o si deben
quedar parkeados fuera de alcance de esta sesión.

## Gap 1 — F5 (Visual Orchestrator Territory) y F6 (Coding+Research
   Territories) sin cierre formal

- **Qué falta**: un ADR que registre la decisión de no construirlas ahora,
  con motivo.
- **¿Bloquea F17?**: No.
- **¿Bloquea Pixel Perfect?**: No.
- **¿Bloquea continuar F16?**: No, F16 ya está cerrado y no dependía de esto.
- **¿Superseded por F15/F16?**: Parcialmente en espíritu — F15's decisión
  D11 ("el shell es arnés, no UX final") hace que CUALQUIER inversión
  grande en el shell actual (incluido un canvas de workflows) sea
  prematura hasta que exista la superficie nativa. Eso es motivo suficiente
  para parking, no para implementación.
- **Ficheros a crear**: `docs/decisions/adr/adr_066_visual_orchestrator_and_
  territories_parked.md`.
- **Tests necesarios**: ninguno (doc-only).
- **Riesgo**: bajo (documental, reversible, no toca código).
- **Asignación**: Sonnet (yo mismo, doc-only, sin necesidad de subagente).
- **Orden**: primero (desbloquea nada, pero es la conclusión más citada del
  resto de fases).

## Gap 2 — "Audit replay" (Fase 7 Hardening) — reconsiderado tras inspección

- **Diagnóstico inicial** (incorrecto, corregido en esta misma pasada antes
  de escribir código): pensé que faltaba un endpoint `/replay`. Al leer
  `schemas/replay.schema.json` (`source_ref: "fixture o segmento del
  store"`) y `src/atlas/api/server.py`, la MITAD del gap ya está cerrada:
  `POST /simulate` ya usa `EventPlayer.play_fixture()` y devuelve un
  `ReplayResult` real — eso ES "audit replay de un fixture".
- **Lo que de verdad falta**: reproducir un SEGMENTO REAL del store (no un
  fixture) — p.ej. "vuelve a mostrar los eventos del intent X" — no existe
  hoy como capacidad (`EventPlayer` no tiene un método `replay_segment`, no
  es un caso de "wiring de un módulo ya diseñado", sería DISEÑAR una
  capacidad nueva: qué significa "replay" de eventos ya guardados, filtro
  por rango/intent_id, si re-emite a WS con `speed`, etc.).
- **Decisión revisada**: **PARK, no implementar en esta sesión.** No hay
  ningún consumidor real (ninguna vista de la UI pide "replay" de una
  sesión pasada) que tire de esta capacidad; construirla ahora sería
  añadir alcance especulativo sin requisito de producto, lo cual viola la
  disciplina de "no diseñar para requisitos hipotéticos". Se documenta
  como candidato explícito para cuando exista una necesidad real (p.ej.
  cuando el Developer Event Inspector de la UI quiera un botón "replay").

## Gap 3 — `docs/INDEX.yaml` sin entradas para los 11 documentos nuevos de
   `docs/continuation/phase_recovery/`

- **Qué falta**: registrar los documentos que esta propia auditoría produce.
- **Riesgo**: nulo — mecánico, regla estándar del repo
  (`scripts/docs_index_audit.py --write`).
- **Asignación**: Sonnet (yo), al final de la Fase 9, después de que todos
  los documentos existan.
- **Orden**: último de esta lista (depende de que el resto de ficheros ya
  existan).

## Gap 4 — Reclasificación de `status: propuesto` en INDEX.yaml para
   contenido de pack YA implementado

- **Qué falta**: ~26 entradas de `docs/handoff/atlas_product_os_liquid_ui_
  pack_v1/backend/*.md` y `atlas_build_pack/docs/atlas-bible/*.md`
  describen motores/contratos que SÍ tienen código real (p.ej.
  `POLICY_ENGINE.md` → `src/atlas/fabric/policy.py`), pero su `status` en
  INDEX.yaml sigue en `propuesto`.
- **¿Blocking?**: No.
- **Riesgo de hacerlo ahora**: MEDIO — requiere juicio caso por caso (¿el
  código implementa el spec EXACTAMENTE, o de forma distinta, lo que
  ameritaría `superseded` en vez de `vigente`?); tocar ~26+ entradas sin
  ese juicio caso por caso podría introducir clasificaciones incorrectas,
  que es peor que dejarlas honestamente en `propuesto` (que ya es un
  estado verdadero: "esto fue una propuesta", no "esto está desactualizado").
- **Decisión**: **PARK, no ejecutar en esta sesión.** Documentar como
  recomendación explícita en `PHASE_RECOVERY_FINAL_VERDICT.md` /
  `NEXT_AI_INSTRUCTIONS_AFTER_RECOVERY.md` para una sesión dedicada, no
  mezclarlo con el backfill de código de esta sesión.

## Gap 5 — El resto de lo NO implementado de F15 (`WHAT_WAS_NOT_IMPLEMENTED.md`)

- 17 sectores restantes, gestoría vertical completa, Presence Engine,
  Liquid App Runtime, conectores reales más allá de Gmail, vault de
  secretos propio, UI nativa/líquida, `docs/atlas-improvement/*` (fichas
  SOTA), 14 gaps restantes de `GAP_DETECTION_REGISTER.md`.
- **Decisión**: **PARK explícitamente, no backfill.** Son trabajo de
  producto futuro (F17+), no fases que "deberían haberse hecho" antes de
  F15/F16 — F15/F16 nunca los necesitaron como prerrequisito (confirmado en
  `F15_F16_DEPENDENCY_AUDIT.md`). Implementarlos ahora violaría
  explícitamente "no empieces F17, no empieces Pixel Perfect, no empieces
  UI nueva, no empieces Gmail real" del mandato de esta sesión.

## Resumen de qué SÍ se ejecuta en Fase 9

| # | Acción | Tipo | Riesgo | Bloquea algo si no se hace |
|---|---|---|---|---|
| 1 | ADR-066 parkeando F5/F6 | Doc | Bajo | No, pero cierra ambigüedad permanente |
| 2 | "Replay de segmento del store" | — | — | **NO se ejecuta** — reconsiderado como diseño especulativo sin consumidor real, parkeado con razón (ver arriba) |
| 3 | Regenerar `docs/INDEX.yaml` | Mecánico | Nulo | Si no se hace, `docs_index_audit.py --strict` fallaría en el próximo gate |
| 4 | Reclasificación masiva de `status:` | — | Medio | **NO se ejecuta** — parkeado con razón |
| 5 | Resto de `WHAT_WAS_NOT_IMPLEMENTED.md` | — | — | **NO se ejecuta** — parkeado con razón, fuera de alcance explícito |

## Conclusión

El backfill de código útil resulta ser **cero líneas de código de
producto** — el único gap que sobrevive al escrutinio como "seguro y con
valor real" es documental (ADR-066) + mecánico (INDEX.yaml). Esto es
consistente con el veredicto de `F15_F16_DEPENDENCY_AUDIT.md`: no hay
cimientos rotos ni huecos bloqueantes reales entre F1-F16, solo trabajo de
producto futuro correctamente fuera de alcance de esta sesión.
