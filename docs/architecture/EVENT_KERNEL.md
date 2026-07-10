# EVENT_KERNEL — Atlas OS (ADR-058)

## Qué es

El sistema nervioso de representación del OS. NO es un segundo bus: es una
proyección serializada del `EventBus` existente + los eventos propios del
bridge/simulador. La auditoría sigue siendo el Merkle de `transparency/`.

## Piezas (todas con test)

| Pieza | Ruta | Qué hace |
| --- | --- | --- |
| Canon | `schemas/event.schema.json` (v1.0) + `src/atlas/events/schemas.py` | contrato del evento OS; paridad modelo↔schema testeada |
| Store | `src/atlas/events/store.py` | JSONL append-only en `$ATLAS_HOME/os_events/`, suscriptores in-process, unsubscribe |
| Player | `src/atlas/events/player.py` | reproduce `fixtures/events/*.jsonl`; marca `simulated=True`; rechaza `merkle_hash` en fixtures (OS-R9) |
| Bridge core | `src/atlas/events/core_bridge.py` | suscriptor de `core/event_bus.py`; mapping único `contracts.Event → OsEvent`; `simulated=False` |

## Reglas del canon

1. `id` = `evt_*`; `schema_version` = "1.0"; cambios de campos = nuevo minor
   ADITIVO (nunca romper fixtures existentes).
2. `simulated` es parte del contrato — la UI lo muestra SIEMPRE.
3. `audit.merkle_hash` solo del TransparencyLog real; el player lo rechaza y
   el bridge core no lo rellena (lo hará una integración transparency futura).
4. `causality.{parent_event_id,trace_id}` encadena pipelines (testeado en
   `tests/test_os_api.py::test_intent_pipeline_chained_and_simulated`).

## Tipos de evento en uso

Los del pack/prompt (§13): intent.*, plan.*, step.*, tool.*, memory.updated,
source.imported, connector.*, permission.evaluated, approval.*, audit.logged,
error.*, replay.* — más los proyectados del core (valores de
`contracts.EventType`, p.ej. `security.violation`). `type` es string libre en
el schema a propósito: el enum cerraría la proyección del core.

## Tests

`tests/test_os_event_schema.py` (paridad + fixtures) y
`tests/test_os_event_store.py` (store/player/bridge).
