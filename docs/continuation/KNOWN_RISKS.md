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
12. **(Fase 16) Hay un daemon de autoconstrucción vivo contra este mismo
    repo** (`ATLAS_SELF_BUILD=1`, verificable con
    `ps aux | grep ATLAS_SELF_BUILD` o inspeccionando
    `/proc/<pid>/environ`). Puede modificar ficheros (incl. UI) EN
    PARALELO a tu sesión sin avisar — antes de escribir código nuevo en un
    área, corre `git status` por si ya lo hizo; verifícalo (build real +
    tests + smoke) en vez de descartar o sobrescribir a ciegas. Detectado
    2026-07-11: implementó el arnés UI de F16-6 mientras se cerraban
    F16-1..5/7/8, con cero colisión de ficheros.
13. **(Fase 16) Un bridge en 7341 puede quedar zombi**: proceso vivo que
    ya no escucha en el puerto (visto con `PID 1446025`, `ps aux` lo
    lista pero `ss -ltnp` no muestra nada escuchando). Si un
    `uvicorn ... --port 7341` nuevo falla a conectar por curl, comprueba
    con `ss -ltnp | grep 7341` antes de asumir que el puerto está
    ocupado — puede estar libre de verdad.
14. **(Phase Recovery, 2026-07-11) No existe una única numeración de fases
    F1-F16 — hay 5 fuentes distintas que no coinciden entre sí** (ver
    `docs/continuation/phase_recovery/PHASE_SOURCE_INDEX.md`). No busques
    "Fase 11" a "Fase 14": nadie las definió nunca, no es un hueco
    silencioso. Lo que SÍ quedó sin ejecutar y sin cerrar formalmente
    hasta ahora eran **Fase 5 (Visual Orchestrator Territory) y Fase 6
    (Coding+Research Territories)** de `docs/handoff/atlas_build_pack/
    docs/atlas-bible/17_PHASES_ROADMAP.md` — parkeadas explícitamente en
    ADR-066, no bloquean nada de F15/F16/F17.
