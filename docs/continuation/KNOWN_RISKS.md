# KNOWN_RISKS — Atlas OS (para la siguiente IA)

Resumen operativo de riesgos que NO debes redescubrir por las malas. Detalle y
estado vivo en `docs/risks/RISK_REGISTER.md`.

1. **JAMÁS instancies `Orchestrator` en el bridge/API.** Dos instancias
   escribiendo el mismo Merkle log corrompen la cadena (bug real documentado
   en `src/atlas/interfaces/dashboard.py`). El bridge es read-only sobre el
   core (ADR-058).
2. **JAMÁS `git add -A`.** El working tree lleva cambios sin commitear del
   operador (WORK_LEDGER.md entre ellos). Add selectivo por ruta, siempre.
3. **No toques `config/governance.json`, `AGENTS.md`, `WORK_LEDGER.md`,
   `docs/backlog.yaml` ni la carpeta `1/`** (cuarentena). Cambios ahí se
   proponen como diff en chat al operador.
4. **No inventes hashes de auditoría.** `audit.merkle_hash` en eventos OS solo
   puede venir del TransparencyLog real; si no hay, null + simulated.
5. **Docs nuevos → regenerar INDEX.yaml** con
   `PYTHONPATH=src python scripts/docs_index_audit.py --write` antes de
   commitear, o el PreflightGate acusará drift.
6. **No dependencias Python nuevas sin ADR** (invariante 6). fastapi/uvicorn/
   pydantic ya están. Para validar schemas usa pydantic, no jsonschema.
7. **La suite completa tarda ~4 min y el daemon del lazo puede estar vivo**:
   corre suites dirigidas (`pytest tests/test_os_*.py`) salvo cierre de fase.
8. **Outbound = gate.** Ninguna acción hacia fuera (email/mensaje/publicar)
   sin approval.required → granted explícito. En v1 todo conector es mock.
9. **(Fase 15) Capa `fabric`/`business` NUNCA importa `atlas.api.*` a nivel
   de módulo.** Causa un ciclo real (`fabric.policy → api.models →
   api.__init__ → api.server → api.product_routes → fabric.concierge →
   fabric.policy`) que rompe cualquier entrypoint que importe fabric
   primero (p.ej. la CLI). Si necesitas un tipo de `atlas.api.models`,
   ponlo bajo `TYPE_CHECKING` e importa de verdad dentro de la función.
10. **(Fase 15) `BusinessCoreEngine`/`AuthBroker`/`ConnectorRegistry` sin
    `path`/`refs_path`/`approvals_path` explícito escriben en el
    `$ATLAS_HOME` real.** En tests, pasa SIEMPRE esos parámetros bajo
    `tmp_path` (o monkeypatch `ATLAS_HOME`); `register_product_routes`/
    `create_app` aceptan `business_core_path` explícito por la misma razón.
11. **(Fase 15) Todo `gate_id` que declares en `fabric/capabilities.py`
    debe existir en `fixtures/governance/gates.json`.** Ya pasó una vez
    (8 de 26 no existían); hay test de regresión
    (`test_every_capability_gate_id_resolves_to_a_real_gate`) pero no lo
    borres si añades capacidades nuevas.
