# ADR-062 — Convergencia PolicyEngine ↔ /permissions/evaluate

- Estado: aceptado (2026-07-11)
- Contexto: Fase 15 dejó dos evaluadores de permisos coexistiendo (D14,
  NEW_GAPS_FOUND #2): el v1 de `/permissions/evaluate` (patrones de acción
  sobre `gates.json`, heurística de lectura) y el `PolicyEngine` nuevo
  (capability + data_class + 7 invariantes duros). Riesgo: una capability
  nueva añadida solo a uno de los dos deja el otro desactualizado.

## Decisión

`/permissions/evaluate` converge de forma **incremental y no disruptiva**:

1. Si `action` es una capability conocida (`get_capability(action) is not
   None`) → se evalúa con `PolicyEngine` (misma `gates.json` + reglas
   blandas). Es la única verdad para el espacio de capabilities.
2. Si no → evaluador v1 legacy intacto (acciones tipo `mail.send`,
   `github.repos.read`, `credentials.rotate` que no son capabilities del
   catálogo siguen exactamente como antes).
3. El vocabulario se normaliza en esta superficie: `require_gate` del
   PolicyEngine se muestra como `require_approval` (el término que ya usa
   la UI del evaluador v1). El `payload.evaluator` distingue
   `"policy_engine"` de `"os_v1_fixture_gates"` para trazabilidad.

## Por qué incremental y no un reemplazo total

Un reemplazo de golpe cambiaría decisiones de acciones legacy ya cubiertas
por tests verdes de Fase 4 (`test_evaluate_*` en `test_os_api.py`). La
convergencia por capability cierra el gap donde importa (el espacio nuevo)
sin tocar el contrato legacy. La convergencia TOTAL (mapear todas las
acciones legacy a capabilities) queda como trabajo futuro con su propio
mapeo acción→capability auditado.

## Consecuencias

- Una capability como `email.send` evaluada por `/permissions/evaluate`
  ahora hereda el invariante duro y el `policy_id` del PolicyEngine, no una
  heurística de patrón.
- `PermissionEvaluation` gana `policy_id` poblado cuando la decisión viene
  del PolicyEngine.
- Sin dependencia circular: `fabric.policy` importa `GateSpec` de forma
  perezosa (ADR-060); `server.py` importa `PolicyEngine`/`get_capability`
  dentro del handler.
