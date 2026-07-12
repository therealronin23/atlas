# REPO_ALIGNMENT_REPORT — repo actual vs atlas_product_os_liquid_ui_pack_v1

Fecha: 2026-07-10. Pack descomprimido en `docs/handoff/atlas_product_os_liquid_ui_pack_v1/`
(status: propuesto — constitución de producto de mayor autoridad entre los handoffs,
por debajo del repo real y la evidencia verificada).

## Veredicto del pack sobre la sesión anterior (asumido)

El pack **valida** lo construido esta mañana como base técnica y lo **degrada** como
producto: `context/FABLE_LAST_OUTPUT_ANALYSIS.md` conserva bus+bridge read-only+
schemas+tests+disciplina de continuación, y rechaza el shell React como UX final.
Consecuencia inmediata: **el rediseño visual JARVIS del shell (petición previa del
operador) queda muerto** — `tasks/DO_NOT_DO.md` lo prohíbe explícitamente ("Do not
polish the web harness as final UX", "cheap Jarvis"). No se había escrito código de
ese rediseño; no hay nada que revertir.

## Qué exige el pack y qué existe ya (no duplicar)

| Exigencia del pack | Estado en repo | Acción Fase 15 |
| --- | --- | --- |
| No segundo event bus | `core/event_bus.py` + proyección ADR-058 | reutilizar `OsEventStore.emit` |
| No segundo API server | bridge 7341 (`src/atlas/api/server.py`) | registrar rutas nuevas en `create_app` |
| No segunda memoria | índice canónico ADR-057 + capa os_import_v1 | sin cambios; candidatos con `requires_review` |
| Gates/policy | `fixtures/governance/gates.json` + evaluador fail-closed v1 | generalizar a PolicyEngine por capability+data_class |
| Connector registry | `fixtures/connectors/` (5 mock) + `/connectors` | conservar; recipes = capa humana encima |
| Web shell = arnés | implícito (ADR-059 lo llama harness-compatible) | marcarlo EXPLÍCITO (README + Decision Review) |
| Schemas | 12 estrictos + espejos pydantic + paridad | añadir 10 del dominio fabric/business, mismo patrón |
| Continuation docs | docs/continuation/ completo | actualizar + subcarpeta phase15/ |

## Qué NO existe y la Fase 15 construye

1. **Integration Fabric**: Connection Ladder (12 peldaños), discovery, health,
   testing harness, auth broker (solo referencias de credencial).
2. **Easy Connection Layer**: recipes + packs + concierge + catálogo por categorías
   humanas ("Gmail", "Odoo"), no por protocolo.
3. **PolicyEngine por capability**: el evaluador v1 solo mira gates por patrón de
   acción; falta data_class, provenance/source-trust y los invariantes duros
   (WhatsApp personal, cloud+sensible, computer-use).
4. **Atlas Business Core**: CRM/ERP nativo draft-first con activación gateada.
5. **Adaptive Question Engine**: packs de preguntas concretas por sector + sesión
   con rama "no sé" + preview confirmable.
6. **Legacy Link Layer**: canonicidad explícita (external/atlas/hybrid), mirror
   read-only por defecto, sync desactivado por defecto.

## Contradicciones detectadas (pack vs repo) y resolución

- **Schemas laxos del pack** (`required: []`, `additionalProperties: true`) vs
  patrón del repo (estrictos + paridad pydantic). Resolución: la ley de mejora de la
  constitución permite endurecer sin diluir → schemas estrictos en `schemas/`,
  el pack queda como referencia en docs/handoff/. Campos del pack se conservan
  como núcleo y se completan con los exigidos por el prompt (setup_steps,
  permissions_explainer, why_this_is_needed...).
- **Rutas API** sugeridas `/atlas/...` vs estilo del bridge sin prefijo.
  Resolución: sin prefijo (`/connections/*`, `/business/*`, `/integrations/health`)
  — consistencia con el bridge existente; documentado en DECISION_REVIEW D13.
- **Nombres de docs de continuación en raíz** (prompt) vs docs raíz curados por el
  operador. Resolución: todo bajo `docs/continuation/phase15/` + actualización de
  los vigentes en `docs/continuation/`.
- **UI harness**: el pack pide pantallas mínimas de validación *si son útiles*;
  DO_NOT_DO prohíbe pulirlas. Resolución: fase centrada en backend/contratos;
  pantalla de validación solo si el presupuesto de la sesión lo permite, marcada
  "harness".

## Autoridad aplicada

repo real > evidencia verificada > atlas_product_os_liquid_ui_pack_v1 >
atlas_fable5_handoff_v1 > atlas_os_build_pack_v1 > prompts históricos.
