"""
Atlas ACP Agent Server — absorbido de Hermes-Agent (2026-07-18).

Expone Atlas como agente invocable por cualquier cliente del Agent Client
Protocol (Zed lo habla nativamente — encaja directo con la ola T2.1 del
Atlas IDE; Void/Continue no lo hablan hoy). NO porta el bucle agéntico de
Hermes (edit-approval, session-fork, slash commands, MCP registration —
~5000 líneas) — eso queda fuera a propósito, tal como marca
absorption_master_plan.md: "interesting less as a tool to absorb and more
as a possible protocol". Este es un adaptador FINO sobre el SDK oficial
(`agent-client-protocol` en PyPI, import `acp`) que reutiliza el
`InferenceHub` YA construido y probado (mismo camino que
`atlas.api.coding_server`, forma ACP en vez de forma OpenAI).

Límite honesto v1 (documentado, no fingido resuelto):
  - Streaming: UN chunk por respuesta (InferenceHub es síncrono, no
    token-a-token) — mismo límite ya documentado en coding_server.py.
  - Sin tool-calling/edit-approval todavía — solo chat de texto.
  - `cancel()` no interrumpe una llamada de InferenceHub en curso (síncrona,
    no cancelable de verdad en este slice) — se registra pero no aborta.
  - Sin persistencia de sesión entre reinicios del proceso.

Arrancar:  python -m atlas.acp.server
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest


@dataclass
class _SessionState:
    session_id: str
    cwd: str
    history: list[dict[str, str]] = field(default_factory=list)


def _extract_text(prompt: list[Any]) -> str:
    """Concatena los bloques de texto de un prompt ACP (ignora imagen/audio/
    recurso en este slice — solo chat de texto)."""
    parts: list[str] = []
    for block in prompt:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


class AtlasACPAgent:
    """Agente ACP mínimo real: initialize/new_session/prompt sobre InferenceHub.

    Hereda de `acp.Agent` en tiempo de import (import perezoso — el paquete
    `agent-client-protocol` solo se necesita para arrancar el server real,
    no para importar el resto de Atlas)."""

    def __init__(self, hub: InferenceHub | None = None) -> None:
        self._hub = hub if hub is not None else InferenceHub()
        self._sessions: dict[str, _SessionState] = {}
        self._conn: Any = None

    def on_connect(self, conn: Any) -> None:
        self._conn = conn

    async def initialize(
        self, protocol_version: int, client_capabilities: Any = None,
        client_info: Any = None, **kwargs: Any,
    ) -> Any:
        from acp import schema  # noqa: PLC0415 — import perezoso, solo al servir

        return schema.InitializeResponse(
            protocol_version=protocol_version,
            agent_capabilities=schema.AgentCapabilities(
                prompt_capabilities=schema.PromptCapabilities(
                    image=False, audio=False, embedded_context=False,
                ),
            ),
            agent_info=schema.Implementation(name="atlas", version="0.1.0"),
        )

    async def new_session(
        self, cwd: str, additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None, **kwargs: Any,
    ) -> Any:
        from acp import schema  # noqa: PLC0415

        session_id = uuid.uuid4().hex
        self._sessions[session_id] = _SessionState(session_id=session_id, cwd=cwd)
        return schema.NewSessionResponse(session_id=session_id)

    async def authenticate(self, method_id: str, **kwargs: Any) -> Any:
        return None  # servidor local de confianza — sin auth en v1

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        # Límite honesto: InferenceHub.infer() es síncrono, no hay una
        # llamada en curso que abortar de verdad en este slice.
        return None

    async def prompt(
        self, session_id: str, prompt: list[Any], **kwargs: Any,
    ) -> Any:
        from acp import schema  # noqa: PLC0415

        state = self._sessions.get(session_id)
        if state is None:
            return schema.PromptResponse(stop_reason="refusal")

        user_text = _extract_text(prompt).strip()
        if not user_text:
            return schema.PromptResponse(stop_reason="end_turn")

        state.history.append({"role": "user", "content": user_text})
        req = InferenceRequest(
            prompt="", messages=state.history, level=InferenceLevel.L1, max_tokens=2048,
        )
        resp = self._hub.infer_for_role("chat", req)
        if not resp.success:
            reply = f"[Atlas InferenceHub falló: {resp.error or 'sin detalle'}]"
        else:
            reply = resp.text
            state.history.append({"role": "assistant", "content": reply})

        if self._conn is not None:
            await self._conn.session_update(
                session_id,
                schema.AgentMessageChunk(
                    session_update="agent_message_chunk",
                    content=schema.TextContentBlock(type="text", text=reply),
                ),
            )
        return schema.PromptResponse(stop_reason="end_turn")


def make_agent_class() -> type:
    """Construye la clase real `acp.Agent`-heredada en tiempo de arranque
    (no en tiempo de import de este módulo, para que `atlas.acp.server` sea
    importable sin tener `agent-client-protocol` instalado)."""
    import acp  # noqa: PLC0415

    class _BoundAtlasACPAgent(AtlasACPAgent, acp.Agent):
        pass

    return _BoundAtlasACPAgent


def serve() -> None:
    """Arranque bloqueante: Atlas como servidor ACP sobre stdio."""
    import asyncio  # noqa: PLC0415
    import acp  # noqa: PLC0415

    agent_cls = make_agent_class()
    asyncio.run(acp.run_agent(agent_cls()))


if __name__ == "__main__":
    serve()
