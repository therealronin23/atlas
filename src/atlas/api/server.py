"""Atlas OS Backend Bridge — FastAPI en 127.0.0.1:7341 (ADR-058).

Reglas no negociables:
  * CERO Orchestrator en este proceso (doble instancia = corrupción Merkle).
  * Todo lo simulado va marcado; audit.merkle_hash jamás se inventa (OS-R9).
  * El core se LEE (reality, memoria vía sqlite read-only); el único estado
    escrito es el event store OS.

Arrancar:  atlas os-bridge
       o:  uvicorn atlas.api.server:app --host 127.0.0.1 --port 7341
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from atlas.api.models import (
    ConnectorSpec,
    EvaluateRequest,
    GateSpec,
    IntentRequest,
    PermissionEvaluation,
    SimulateRequest,
)
from atlas.api.product_routes import register_product_routes
from atlas.events.player import EventPlayer
from atlas.events.schemas import Causality, EventStatus, OsEvent, Risk
from atlas.events.store import OsEventStore

HOST = "127.0.0.1"
PORT = 7341

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "fixtures"

_INTENT_PIPELINE: list[tuple[str, str, EventStatus]] = [
    ("intent.created", "user", EventStatus.COMPLETED),
    ("intent.classified", "kernel", EventStatus.COMPLETED),
    ("context.loaded", "kernel", EventStatus.COMPLETED),
    ("plan.created", "kernel", EventStatus.COMPLETED),
    ("step.started", "kernel", EventStatus.RUNNING),
    ("tool.called", "kernel", EventStatus.RUNNING),
    ("tool.finished", "kernel", EventStatus.COMPLETED),
    ("step.finished", "kernel", EventStatus.COMPLETED),
    ("memory.updated", "memory", EventStatus.COMPLETED),
    ("audit.logged", "governance", EventStatus.COMPLETED),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_connectors(connectors_dir: Path) -> dict[str, ConnectorSpec]:
    specs: dict[str, ConnectorSpec] = {}
    if connectors_dir.exists():
        for path in sorted(connectors_dir.glob("*.json")):
            spec = ConnectorSpec.model_validate_json(path.read_text(encoding="utf-8"))
            specs[spec.connector_id] = spec
    return specs


def _load_gates(gates_path: Path) -> list[GateSpec]:
    if not gates_path.exists():
        return []
    raw = json.loads(gates_path.read_text(encoding="utf-8"))
    return [GateSpec.model_validate(g) for g in raw]


def _memory_summary() -> dict[str, Any]:
    """Lectura sqlite READ-ONLY del índice canónico (ADR-057). Jamás
    instancia SqliteMemoryIndex aquí: cargaría el embedder (~500MB)."""
    db = Path("~/atlas-mcp/memory.db").expanduser()
    if not db.exists():
        return {"real": False, "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "detail": f"no existe {db}"}
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            records = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        finally:
            conn.close()
        return {"real": True, "records": int(records), "db": str(db)}
    except sqlite3.Error as exc:
        return {"real": False, "status": "UNVERIFIED", "detail": str(exc)}


def create_app(
    store: OsEventStore | None = None,
    fixtures_dir: Path | None = None,
    business_core_path: Path | None = None,
) -> FastAPI:
    fixtures = fixtures_dir or _FIXTURES
    event_store = store or OsEventStore()
    player = EventPlayer(event_store)
    connectors = _load_connectors(fixtures / "connectors")
    gates = _load_gates(fixtures / "governance" / "gates.json")

    app = FastAPI(title="Atlas OS Bridge", docs_url=None, redoc_url=None,
                  openapi_url=None)

    def emit(
        type_: str,
        summary: str,
        *,
        actor: str,
        status: EventStatus = EventStatus.COMPLETED,
        risk: Risk = Risk.LOW,
        payload: dict[str, Any] | None = None,
        intent_id: str | None = None,
        process_id: str | None = None,
        parent: str | None = None,
        trace: str | None = None,
        simulated: bool = True,
    ) -> OsEvent:
        event = OsEvent(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            type=type_,
            timestamp=_now(),
            source="atlas.api.simulator" if simulated else "atlas.api.bridge",
            actor=actor,
            summary=summary,
            status=status,
            risk=risk,
            visible=True,
            simulated=simulated,
            payload=payload or {},
            intent_id=intent_id,
            process_id=process_id,
            causality=None
            if parent is None and trace is None
            else Causality(parent_event_id=parent, trace_id=trace),
        )
        return event_store.append(event)

    # -- Estado / lecturas reales ------------------------------------------

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "real": True,
            "service": "atlas-os-bridge",
            "os_events": event_store.count(),
            "connectors": len(connectors),
            "gates": len(gates),
        }

    @app.get("/reality")
    def reality() -> dict[str, Any]:
        from atlas.core.reality import collect_reality  # import perezoso: caro

        return {"real": True, "report": collect_reality()}

    @app.get("/memory/summary")
    def memory_summary() -> dict[str, Any]:
        return _memory_summary()

    @app.post("/memory/import")
    def memory_import(raw: dict[str, Any]) -> dict[str, Any]:
        """Import REAL (Fase 8): preserva raw, extrae por reglas, emite eventos."""
        from atlas.api.conversation_import import import_conversation

        result = import_conversation(raw)
        if not result.already_imported:
            # Este import SÍ ocurrió (raw preservado en disco): simulated=False.
            emit(
                "source.imported",
                f"Conversación externa importada ({len(result.records)} memorias extraídas)",
                actor="memory",
                simulated=False,
                payload={
                    "raw_ref": result.source_ref,
                    "provider": str(raw.get("provider", "unknown")),
                    "records": len(result.records),
                    "layer": "os_import_v1",
                },
            )
            if result.records:
                emit(
                    "memory.updated",
                    f"{len(result.records)} registros de memoria OS con provenance",
                    actor="memory",
                    simulated=False,
                    payload={"layer": "os_import_v1", "count": len(result.records)},
                )
        return result.to_dict()

    @app.get("/memory/imports")
    def memory_imports(limit: int = 200) -> dict[str, Any]:
        from atlas.api.conversation_import import list_imported_records

        records = list_imported_records(limit=limit)
        return {"count": len(records), "records": records, "layer": "os_import_v1"}

    # -- Eventos / timeline / grafo ----------------------------------------

    @app.get("/events")
    def events(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        items = event_store.read(limit=limit, offset=offset)
        return {"count": len(items), "events": [e.model_dump() for e in items]}

    @app.get("/timeline")
    def timeline(limit: int = 100) -> dict[str, Any]:
        visible = [e for e in event_store.iter_events() if e.visible][-limit:]
        return {"count": len(visible), "events": [e.model_dump() for e in visible]}

    @app.get("/graph")
    def graph() -> dict[str, Any]:
        path = fixtures / "graph" / "initial_graph.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="grafo inicial ausente")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"simulated": True, "source": "fixture", **data}

    # -- Intent / simulación -------------------------------------------------

    @app.post("/intent")
    def intent(req: IntentRequest) -> dict[str, Any]:
        intent_id = f"int_{uuid.uuid4().hex[:10]}"
        process_id = f"proc_{uuid.uuid4().hex[:10]}"
        trace = f"trace_{uuid.uuid4().hex[:10]}"
        emitted: list[OsEvent] = []
        parent: str | None = None
        for type_, actor, status in _INTENT_PIPELINE:
            payload: dict[str, Any] = {"simulated_pipeline": True}
            if type_ == "intent.created":
                payload["text"] = req.text
            event = emit(
                type_,
                f"{type_} — pipeline simulado del intent",
                actor=actor,
                status=status,
                payload=payload,
                intent_id=intent_id,
                process_id=process_id,
                parent=parent,
                trace=trace,
            )
            parent = event.id
            emitted.append(event)
        return {
            "intent_id": intent_id,
            "process_id": process_id,
            "simulated": True,
            "events": [e.model_dump() for e in emitted],
        }

    @app.post("/simulate")
    def simulate(req: SimulateRequest) -> dict[str, Any]:
        fixture = fixtures / "events" / f"{req.fixture}.jsonl"
        if not fixture.exists():
            raise HTTPException(status_code=404, detail=f"fixture {req.fixture} no existe")
        return player.play_fixture(fixture).to_dict()

    # -- Integration Fabric ---------------------------------------------------

    @app.get("/connectors")
    def list_connectors() -> dict[str, Any]:
        return {
            "count": len(connectors),
            "connectors": [c.model_dump() for c in connectors.values()],
        }

    @app.post("/connectors/{connector_id}/test")
    def test_connector(connector_id: str) -> dict[str, Any]:
        spec = connectors.get(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector desconocido")
        emit(
            "connector.connected",
            f"Test de {spec.display_name} en modo {spec.mode.value}",
            actor="connector",
            payload={"connector_id": connector_id, "mode": spec.mode.value},
        )
        return {"ok": True, "mode": spec.mode.value, "simulated": spec.mode.value != "real"}

    @app.post("/connectors/{connector_id}/sync")
    def sync_connector(connector_id: str) -> dict[str, Any]:
        spec = connectors.get(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector desconocido")
        process_id = f"proc_{uuid.uuid4().hex[:10]}"
        started = emit(
            "connector.sync.started",
            f"Sync de {spec.display_name} iniciado ({spec.mode.value})",
            actor="connector",
            status=EventStatus.RUNNING,
            payload={"connector_id": connector_id},
            process_id=process_id,
        )
        emit(
            "connector.sync.finished",
            f"Sync de {spec.display_name} completado ({spec.mode.value})",
            actor="connector",
            payload={"connector_id": connector_id, "items": 0},
            process_id=process_id,
            parent=started.id,
        )
        return {"ok": True, "process_id": process_id, "simulated": spec.mode.value != "real"}

    # -- Governance -----------------------------------------------------------

    @app.get("/permissions")
    def permissions() -> dict[str, Any]:
        return {"count": len(gates), "gates": [g.model_dump() for g in gates]}

    @app.post("/permissions/evaluate")
    def evaluate(req: EvaluateRequest) -> dict[str, Any]:
        """Evaluador de permisos. Convergencia incremental (ADR-062):
        si `action` es una capability conocida del catálogo → PolicyEngine
        (capability + data_class + invariantes duros); si no → evaluador v1
        legacy sobre patrones de gate. Una sola verdad para el espacio de
        capabilities, compatibilidad para acciones legacy."""
        from atlas.fabric.capabilities import get_capability  # noqa: PLC0415
        from atlas.fabric.policy import PolicyEngine, PolicyRequest  # noqa: PLC0415

        if get_capability(req.action) is not None:
            engine = PolicyEngine(
                rules_path=fixtures / "security" / "policies.json",
                gates=gates,
            )
            pdecision = engine.evaluate(PolicyRequest(capability=req.action))
            # Vocabulario del contrato de representación: require_gate del
            # PolicyEngine se muestra como require_approval en esta superficie.
            pdecision_str: str = (
                "require_approval"
                if pdecision.decision == "require_gate"
                else pdecision.decision
            )
            evaluation = PermissionEvaluation(
                action=req.action,
                resource=req.resource,
                actor=req.actor,
                decision=pdecision_str,
                risk=pdecision.risk,
                reason=pdecision.reason,
                policy_id=pdecision.policy_id,
                gate_id=pdecision.gate_id,
                evaluated_at=_now(),
            )
            emit(
                "permission.evaluated",
                f"{req.action} → {pdecision_str}",
                actor="governance",
                risk=pdecision.risk,
                status=EventStatus.WAITING_USER
                if pdecision_str == "require_approval"
                else EventStatus.COMPLETED,
                payload={"evaluator": "policy_engine", **evaluation.model_dump()},
            )
            return {"simulated": True, "evaluation": evaluation.model_dump()}

        # -- v1 legacy: patrones de acción sobre gates.json --------------------
        matched: GateSpec | None = None
        for gate in gates:
            if not gate.enabled:
                continue
            for pattern in gate.applies_to:
                if req.action == pattern or (
                    pattern.endswith("*") and req.action.startswith(pattern[:-1])
                ):
                    matched = gate
                    break
            if matched:
                break
        if matched is not None:
            decision = "deny" if matched.approval_mode == "always_block" else matched.default_decision
            risk = matched.risk_threshold
            reason = f"gate {matched.gate_id} cubre {req.action}"
            gate_id: str | None = matched.gate_id
        elif req.action.split(".")[-1].startswith(("read", "get", "list", "search")):
            decision, risk, reason, gate_id = "allow", Risk.LOW, "acción de lectura sin gate", None
        else:
            decision, risk, reason, gate_id = (
                "require_approval",
                Risk.MEDIUM,
                "acción no cubierta por ningún gate: fail-closed",
                None,
            )
        evaluation = PermissionEvaluation(
            action=req.action,
            resource=req.resource,
            actor=req.actor,
            decision=decision,
            risk=risk,
            reason=reason,
            gate_id=gate_id,
            evaluated_at=_now(),
        )
        emit(
            "permission.evaluated",
            f"{req.action} → {decision}",
            actor="governance",
            risk=risk,
            status=EventStatus.WAITING_USER
            if decision == "require_approval"
            else EventStatus.COMPLETED,
            payload={"evaluator": "os_v1_fixture_gates", **evaluation.model_dump()},
        )
        return {"simulated": True, "evaluation": evaluation.model_dump()}

    # -- WebSocket -------------------------------------------------------------

    @app.websocket("/events")
    async def ws_events(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[OsEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(event: OsEvent) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        event_store.subscribe(on_event)
        try:
            for event in event_store.tail(50):
                await ws.send_text(event.model_dump_json())
            while True:
                event = await queue.get()
                await ws.send_text(event.model_dump_json())
        except WebSocketDisconnect:
            pass
        finally:
            event_store.unsubscribe(on_event)

    # -- Product OS (Fase 15): Integration Fabric + Business Core --------------
    register_product_routes(app, event_store, fixtures, business_core_path)

    return app


def serve(host: str = HOST, port: int = PORT) -> None:
    """Arranque bloqueante (usado por `atlas os-bridge`)."""
    import uvicorn  # noqa: PLC0415 — import perezoso, solo al servir

    uvicorn.run("atlas.api.server:app", host=host, port=port, log_level="info")


_app_singleton: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """`app` perezosa (PEP 562): uvicorn atlas.api.server:app funciona sin
    que importar el módulo cree el store en $ATLAS_HOME como efecto lateral."""
    if name == "app":
        global _app_singleton
        if _app_singleton is None:
            _app_singleton = create_app()
        return _app_singleton
    raise AttributeError(name)
