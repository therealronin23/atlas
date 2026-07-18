"""
Tests del Atlas ACP Agent Server (absorbido de Hermes-Agent, 2026-07-18).

InferenceHub mockeado (nunca una llamada real a proveedores). AtlasACPAgent
se instancia directamente (sin heredar acp.Agent) — solo necesita el paquete
`agent-client-protocol` para los tipos de schema en las respuestas, no para
el transporte stdio real.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from atlas.acp.server import AtlasACPAgent, _extract_text
from atlas.core.inference_hub import InferenceResponse


@dataclass
class _FakeTextBlock:
    text: str


class TestExtractText:
    def test_joins_text_blocks(self) -> None:
        blocks = [_FakeTextBlock("hola"), _FakeTextBlock("mundo")]
        assert _extract_text(blocks) == "hola\nmundo"

    def test_ignores_blocks_without_text_attribute(self) -> None:
        class _ImageBlock:
            pass

        blocks = [_FakeTextBlock("hola"), _ImageBlock()]
        assert _extract_text(blocks) == "hola"

    def test_empty_list_returns_empty_string(self) -> None:
        assert _extract_text([]) == ""


class TestInitialize:
    async def test_returns_protocol_version_and_capabilities(self) -> None:
        agent = AtlasACPAgent(hub=MagicMock())
        result = await agent.initialize(protocol_version=1)
        assert result.protocol_version == 1
        assert result.agent_info.name == "atlas"


class TestNewSession:
    async def test_creates_a_session_with_real_uuid(self) -> None:
        agent = AtlasACPAgent(hub=MagicMock())
        result = await agent.new_session(cwd="/tmp")
        assert result.session_id in agent._sessions
        assert agent._sessions[result.session_id].cwd == "/tmp"

    async def test_two_sessions_get_different_ids(self) -> None:
        agent = AtlasACPAgent(hub=MagicMock())
        a = await agent.new_session(cwd="/tmp")
        b = await agent.new_session(cwd="/tmp")
        assert a.session_id != b.session_id


class TestPrompt:
    async def test_unknown_session_returns_refusal(self) -> None:
        agent = AtlasACPAgent(hub=MagicMock())
        result = await agent.prompt(session_id="no-existe", prompt=[_FakeTextBlock("hola")])
        assert result.stop_reason == "refusal"

    async def test_empty_prompt_returns_end_turn_without_calling_hub(self) -> None:
        hub = MagicMock()
        agent = AtlasACPAgent(hub=hub)
        session = await agent.new_session(cwd="/tmp")
        result = await agent.prompt(session_id=session.session_id, prompt=[])
        assert result.stop_reason == "end_turn"
        hub.infer_for_role.assert_not_called()

    async def test_real_reply_calls_hub_with_chat_role_and_appends_history(self) -> None:
        from atlas.core.inference_hub import InferenceLevel

        hub = MagicMock()
        hub.infer_for_role.return_value = InferenceResponse(
            text="respuesta real", provider="p", model="m",
            level=InferenceLevel.L1, latency_ms=1, success=True,
        )
        agent = AtlasACPAgent(hub=hub)
        session = await agent.new_session(cwd="/tmp")

        result = await agent.prompt(
            session_id=session.session_id, prompt=[_FakeTextBlock("hola atlas")],
        )

        assert result.stop_reason == "end_turn"
        hub.infer_for_role.assert_called_once()
        role_arg = hub.infer_for_role.call_args[0][0]
        assert role_arg == "chat"
        state = agent._sessions[session.session_id]
        assert state.history[0] == {"role": "user", "content": "hola atlas"}
        assert state.history[1] == {"role": "assistant", "content": "respuesta real"}

    async def test_hub_failure_does_not_raise_and_reports_error_text(self) -> None:
        from atlas.core.inference_hub import InferenceLevel

        hub = MagicMock()
        hub.infer_for_role.return_value = InferenceResponse(
            text="", provider="p", model="m", level=InferenceLevel.L1,
            latency_ms=1, success=False, error="proveedor caído",
        )
        agent = AtlasACPAgent(hub=hub)
        session = await agent.new_session(cwd="/tmp")

        result = await agent.prompt(
            session_id=session.session_id, prompt=[_FakeTextBlock("hola")],
        )
        assert result.stop_reason == "end_turn"  # no lanza, responde con el error como texto


class TestCancelAndAuthenticate:
    async def test_cancel_does_not_raise(self) -> None:
        agent = AtlasACPAgent(hub=MagicMock())
        await agent.cancel(session_id="cualquiera")  # no debe lanzar

    async def test_authenticate_returns_none_local_trusted_server(self) -> None:
        agent = AtlasACPAgent(hub=MagicMock())
        assert await agent.authenticate(method_id="none") is None
