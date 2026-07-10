# GOVERNANCE_KERNEL — Atlas OS sobre la governance real

## Autoridad

La governance REAL vive en el core: `governance/` + `config/governance.json`
(intocable por agentes, invariante 3) + CapabilityIssuer/PermissionProfile/
AtlasExecutor + BwrapJail + Merkle. El OS añade REPRESENTACIÓN y un evaluador
v1 propio para su superficie, sin suplantar al core.

## Lo construido (Fase 9 inicial)

- `schemas/gate.schema.json` + `schemas/permission.schema.json` (contratos).
- `fixtures/governance/gates.json`: gate_outbound (email/mensajes/publicar →
  aprobación humana), gate_destructive_fs, gate_credentials (always_block),
  gate_shell.
- `POST /permissions/evaluate` (bridge): **fail-closed** — acción cubierta por
  gate → decisión del gate; no cubierta y no-lectura → require_approval; solo
  lectura explícita (read/get/list/search) → allow. Cada evaluación emite
  `permission.evaluated`.
- UI: Permissions Matrix (tabla de gates + probador en vivo) y Security Center
  (aprobaciones pendientes + actividad de governance).

## Límites declarados (v1, honestos)

- El evaluador OS trabaja sobre gates de FIXTURE (`simulated=true` en el
  evento): la evaluación real de capacidades sigue siendo del core.
- approval.granted/denied desde la UI NO ejecuta nada: v1 representa; el HITL
  real ocurre en el runtime (atlas pending/approve).
- Zero trust por defecto: todos los conectores nacen mock, outbound bloqueado.

## Camino a real

1. Bridge lee gates desde governance real (read-only) en vez de fixture.
2. `approval.required` del core proyectado vía CoreEventBridge (ya soporta
   cualquier EventType).
3. Aprobaciones desde la UI → cola HITL existente (`atlas pending`), nunca
   ejecución directa. Requiere decisión de transporte (OPEN_QUESTIONS #4).
