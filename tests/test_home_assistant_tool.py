"""
Tests del Home Assistant Tool (absorbido de Hermes-Agent, 2026-07-18).

Mockea urllib (nunca una instancia HA real). Foco especial en la lista de
dominios de servicio bloqueados y la validación de entity_id/service —
lógica de seguridad absorbida fiel del original, no debe debilitarse.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.tools.home_assistant_tool import BLOCKED_SERVICE_DOMAINS, HomeAssistantTool


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class TestBlockedDomains:
    def test_all_dangerous_domains_present(self) -> None:
        expected = {
            "shell_command", "command_line", "python_script",
            "pyscript", "hassio", "rest_command",
        }
        assert expected <= BLOCKED_SERVICE_DOMAINS

    def test_call_service_blocks_shell_command_before_any_network_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        tool = HomeAssistantTool()
        with patch("urllib.request.urlopen") as urlopen_mock:
            result = tool.call_service("shell_command", "turn_on")
        assert not result.success
        assert "bloqueado" in (result.error or "")
        urlopen_mock.assert_not_called()

    def test_call_service_blocks_hassio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        tool = HomeAssistantTool()
        result = tool.call_service("hassio", "host_shutdown")
        assert not result.success


class TestInputValidation:
    def test_call_service_rejects_path_traversal_in_domain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        tool = HomeAssistantTool()
        result = tool.call_service("../../api/config", "turn_on")
        assert not result.success

    def test_get_state_rejects_malformed_entity_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        tool = HomeAssistantTool()
        result = tool.get_state("not-a-valid-entity-id")
        assert not result.success


class TestGovernance:
    def test_missing_token_returns_failed_result_not_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        tool = HomeAssistantTool()
        result = tool.list_entities()
        assert not result.success
        assert "HASS_TOKEN" in (result.error or "")


class TestReadOperationsMocked:
    def test_list_entities_filters_by_domain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        tool = HomeAssistantTool()
        states = [
            {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen"}},
            {"entity_id": "sensor.temp", "state": "21", "attributes": {"friendly_name": "Temp"}},
        ]
        with patch("urllib.request.urlopen", return_value=_FakeResponse(states)):
            result = tool.list_entities(domain="light")
        assert result.success
        assert result.data["count"] == 1
        assert result.data["entities"][0]["entity_id"] == "light.kitchen"

    def test_get_state_returns_raw_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        tool = HomeAssistantTool()
        entity = {"entity_id": "light.kitchen", "state": "on", "attributes": {}}
        with patch("urllib.request.urlopen", return_value=_FakeResponse(entity)):
            result = tool.get_state("light.kitchen")
        assert result.success
        assert result.data["entity_id"] == "light.kitchen"


class TestCallServiceMocked:
    def test_successful_call_returns_success_and_logs_moderate_risk(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HASS_TOKEN", "fake-token")
        merkle = MerkleLogger(log_dir=tmp_path / "ha_merkle_test")
        tool = HomeAssistantTool(merkle=merkle)
        with patch("urllib.request.urlopen", return_value=_FakeResponse([{"entity_id": "light.kitchen"}])):
            result = tool.call_service("light", "turn_on", entity_id="light.kitchen")
        assert result.success
        entries = list(merkle.tail(5))
        assert any(
            e.action == "home_assistant.call_service" and e.result == "ok"
            for e in entries
        )
