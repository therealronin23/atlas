# ADR-060 — Integration Fabric, Easy Connection Layer y PolicyEngine

- Estado: aceptado (2026-07-10)
- Contexto: `atlas_product_os_liquid_ui_pack_v1` exige que Atlas negocie
  capacidades seguras con cada sistema externo en vez de conectar a ciegas,
  y que "conectar sea fácil, actuar gobernado". El evaluador v1
  (`/permissions/evaluate`, Fase 4) solo mira patrones de acción contra
  `fixtures/governance/gates.json`; no modela capability, data_class ni
  invariantes independientes de fixture.

## Decisión

1. **Connection Ladder codificada como dato** (`src/atlas/fabric/ladder.py`):
   12 peldaños ordenados por riesgo, API-first, computer-use en el puesto
   11 de 12. `RecipeEngine` rechaza (no sirve a medias) cualquier receta
   que recomiende computer-use o invierta el orden de sus fallbacks.
2. **RecipeEngine + PackEngine fail-closed**: una receta que concede por
   defecto una capacidad marcada `gate_required` en el catálogo, o que
   mezcla la misma capacidad en concedidas y prohibidas, se rechaza al
   cargar — no hay "receta parcialmente válida".
3. **PolicyEngine nuevo EXTIENDE, no duplica, el evaluador v1** (D14): capas
   en orden — provenance no confiable → invariantes duros en código →
   reglas blandas de `fixtures/security/policies.json` → spec de la
   capacidad → default fail-closed. Los 7 invariantes constitucionales
   (WhatsApp personal, cloud+sensible, certificado, oficial, contable,
   computer-use, contenido no confiable) están en `HARD_RULES` (Python), no
   en el fixture: borrarlo o vaciarlo no los relaja (P15-R2, probado en
   `test_hard_rules_independent_of_fixture_file`).
4. **AuthBroker nunca ve el secreto**: solo emite/valida referencias
   `env:VAR`; rechaza con `SecretRejected` cualquier valor con forma de
   secreto real (prefijos conocidos, JWT, cadenas largas aleatorias). Vault
   propio queda `BLOCKED_BY_DESIGN` — no se finge un backend de secretos
   que no existe.
5. **ConnectorRegistry detecta rug-pull por hash del descriptor completo**,
   no por leer si la nueva descripción "suena mal": aprobar fija un hash;
   verificar con un descriptor distinto degrada a
   `rug_pull_suspected` y exige re-aprobación humana.
6. **HealthMonitor/ConnectionTestRunner nunca fingen "real"**: sin
   conector real implementado, `mode=real` responde
   `BLOCKED_BY_MISSING_DEPENDENCY`, igual que `/reality` y `/memory/summary`
   en Fase 4.

## Consecuencias

- Rutas nuevas (`/connections/*`, `/integrations/health`) y comandos CLI
  (`atlas connections ...`) sin tocar `/permissions/evaluate` existente.
- Bug real encontrado y corregido durante la implementación: import
  circular `fabric.policy → api.models → api.__init__ → api.server →
  api.product_routes → fabric.concierge → fabric.policy`, al importar
  `GateSpec` a nivel de módulo. Fix: `GateSpec` solo bajo `TYPE_CHECKING`
  en `fabric/policy.py`; import real perezoso dentro de `load_gates()`.
  Documentado para que nadie reintroduzca un import de `atlas.api.*` a
  nivel de módulo en `atlas.fabric.*` (capa inferior no debe depender de
  capa superior).
- 10 recetas + 5 packs de conectores, todo `demo: true`, cero secretos.
