"""Atlas Core — Dashboard web local (Gate E/E2).

FastAPI + Jinja2, puerto 7331, solo localhost.
Auto-refresca cada 30s via meta tag.
Sin dependencias nuevas: fastapi, jinja2, uvicorn ya en pyproject.toml.

Arrancar con:  atlas dashboard
           o:  uvicorn atlas.interfaces.dashboard:app --host 127.0.0.1 --port 7331
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from collections import deque
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from atlas.core.inference_hub import DEFAULT_PROVIDERS
from atlas.core.orchestrator import Orchestrator
from atlas.interfaces.hermes_webhook import HermesWebhookHandler
from atlas.memory.memory_system import (
    ApprovedPatternStore,
    ErrorRegistry,
    ProviderMetricsStore,
    SystemContextLoader,
)

_log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
PORT = 7331
DASHBOARD_TOKEN_ENV = "ATLAS_DASHBOARD_TOKEN"
_INDEPENDENTLY_AUTHENTICATED_POSTS = {
    "/api/exec/health",
    "/api/exec/shell",
    "/api/exec/file",
    "/api/exec/intent",
    "/api/exec/audit",
    "/api/exec/browser",
    "/api/hermes/webhook",
}

app = FastAPI(
    title="Atlas Dashboard",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _is_loopback_host(value: str) -> bool:
    host = value.strip().lower()
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_bind_security(host: str) -> None:
    """Refuse a network-visible dashboard unless a strong token is configured."""
    if _is_loopback_host(host):
        return
    token = os.environ.get(DASHBOARD_TOKEN_ENV, "")
    if len(token) < 32:
        raise RuntimeError(
            f"non-loopback dashboard bind requires {DASHBOARD_TOKEN_ENV} "
            "with at least 32 characters"
        )


@app.middleware("http")
async def _dashboard_access_control(request: Request, call_next: Any) -> Any:
    """Keep local UI convenient while authenticating every remote read route."""
    if (
        request.method == "POST"
        and request.url.path in _INDEPENDENTLY_AUTHENTICATED_POSTS
    ):
        return await call_next(request)

    client_host = request.client.host if request.client is not None else ""
    request_host = request.headers.get("host", "")
    if _is_loopback_host(client_host) and _is_loopback_host(request_host):
        return await call_next(request)

    expected = os.environ.get(DASHBOARD_TOKEN_ENV, "")
    authorization = request.headers.get("authorization", "")
    supplied = (
        authorization[7:].strip()
        if authorization.lower().startswith("bearer ")
        else request.headers.get("x-atlas-dashboard-token", "").strip()
    )
    if len(expected) >= 32 and secrets.compare_digest(supplied, expected):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "authentication required"})

# ---------------------------------------------------------------------------
# Singleton Orchestrator (lazy, one per process)
# ---------------------------------------------------------------------------

_orch: Orchestrator | None = None


def set_orchestrator(orch: Orchestrator) -> None:
    """Inject an externally-managed Orchestrator (used by AtlasServiceRunner).

    Avoids the double-Orchestrator bug where the dashboard would otherwise
    create its own instance and corrupt the Merkle chain by writing to the
    same log file from a separate threading.Lock().

    Also wires the Hermes webhook handler against the injected bus, so the
    wiring no longer triggers eagerly at module import (which would spawn
    a second Orchestrator before injection had a chance to run).
    """
    global _orch
    _orch = orch
    _wire_hermes_webhook(orch)
    _wire_exec_api(orch)
    _wire_agentic_progress(orch)


def _get_orch() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
        # Best-effort wiring for the standalone `atlas dashboard` case where
        # there is no service_runner to call set_orchestrator first.
        _wire_hermes_webhook(_orch)
        _wire_exec_api(_orch)
        _wire_agentic_progress(_orch)
    return _orch


# ---------------------------------------------------------------------------
# ADR-033 #4 — feed en memoria de progreso del loop agéntico
# ---------------------------------------------------------------------------

# Ring buffer de las últimas trazas AGENTIC_PROGRESS, alimentado por el EventBus.
# Vive solo en este proceso (igual que el dashboard); se expone vía API JSON
# para que el front lo pinte sin tocar la cadena Merkle.
_progress_feed: deque[dict[str, Any]] = deque(maxlen=50)
_progress_wired = False


def _wire_agentic_progress(orch: Orchestrator) -> None:
    global _progress_wired
    if _progress_wired:
        return

    def _on_progress(event: Any) -> None:
        p = getattr(event, "payload", {}) or {}
        _progress_feed.appendleft({
            "task_id": p.get("task_id"),
            "iteration": p.get("iteration"),
            "tool": p.get("tool"),
            "summary": p.get("summary"),
            "timestamp": getattr(event, "timestamp", None),
        })

    from atlas.core.contracts import EventType  # noqa: PLC0415
    orch._bus.subscribe(EventType.AGENTIC_PROGRESS, _on_progress)
    _progress_wired = True


def _workspace() -> Path:
    env = os.environ.get("ATLAS_HOME")
    return Path(env).expanduser().resolve() if env else Path.home() / "atlas"


# ---------------------------------------------------------------------------
# System metrics (sin psutil: lee /proc y /sys igual que ThermalWatchdog)
# ---------------------------------------------------------------------------

def _read_ram_free_mb() -> int:
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return -1


def _read_temp_c() -> float:
    hwmon = Path("/sys/class/hwmon")
    if not hwmon.exists():
        return 0.0
    for sensor_dir in sorted(hwmon.iterdir()):
        for temp_file in sorted(sensor_dir.glob("temp*_input")):
            try:
                raw = int(temp_file.read_text().strip())
                val = raw / 1000.0
                if 20.0 < val < 120.0:
                    return val
            except Exception:
                continue
    return 0.0


def _thermal_data() -> dict[str, Any]:
    temp = _read_temp_c()
    ram = _read_ram_free_mb()
    if temp >= 80.0 or (0 < ram < 1024):
        mode = "DEGRADED"
    else:
        mode = "NORMAL"
    return {"temp_c": temp, "ram_free_mb": ram, "mode": mode}


# ---------------------------------------------------------------------------
# Memory stats (reads workspace files directly)
# ---------------------------------------------------------------------------

def _memory_stats() -> dict[str, Any]:
    ws = _workspace()
    ctx = SystemContextLoader.load(ws / "memory" / "system_context")
    has_context = bool(ctx.vision or ctx.rules or ctx.adr)

    err_reg = ErrorRegistry(ws / "memory" / "error_registry")
    errors = err_reg.all()

    pat_store = ApprovedPatternStore(ws / "memory" / "approved_patterns")
    patterns = pat_store.all()

    perf = ProviderMetricsStore(ws / "memory" / "performance")
    perf_path = ws / "memory" / "performance" / "performance.jsonl"
    perf_count = 0
    if perf_path.exists():
        try:
            perf_count = sum(1 for _ in perf_path.open())
        except Exception:
            pass

    context_data: dict[str, str] = {}
    if has_context:
        if ctx.vision:
            # first non-empty line as preview
            first = next((l for l in ctx.vision.splitlines() if l.strip()), "")
            context_data["vision"] = first
        if ctx.rules:
            first = next((l for l in ctx.rules.splitlines() if l.strip()), "")
            context_data["rules"] = first
        if ctx.adr:
            first = next((l for l in ctx.adr.splitlines() if l.strip()), "")
            context_data["adr"] = first

    return {
        "context_loaded": has_context,
        "context_sections": sum([bool(ctx.vision), bool(ctx.rules), bool(ctx.adr)]),
        "error_count": len(errors),
        "pattern_count": len(patterns),
        "kuzu_active": False,   # se activa si KuzuVectorStore está instanciado
        "kuzu_patterns": 0,
        "kuzu_failures": 0,
        "kuzu_evidence": 0,
        "perf_samples": perf_count,
        "context_data": context_data,
    }


# ---------------------------------------------------------------------------
# Provider stats
# ---------------------------------------------------------------------------

def _provider_data() -> list[dict[str, Any]]:
    ws = _workspace()
    perf = ProviderMetricsStore(ws / "memory" / "performance")
    result = []
    for p in DEFAULT_PROVIDERS:
        env_key = p.api_key_env
        has_key = bool(env_key and os.environ.get(env_key))
        stats = perf.get_stats(p.name) if p.api_key_env else {"count": 0}
        result.append({
            "name": p.name,
            "model": p.model_id,
            "context_tokens": p.context_tokens,
            "has_key": has_key,
            "stats": stats,
        })
    return result


# ---------------------------------------------------------------------------
# Task filter from audit log
# ---------------------------------------------------------------------------

def _extract_tasks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filtra y enriquece registros del Merkle log que representan tareas."""
    tasks = []
    for r in records:
        action = r.get("action", "")
        payload = r.get("payload", {})
        if action in ("task.received", "task.completed", "task.blocked",
                      "intent.classified", "intent.executed"):
            intent = payload.get("intent", payload.get("task_intent", ""))
            route = payload.get("route", payload.get("classification", ""))
            tasks.append({
                "timestamp": r.get("timestamp", ""),
                "intent": intent or action,
                "route": route,
                "result": r.get("result", ""),
                "risk_level": r.get("risk_level", ""),
            })
    return tasks


