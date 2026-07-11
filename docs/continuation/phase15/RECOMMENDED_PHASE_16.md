# RECOMMENDED_PHASE_16

Orden sugerido, de mayor a menor prioridad (basado en NEW_GAPS_FOUND.md y
WHAT_WAS_NOT_IMPLEMENTED.md — no vibras, evidencia de esta fase):

1. **Converger PolicyEngine y `/permissions/evaluate`** en un único punto
   de evaluación (gap #2). Es la base para que el resto de Fase 16 no siga
   duplicando lógica de gates.
2. **Gate Engine real** enlazado a `BusinessCore.activation` y a
   `PolicyDecision.gate_id` (gap #3) — ceremonia auditable, no solo
   `approved_by` de texto libre.
3. **Persistir sesiones de onboarding** a disco (mismo patrón JSON con
   lock que `BusinessCoreEngine`, gap #5) para que sobrevivan un reinicio
   del bridge.
4. **Primer conector real** (candidato: Gmail read-only, es el de menor
   riesgo y ya tiene receta completa) — validaría todo el Integration
   Fabric contra un sistema de verdad, no solo mock.
5. **Sector Registry / Objective Registry** formales (hoy sector_id es un
   string suelto compartido por convención entre question packs y
   connector packs) — con esto, `sales_channels`→`resulting_workbenches`
   deja de ser solo strings y puede validarse contra un catálogo.
6. **UI de producto mínima** sobre `/connections` y `/business` (Connection
   Store + Business Setup Workbench del pack) — respetando
   `docs/design/UI_QUALITY_GATE.md`, en la superficie nativa futura, no en
   el shell arnés.
7. Legal/ToS registry por conector (gap #10, ya señalado en el propio pack).
8. Campo estructural `personal_channel: bool` en `connection_recipe.schema.json`
   para no depender de convención de nombres (gap #9).

## No repetir

- No pulir `ui/atlas-shell` como si fuera producto final (D11).
- No dar por hecho que un `gate_id` referenciado existe: la Fase 15 lo
  encontró roto una vez (gap #1) — verificar con el mismo test de
  regresión antes de añadir capacidades nuevas.
- No importar `atlas.api.*` a nivel de módulo desde `atlas.fabric.*` ni
  `atlas.business.*` (ver ADR-060, causa del ciclo ya corregido).
