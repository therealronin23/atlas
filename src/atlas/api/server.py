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
import hashlib
import hmac
import ipaddress
import json
import os
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response

from atlas.api.missions import (
    ecosystem_drift_mission,
    ecosystem_drift_receipt,
    mission_receipt,
    missions_payload,
    proposal_to_mission,
    radar_findings,
)
from atlas.api.models import (
    ConnectorSpec,
    EvaluateRequest,
    GateSpec,
    IntentRequest,
    PermissionEvaluation,
    SimulateRequest,
)
from atlas.api.product_routes import register_product_routes
from atlas.core.self_maintenance.ecosystem_drift import ecosystem_map_drift
from atlas.events.player import EventPlayer
from atlas.events.schemas import Causality, EventStatus, OsEvent, Risk
from atlas.events.store import OsEventStore
from atlas.runtime_paths import atlas_data_root

HOST = "127.0.0.1"
PORT = 7341
AUTH_TOKEN_ENV = "ATLAS_OS_BRIDGE_TOKEN"
_MIN_AUTH_TOKEN_BYTES = 32

_REPO_ROOT = atlas_data_root()
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


class _AuthenticationError(Exception):
    """Credencial o contexto de red no admitido por el bridge."""


def _is_loopback_host(host: str | None) -> bool:
    """Comprueba loopback sin resolver DNS ni confiar en cabeceras proxy."""
    if host is None:
        return False
    candidate = host.strip().removeprefix("[").removesuffix("]")
    if candidate.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _configured_strong_token() -> str | None:
    token = os.environ.get(AUTH_TOKEN_ENV, "")
    if len(token.encode("utf-8")) < _MIN_AUTH_TOKEN_BYTES:
        return None
    return token