# ---------------------------------------------------------------------------
# Hermes Webhook (cableado opcional, solo si HERMES_API_KEY está configurada)
# ---------------------------------------------------------------------------

_hermes_api_key = os.environ.get("HERMES_API_KEY") or ""
_webhook_handler: HermesWebhookHandler | None = None
_webhook_wired = False
_exec_api_wired = False


def _wire_exec_api(orch: Orchestrator) -> None:
    """ADR-027: mount /api/exec/* routes for Hermes-driven capability execution.

    Idempotent. Only mounts if HERMES_API_KEY is present (the routes themselves
    also check, returning 503 if it's later removed at runtime).
    """
    global _exec_api_wired
    if _exec_api_wired or not _hermes_api_key:
        return
    try:
        from atlas.interfaces.exec_api import build_router
        # Pass _get_orch as the provider so the router resolves the orchestrator
        # lazily on each request — survives orchestrator swaps in tests.
        app.include_router(build_router(_get_orch))
        _exec_api_wired = True
        _log.info("Exec API cableado en /api/exec/* (ADR-027)")
    except Exception as exc:
        _log.warning(f"No se pudo cablear exec_api: {exc}")


def _wire_hermes_webhook(orch: Orchestrator) -> None:
    """Lazy: cable Hermes webhook against an existing Orchestrator's bus.

    Called from `set_orchestrator()` (preferred) or from the first `_get_orch()`
    that happens to lazy-init. Idempotent.
    """
    global _webhook_handler, _webhook_wired
    if _webhook_wired or not _hermes_api_key:
        return
    try:
        _webhook_handler = HermesWebhookHandler(
            orch._bus,
            hmac_key=_hermes_api_key,
        )
        app.include_router(_webhook_handler.router)
        _webhook_wired = True
        _log.info("Hermes webhook handler cableado en /api/hermes/webhook")
    except Exception as exc:
        _log.warning(f"No se pudo cablear Hermes webhook: {exc}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def status_page(request: Request) -> HTMLResponse:
    orch = _get_orch()
    status = orch.status()
    thermal = _thermal_data()
    audit = orch.audit_tail(8)
    gate_d = getattr(orch, "_gate_d_enabled", False)
    return _templates.TemplateResponse(
        request,
        "status.html",
        {
            "page": "status",
            "status": status,
            "thermal": thermal,
            "audit_tail": audit,
            "gate_d": gate_d,
        },
    )


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request) -> HTMLResponse:
    orch = _get_orch()
    all_records = orch.audit_tail(100)
    tasks = _extract_tasks(all_records)
    return _templates.TemplateResponse(
        request,
        "tasks.html",
        {"page": "tasks", "tasks": tasks},
    )


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> HTMLResponse:
    orch = _get_orch()
    records = orch.audit_tail(50)
    chain_ok, chain_msg = orch._merkle.verify_chain()
    total = orch.status().record_count
    return _templates.TemplateResponse(
        request,
        "audit.html",
        {
            "page": "audit",
            "records": records,
            "chain_ok": chain_ok,
            "chain_msg": chain_msg,
            "total": total,
        },
    )


