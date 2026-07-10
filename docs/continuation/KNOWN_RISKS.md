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