def _tokens_equal(left: str, right: str) -> bool:
    """Comparación constante también para entradas Unicode hostiles."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _validate_bind_security(host: str) -> None:
    """Impide exponer el bridge fuera de loopback sin secreto fuerte."""
    if not _is_loopback_host(host) and _configured_strong_token() is None:
        raise RuntimeError(
            f"{AUTH_TOKEN_ENV} debe contener al menos "
            f"{_MIN_AUTH_TOKEN_BYTES} bytes para escuchar fuera de loopback"
        )


def _presented_token(headers: Headers) -> str | None:
    authorization = headers.get("authorization")
    bearer: str | None = None
    if authorization is not None:
        scheme, separator, value = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not separator or not value.strip():
            raise _AuthenticationError
        bearer = value.strip()

    x_token = headers.get("x-atlas-token")
    if x_token is not None:
        x_token = x_token.strip()
        if not x_token:
            raise _AuthenticationError
    if bearer is not None and x_token is not None:
        if not _tokens_equal(bearer, x_token):
            raise _AuthenticationError
    return bearer or x_token


def _credential_identity(token: str) -> str:
    """Identidad auditable opaca: deriva de la credencial, no la revela."""
    fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"atlas-token:{fingerprint}"


def _authenticate_client(client_host: str | None, headers: Headers) -> str:
    presented = _presented_token(headers)
    if presented is not None:
        configured = _configured_strong_token()
        if configured is None or not _tokens_equal(presented, configured):
            raise _AuthenticationError
        return _credential_identity(configured)
    if _is_loopback_host(client_host):
        return f"atlas-loopback:{client_host}"
    raise _AuthenticationError


def _authority_hostname(authority: str | None) -> str | None:
    if not authority or any(char.isspace() for char in authority):
        return None
    try:
        parsed = urlsplit(f"//{authority}")
        # Acceder a .port fuerza la validación de puertos no numéricos/rango.
        _ = parsed.port
        if (
            parsed.username is not None
            or parsed.password is not None
            or bool(parsed.path)
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            return None
        return parsed.hostname
    except ValueError:
        return None


def _validate_loopback_http_host(
    client_host: str | None, headers: Headers, identity: str,
) -> None:
    """Cierra DNS rebinding cuando loopback opera sin una credencial."""
    if not identity.startswith("atlas-loopback:"):
        return
    host = _authority_hostname(headers.get("host"))
    if not _is_loopback_host(client_host) or not _is_loopback_host(host):
        raise _AuthenticationError


def _validate_websocket_origin(client_host: str | None, headers: Headers) -> None:
    host = _authority_hostname(headers.get("host"))
    origin_value = headers.get("origin")
    if host is None or origin_value is None:
        raise _AuthenticationError
    try:
        origin = urlsplit(origin_value)
    except ValueError as exc:
        raise _AuthenticationError from exc
    try:
        origin_host = origin.hostname
        _ = origin.port
    except ValueError as exc:
        raise _AuthenticationError from exc
    if (
        origin.scheme not in {"http", "https"}
        or origin_host is None
        or origin.username is not None
        or origin.password is not None
        or origin.path not in {"", "/"}
        or bool(origin.query)
        or bool(origin.fragment)
    ):
        raise _AuthenticationError

    client_is_loopback = _is_loopback_host(client_host)
    host_is_loopback = _is_loopback_host(host)
    if client_is_loopback != host_is_loopback:
        raise _AuthenticationError
    same_endpoint = host.casefold() == origin_host.casefold()
    if not same_endpoint and not (
        host_is_loopback and _is_loopback_host(origin_host)
    ):
        raise _AuthenticationError


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


def _self_build_summary(limit: int = 50) -> dict[str, Any]:
    """Lectura READ-ONLY del ledger de ColdUpdateManager (ADR-025). Jamás
    instancia ColdUpdateManager aquí: su __init__ barre worktrees huérfanos
    (efecto lateral de escritura) — solo se lee `proposals.json` del disco,
    igual que `_memory_summary` lee sqlite sin instanciar el índice pesado."""
    path = _REPO_ROOT.parent / "atlas-cold-updates" / "proposals.json"
    if not path.exists():
        return {"real": False, "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "detail": f"no existe {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"real": False, "status": "UNVERIFIED", "detail": str(exc)}

    proposals: list[dict[str, Any]] = data.get("proposals", [])
    by_status: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for p in proposals:
        by_status[p.get("status", "unknown")] = by_status.get(p.get("status", "unknown"), 0) + 1
        by_origin[p.get("origin", "unknown")] = by_origin.get(p.get("origin", "unknown"), 0) + 1
        by_risk[p.get("risk", "unknown")] = by_risk.get(p.get("risk", "unknown"), 0) + 1

    recent = sorted(proposals, key=lambda p: p.get("created_at", ""), reverse=True)[:limit]
    recent_slim = [
        {
            "id": p.get("id"),
            "intent": p.get("intent"),
            "status": p.get("status"),
            "origin": p.get("origin"),
            "risk": p.get("risk"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        }
        for p in recent
    ]
    return {
        "real": True,
        "total": len(proposals),
        "by_status": by_status,
        "by_origin": by_origin,
        "by_risk": by_risk,
        "recent": recent_slim,
    }


_NEXT_ACTION_BY_STATUS: dict[str, str] = {
    "proposed": "atlas update validate {id}",
    "validated": "atlas update approve {id}",
    "approved": "atlas update apply {id}",
}


def _next_action_hint(status: str, proposal_id: str) -> str | None:
    """Comando CLI real que un humano correría a continuación — nunca se
    ejecuta desde el bridge (ADR-058 es read-only), solo se muestra."""
    template = _NEXT_ACTION_BY_STATUS.get(status)
    return template.format(id=proposal_id) if template else None


def _files_touched_from_patch(patch_text: str) -> list[str]:
    """Extrae rutas tocadas de un diff unificado (cabeceras ---/+++)."""
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            path = line[4:].strip()
            if path == "/dev/null":
                continue
            if path.startswith(("a/", "b/")):
                path = path[2:]
            if path not in files:
                files.append(path)
    return files


def _load_proposals() -> list[dict[str, Any]] | dict[str, Any]:
    """Carga READ-ONLY del ledger de ColdUpdate; si no se puede, devuelve el
    payload de error ({real: False, …}) para que el endpoint lo retorne tal
    cual. Mismo patrón honesto que _self_build_summary."""
    path = _REPO_ROOT.parent / "atlas-cold-updates" / "proposals.json"
    if not path.exists():
        return {"real": False, "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "detail": f"no existe {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"real": False, "status": "UNVERIFIED", "detail": str(exc)}
    proposals: list[dict[str, Any]] = data.get("proposals", [])
    return proposals


def _proposal_files_touched(proposal: dict[str, Any]) -> list[str]:
    """Ficheros tocados por el patch real de una propuesta (si existe)."""
    patch_path = proposal.get("patch_path")
    if not patch_path:
        return []
    patch_file = Path(patch_path)
    if not patch_file.exists():
        return []
    try:
        return _files_touched_from_patch(
            patch_file.read_text(encoding="utf-8", errors="replace")
        )
    except OSError:
        return []


def _self_build_proposal_detail(proposal_id: str) -> dict[str, Any]:
    """Lectura READ-ONLY de una propuesta concreta del ledger de
    ColdUpdateManager, con el diff parseado a ficheros tocados — mismo
    patrón de no-instanciar-la-clase que `_self_build_summary`."""
    path = _REPO_ROOT.parent / "atlas-cold-updates" / "proposals.json"
    if not path.exists():
        return {"real": False, "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "detail": f"no existe {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"real": False, "status": "UNVERIFIED", "detail": str(exc)}

    proposals: list[dict[str, Any]] = data.get("proposals", [])
    proposal = next((p for p in proposals if p.get("id") == proposal_id), None)
    if proposal is None:
        return {"real": False, "status": "NOT_FOUND",
                "detail": f"sin propuesta con id={proposal_id}"}

    patch_path = proposal.get("patch_path")
    files_touched: list[str] = []
    patch_available = False
    if patch_path:
        patch_file = Path(patch_path)
        if patch_file.exists():
            try:
                files_touched = _files_touched_from_patch(
                    patch_file.read_text(encoding="utf-8", errors="replace")
                )
                patch_available = True
            except OSError:
                pass

    return {
        "real": True,
        "id": proposal.get("id"),
        "intent": proposal.get("intent"),
        "status": proposal.get("status"),
        "origin": proposal.get("origin"),
        "risk": proposal.get("risk"),
        "base_ref": proposal.get("base_ref"),
        "created_at": proposal.get("created_at"),
        "updated_at": proposal.get("updated_at"),
        "evidence": proposal.get("evidence"),
        "validation": proposal.get("validation"),
        "files_touched": files_touched,
        "patch_available": patch_available,
        "next_action": _next_action_hint(proposal.get("status", ""), proposal.get("id", "")),
    }


def create_app(
    store: OsEventStore | None = None,
    fixtures_dir: Path | None = None,
    business_core_path: Path | None = None,
    repo_root: Path | None = None,
) -> FastAPI:
    fixtures = fixtures_dir or _FIXTURES
    mission_repo_root = repo_root or _REPO_ROOT
    event_store = store or OsEventStore()
    player = EventPlayer(event_store)
    connectors = _load_connectors(fixtures / "connectors")
    gates = _load_gates(fixtures / "governance" / "gates.json")

    app = FastAPI(title="Atlas OS Bridge", docs_url=None, redoc_url=None,
                  openapi_url=None)

    @app.middleware("http")
    async def authenticate_http(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = request.client.host if request.client is not None else None
        try:
            identity = _authenticate_client(client_host, request.headers)
            _validate_loopback_http_host(client_host, request.headers, identity)
        except _AuthenticationError:
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        request.state.auth_identity = identity
        return await call_next(request)

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

    @app.get("/self-build/summary")
    def self_build_summary(limit: int = 50) -> dict[str, Any]:
        return _self_build_summary(limit=limit)

    @app.get("/self-build/proposal/{proposal_id}")
    def self_build_proposal(proposal_id: str) -> dict[str, Any]:
        return _self_build_proposal_detail(proposal_id)

    # -- Mission Layer v0 (Foundry, ADR-069) -------------------------------
    # Proyección read-only del ledger de ColdUpdate como misiones. Mismo
    # patrón que /self-build/*: leer proposals.json, jamás instanciar
    # ColdUpdateManager. /missions/radar va ANTES de /missions/{id} para
    # que el path param no capture "radar".

    @app.get("/missions/radar")
    def missions_radar() -> dict[str, Any]:
        proposals = _load_proposals()
        if isinstance(proposals, dict):  # error payload
            return proposals
        # T1.3: ecosystem_map_drift es puro/read-only (nunca lanza, nunca
        # red) — igual de seguro leerlo aquí que leer proposals.json.
        drift = ecosystem_map_drift(mission_repo_root)
        return {"real": True, "findings": radar_findings(proposals, drift=drift)}

    @app.get("/missions/{mission_id}")
    def mission_detail(mission_id: str) -> dict[str, Any]:
        proposals = _load_proposals()
        if isinstance(proposals, dict):
            return proposals
        # T1.3: la misión draft de ecosystem_drift no vive en proposals.json
        # (no es un ColdUpdateProposal real) — se recalcula igual que en
        # /missions y se compara por mission_id antes de caer al ledger.
        drift = ecosystem_map_drift(mission_repo_root)
        drift_mission = ecosystem_drift_mission(drift)
        if drift_mission is not None and drift_mission["mission_id"] == mission_id:
            return {
                "real": True,
                "mission": drift_mission,
                "receipt": ecosystem_drift_receipt(drift_mission),
            }
        proposal_id = mission_id.removeprefix("msn_")
        proposal = next(
            (p for p in proposals if p.get("id") == proposal_id), None
        )
        if proposal is None:
            return {"real": False, "status": "NOT_FOUND",
                    "detail": f"sin misión con id={mission_id}"}
        files = _proposal_files_touched(proposal)
        return {
            "real": True,
            "mission": proposal_to_mission(proposal, files_touched=files),
            "receipt": mission_receipt(proposal, files_touched=files),
        }

    @app.get("/missions")
    def missions_list(limit: int = 50) -> dict[str, Any]:
        proposals = _load_proposals()
        if isinstance(proposals, dict):
            return proposals
        # T1.3: hallazgos de ecosystem_drift generan misiones draft NUEVAS
        # (no derivadas de ningún proposal existente) — mismo seam de
        # misión/next_action-humano, nunca auto-aprobadas.
        drift = ecosystem_map_drift(mission_repo_root)
        extra_missions = []
        drift_mission = ecosystem_drift_mission(drift)
        if drift_mission is not None:
            extra_missions.append(drift_mission)
        return missions_payload(proposals, limit=limit, extra_missions=extra_missions)

    @app.post("/memory/import")
    def memory_import(raw: dict[str, Any]) -> dict[str, Any]:
        """Import REAL (Fase 8): preserva raw, extrae por reglas, emite eventos."""
        from atlas.api.conversation_import import import_conversation

        try:
            result = import_conversation(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        client_host = ws.client.host if ws.client is not None else None
        try:
            identity = _authenticate_client(client_host, ws.headers)
            _validate_websocket_origin(client_host, ws.headers)
        except _AuthenticationError:
            await ws.close(code=1008)
            return
        ws.state.auth_identity = identity
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
    _validate_bind_security(host)
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