@app.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request) -> HTMLResponse:
    mem = _memory_stats()
    return _templates.TemplateResponse(
        request,
        "memory.html",
        {"page": "memory", "mem": mem},
    )


@app.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request) -> HTMLResponse:
    orch = _get_orch()
    tools = orch.tools()
    return _templates.TemplateResponse(
        request,
        "tools.html",
        {"page": "tools", "tools": tools},
    )


@app.get("/providers", response_class=HTMLResponse)
async def providers_page(request: Request) -> HTMLResponse:
    providers = _provider_data()
    return _templates.TemplateResponse(
        request,
        "providers.html",
        {"page": "providers", "providers": providers},
    )


# ---------------------------------------------------------------------------
# JSON API (útil para scripts y futuros widgets)
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    orch = _get_orch()
    st = orch.status()
    thermal = _thermal_data()
    return {
        "version": st.version,
        "governance_ok": st.governance_ok,
        "chain_ok": st.chain_ok,
        "record_count": st.record_count,
        "tool_count": st.tool_count,
        "hermes_mode": st.hermes_mode,
        "queue_depth": st.queue_depth,
        "uptime_seconds": st.uptime_seconds,
        "emergency_mode": st.emergency_mode,
        "temp_c": thermal["temp_c"],
        "ram_free_mb": thermal["ram_free_mb"],
        "operational_mode": thermal["mode"],
    }


@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    """Health JSON para Gate I (localhost/Tailscale only)."""
    return _get_orch().health_report()


@app.get("/api/observability")
async def api_observability() -> dict[str, Any]:
    """ADR-024 telemetry + microledger + WAL snapshot."""
    return dict(_get_orch()._observability.snapshot())


@app.get("/observability", response_class=HTMLResponse)
async def observability_page(request: Request) -> HTMLResponse:
    snap = _get_orch()._observability.snapshot()
    return _templates.TemplateResponse(
        request,
        "observability.html",
        {"page": "observability", "snapshot": snap},
    )


@app.get("/api/providers")
async def api_providers() -> list[dict[str, Any]]:
    return _provider_data()


@app.get("/api/agentic/progress")
async def api_agentic_progress() -> list[dict[str, Any]]:
    """ADR-033 #4: últimas trazas de progreso del loop agéntico (más reciente
    primero). Vacío si no se ha emitido ninguna en este proceso."""
    _get_orch()  # asegura que el feed está cableado al bus
    return list(_progress_feed)


# ---------------------------------------------------------------------------
# Entry point for direct run
# ---------------------------------------------------------------------------

def serve(host: str = "127.0.0.1", port: int = PORT) -> None:
    """Arranca el dashboard con uvicorn. Llamar desde CLI."""
    _validate_bind_security(host)
    import uvicorn  # noqa: PLC0415 — import tardío para no penalizar import
    uvicorn.run(app, host=host, port=port, log_level="warning")
