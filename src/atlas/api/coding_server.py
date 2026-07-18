"""Atlas Coding Bridge — adaptador OpenAI-compatible sobre el InferenceHub real.

Proceso SEPARADO del Atlas OS Bridge (127.0.0.1:7341, ADR-058), a propósito:
ese bridge es de solo lectura ("CERO Orchestrator en este proceso" — invariante
dura para no corromper Merkle). Este servicio SÍ hace llamadas reales a LLMs
(efecto de red, no de repo) y no debe compartir proceso con el bridge read-only.

No reimplementa un editor ni un chat: expone `/v1/chat/completions` y
`/v1/models` con la forma estándar OpenAI para que herramientas YA REALES y
probadas (Continue en VS Code, o cualquier cliente OpenAI-compatible) hablen
con Atlas usando su propio InferenceHub (roles chat/edit/apply, fallback
chain multi-proveedor) en vez de un backend inventado.

Arrancar:  atlas coding-bridge
       o:  uvicorn atlas.api.coding_server:app --host 127.0.0.1 --port 7342
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from starlette.responses import JSONResponse, StreamingResponse

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest

HOST = "127.0.0.1"
PORT = 7342

_hub_singleton: InferenceHub | None = None


def _hub() -> InferenceHub:
    global _hub_singleton
    if _hub_singleton is None:
        _hub_singleton = InferenceHub()
    return _hub_singleton


def _role_for_model(model: str) -> str:
    """El campo `model` del request OpenAI se reusa como selector de ROL
    (chat/edit/apply), no de proveedor: Atlas ya enruta por fallback chain
    real, no por nombre de modelo fijo. Ver comentario de diseño en
    Provider.roles (inference_hub.py) — patrón validado Continue/Cline/Cursor."""
    m = (model or "").lower()
    if "edit" in m:
        return "edit"
    if "apply" in m:
        return "apply"
    return "chat"


def create_app() -> FastAPI:
    app = FastAPI(title="Atlas Coding Bridge", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "atlas-coding-bridge", "real": True}

    @app.get("/v1/models")
    def list_models() -> dict[str, Any]:
        hub = _hub()
        seen: dict[str, dict[str, Any]] = {}
        for p in hub.providers_status():
            model_id = str(p.get("model_id") or p.get("name") or "")
            if not model_id or model_id in seen:
                continue
            seen[model_id] = {
                "id": model_id,
                "object": "model",
                "owned_by": p.get("name", "atlas"),
            }
        # Roles lógicos también expuestos como "modelos" seleccionables — el
        # cliente elige rol (chat/edit/apply), Atlas resuelve el proveedor real.
        for role in ("atlas-chat", "atlas-edit", "atlas-apply"):
            seen.setdefault(role, {"id": role, "object": "model", "owned_by": "atlas"})
        return {"object": "list", "data": list(seen.values())}

    @app.post("/v1/chat/completions")
    async def chat_completions(payload: dict[str, Any]) -> Any:
        messages = payload.get("messages")
        if not messages:
            raise HTTPException(400, "messages es requerido")
        model = str(payload.get("model", "atlas-chat"))
        role = _role_for_model(model)
        raw_temperature = payload.get("temperature")
        temperature = float(raw_temperature) if raw_temperature is not None else 0.1
        req = InferenceRequest(
            prompt="",
            messages=messages,
            level=InferenceLevel.L1,
            max_tokens=int(payload.get("max_tokens") or 2048),
            temperature=temperature,
            tools=payload.get("tools"),
            tool_choice=payload.get("tool_choice", "auto"),
        )
        hub = _hub()
        resp = hub.infer_for_role(role, req)
        if not resp.success:
            raise HTTPException(502, f"Atlas InferenceHub falló: {resp.error or 'sin detalle'}")

        created = int(time.time())
        completion_id = f"atlas-{uuid.uuid4().hex[:16]}"
        message: dict[str, Any] = {"role": "assistant", "content": resp.text}
        if resp.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", "{}"),
                    },
                }
                for tc in resp.tool_calls
            ]
        body: dict[str, Any] = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": resp.model or resp.provider,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": resp.finish_reason or ("tool_calls" if resp.tool_calls else "stop"),
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": resp.tokens_used,
                "total_tokens": resp.tokens_used,
            },
            # No estándar OpenAI, pero honesto: qué proveedor REAL respondió.
            "atlas_meta": {"provider": resp.provider, "mode": resp.mode, "latency_ms": resp.latency_ms},
        }

        if payload.get("stream"):
            # Streaming REAL token-a-token no implementado aún (InferenceHub
            # es síncrono, una llamada = una respuesta completa). Se entrega
            # como UN único chunk SSE — compatible con clientes que parsean
            # SSE, honesto sobre no ser incremental (ver README del módulo).
            chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": body["model"],
                "choices": [
                    {"index": 0, "delta": {"role": "assistant", "content": resp.text}, "finish_reason": None}
                ],
            }
            done = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": body["model"],
                "choices": [{"index": 0, "delta": {}, "finish_reason": body["choices"][0]["finish_reason"]}],
            }

            def gen() -> Any:
                import json as _json

                yield f"data: {_json.dumps(chunk)}\n\n"
                yield f"data: {_json.dumps(done)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(gen(), media_type="text/event-stream")

        return JSONResponse(body)

    return app


_app_singleton: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        global _app_singleton
        if _app_singleton is None:
            _app_singleton = create_app()
        return _app_singleton
    raise AttributeError(name)


def serve(host: str = HOST, port: int = PORT) -> None:
    """Arranque bloqueante (usado por `atlas coding-bridge`)."""
    import uvicorn  # noqa: PLC0415 — import perezoso, solo al servir

    uvicorn.run("atlas.api.coding_server:app", host=host, port=port, log_level="info")
