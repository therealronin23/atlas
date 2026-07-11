# PHASE_15_COMPLETION_REPORT — Atlas Product OS (Integration Fabric + Business Core)

Fecha: 2026-07-10/11. Origen: `atlas_product_os_liquid_ui_pack_v1.zip`.

## Repo state

- Rama `main`, sin push. Commits de esta fase (en orden):
  `bac77283` (ingesta+plan), `50293445` (10 schemas + espejos), `986c77f0`
  (Integration Fabric + PolicyEngine), `63932f44` (corpus de seguridad),
  `13f724f8` (Business Core + Question Engine + Legacy Link), `cd3fd214`
  (API /connections+/business + CLI).
- Dirty paths del operador (12, previos a esta sesión) intactos; no se ha
  usado `git add -A` en ningún commit.

## Files changed (resumen; detalle en cada commit)

- 10 schemas nuevos en `schemas/` + espejos en `src/atlas/fabric/models.py`
  y `src/atlas/business/models.py`.
- `src/atlas/fabric/`: models, capabilities, ladder, policy, recipes,
  packs, auth_broker, registry, health, testing, concierge, discovery.
- `src/atlas/business/`: models, entities, core_engine, questions, extract,
  legacy.
- `src/atlas/api/product_routes.py` + wiring aditivo en `server.py` y
  `interfaces/cli.py`.
- `fixtures/`: connection_recipes (10), connector_packs (5), question_packs
  (5), security (18, incluye corpus copiado + fixtures propios), business_core
  (9).
- Tests: `test_os_product_contracts.py` (33), `test_os_fabric.py` (21),
  `test_os_policy_security.py` (21), `test_os_business.py` (18),
  `test_os_product_api.py` (12) — 105 tests nuevos.
- Docs: este directorio, `docs/decisions/adr/adr_060_*`, `adr_061_*`,
  `docs/design/UI_QUALITY_GATE.md`, `docs/architecture/DECISION_REVIEW.md`
  (D11-D14), `ui/atlas-shell/README.md`.

## What works (verificado, no asumido)

- Suite OS completa: **144 passed** (`tests/test_os_*.py`), mypy strict
  limpio en `api/`, `events/`, `fabric/`, `business/`, `interfaces/cli.py`.
- Bridge real levantado con `ATLAS_HOME` aislado en `/tmp` y probado por
  curl en vivo: `/health`, `/connections/catalog`, `/connections/plan`,
  `/business/question-packs` — respuestas reales, no simuladas por el test.
- CLI real ejecutada (no solo importada): `atlas connections catalog`,
  `atlas connections plan gmail`, `atlas connections test gmail --mode
  mock`, `atlas business question-packs`, `atlas business onboarding-start
  qp_restauracion_hosteleria` — las cinco funcionan de punta a punta.
- Ciclo completo de onboarding probado vía API real
  (`test_onboarding_full_loop_via_api`): start→answer→confirm→skip→
  preview→confirm, con rechazo real (422) si se intenta preview con
  respuestas pendientes de confirmar.
- Ciclo completo de activación de Business Core probado vía API real:
  draft→(activate directo rechazado 422)→request-activation→activate.

## What is simulated

- Todos los conectores son mock/sandbox; ningún conector real (Gmail/Odoo/
  Claude en producción) existe todavía. `mode=real` siempre devuelve
  `BLOCKED_BY_MISSING_DEPENDENCY`, nunca un éxito fingido.
- El AuthBroker no persiste secretos reales (ni falsos): solo referencias
  `env:VAR`. No hay vault propio.
- Los `EntityCandidate` de los fixtures son datos demo (`cliente.demo@`,
  `Proveedor Demo`...), nunca datos reales de ningún usuario.
- El `gate_id` en `BusinessCore.activation` es descriptivo; no está
  enlazado al motor de gates general de `governance/` (gap, ver
  NEW_GAPS_FOUND #3).

## Tests run

```
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 .venv/bin/python -m pytest tests/test_os_*.py -q
# 144 passed
MYPYPATH=src PYTHONPATH=src .venv/bin/python -m mypy src/atlas/api/ src/atlas/events/ src/atlas/fabric/ src/atlas/business/ src/atlas/interfaces/cli.py
# Success: no issues found in 32 source files
```
Suite COMPLETA del repo: pendiente de ejecutar al cierre de esta sesión
(ver TESTING_STATUS.md de esta carpeta para el resultado final).

## Known limitations

Ver `NEW_GAPS_FOUND.md` (12 gaps clasificados) y `KNOWN_RISKS.md` global
actualizado.

## Next safest step

`RECOMMENDED_PHASE_16.md` en esta misma carpeta.

## Bugs reales encontrados y corregidos DURANTE la implementación (honesto)

1. **Import circular** `fabric.policy → api.models → api.__init__ →
   api.server → api.product_routes → fabric.concierge → fabric.policy`.
   No lo cazaban los tests (siempre importaban `atlas.api.server`
   primero); lo cazó invocar `atlas connections plan` en frío desde CLI.
   Fix: `GateSpec` solo bajo `TYPE_CHECKING` en `policy.py`.
2. **Riesgo de escritura en `~/atlas` real durante tests**: `BusinessCoreEngine`
   sin `path` explícito habría escrito en `$ATLAS_HOME/business_core/` real
   (mismo patrón que ya forzó la app perezosa en Fase 4). Detectado
   ANTES de ejecutar el test sospechoso (revisando el código, no por
   accidente) — se verificó `ls ~/atlas/business_core` para confirmar
   ausencia antes y después del fix.
3. **Regla dura de WhatsApp personal con `connector_id` equivocado**
   (`whatsapp_personal` en vez de `whatsapp_personal_import`, el id real
   del fixture) — se habría "arreglado solo" en los tests porque el
   fallback (`gate_required` de la capacidad) igual bloqueaba, ocultando el
   bug. Cazado por diseño (revisión manual del código antes de correr),
   documentado como lección: revisar que los `connector_id` en reglas
   duras coincidan con los IDs reales de los fixtures, no solo confiar en
   el fallback.
4. **Regla dura de computer-use nunca casaba** porque exigía `route` en la
   request además de `capability`, y una request típica solo pasa
   `capability`. Cazado por el propio test que yo mismo escribí
   (`test_computer_use_matches_remote_command_high_risk_profile`).
5. Ladder inválido en `generic_crm.recipe.json` (managed_oauth como
   fallback de una ruta recomendada peor) — cazado por
   `RecipeEngine`/`PackEngine` fail-closed, exactamente como debían.
