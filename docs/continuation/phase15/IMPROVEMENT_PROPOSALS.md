# IMPROVEMENT_PROPOSALS — Fase 15

## 1. Converger PolicyEngine y el evaluador v1 de `/permissions/evaluate`

- **Problem**: dos evaluadores de permisos activos a la vez (D14 los dejó
  coexistir a propósito para no romper Fase 4, pero el gap persiste).
- **Proposed improvement**: `/permissions/evaluate` delega en
  `PolicyEngine` para toda acción que tenga una `capability` mapeable;
  mantiene su forma de respuesta actual para no romper la UI existente.
- **Why it improves Atlas**: una sola fuente de verdad para "¿esto está
  permitido?" en todo el bridge, en vez de dos que pueden divergir.
- **Risk**: bajo si se hace incremental (mapear acción→capability antes de
  redirigir); medio si se intenta de golpe (podría cambiar decisiones ya
  probadas en `test_os_api.py`).
- **Files affected**: `src/atlas/api/server.py` (evaluate()),
  `src/atlas/fabric/policy.py` (tabla acción→capability).
- **ADR needed**: sí — es un cambio de arquitectura de gobernanza.

## 2. Gate Engine real para activaciones de Business Core

- **Problem**: `approve_activation(business_core_id, approved_by)` confía
  en un string; no hay ceremonia con evidencia adjunta ni registro
  separado de la aprobación.
- **Proposed improvement**: nuevo `GateTicket` (schema propio) creado por
  `request_activation`, resuelto por una acción `approve_activation`/
  `reject_activation` que además valida que el ticket siga vigente.
- **Why it improves Atlas**: hoy "gate" es un campo descriptivo; con esto
  se vuelve un objeto auditable con su propio ciclo de vida, coherente con
  `docs/architecture/GOVERNANCE_KERNEL.md`.
- **Risk**: medio — toca el modelo `BusinessCore.activation` (cambio de
  schema, requiere migración de los fixtures existentes).
- **Files affected**: `schemas/business_core.schema.json`,
  `src/atlas/business/core_engine.py`, fixtures `business_core/`.
- **ADR needed**: sí.

## 3. Persistencia de sesiones de onboarding

- **Problem**: `_sessions` vive en memoria del proceso del bridge.
- **Proposed improvement**: reutilizar el patrón `_Store` de
  `core_engine.py` (JSON con lock) para onboarding sessions, con
  `$ATLAS_HOME/business_core/onboarding_sessions.json`.
- **Why it improves Atlas**: sobrevive a reinicios del bridge; permite
  reanudar un onboarding largo (gestoría tiene 4+ preguntas con follow-ups
  potenciales).
- **Risk**: bajo — mismo patrón ya probado, sin cambio de schema.
- **Files affected**: `src/atlas/api/product_routes.py`
  (nuevo `_SessionStore` en vez de dict).
- **ADR needed**: no (extensión mecánica de un patrón ya aceptado).

## 4. Campo estructural `personal_channel` en connection_recipe

- **Problem**: el invariante duro de WhatsApp personal depende de que
  `connector_id` empiece por `whatsapp_personal` (convención de nombre,
  no propiedad estructural — gap #9).
- **Proposed improvement**: añadir `personal_channel: bool` (default
  false) al schema; `pol_hard_whatsapp_personal_send` (renombrar a
  `pol_hard_personal_channel_send`) matchea por ese campo, no por prefijo
  de id. `RecipeEngine` inyecta el flag en el `PolicyRequest.connector_id`
  o se pasa aparte.
- **Why it improves Atlas**: cierra el gap #9 con una propiedad que no se
  puede evadir renombrando el conector.
- **Risk**: bajo-medio — cambio de schema con migración de 2 fixtures
  (`whatsapp_personal_import.recipe.json` + cualquier futuro similar).
- **Files affected**: `schemas/connection_recipe.schema.json`,
  `src/atlas/fabric/models.py`, `src/atlas/fabric/policy.py`,
  fixtures `connection_recipes/whatsapp_personal_import.recipe.json`.
- **ADR needed**: no — es endurecer un invariante ya aceptado, no una
  decisión de arquitectura nueva.
