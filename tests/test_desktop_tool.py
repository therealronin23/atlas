"""Tests T3 (t3-1-universal-gui-operator) — DesktopTool: wrapper fino sobre
computer-control-mcp. invoke/invoke_readonly son callables narrow inyectados
(mismo estilo que check_gate_h_allowed/record_receipt en GateFExecutor), no
un cliente MCP propio. Solo lectura pasa por invoke_readonly; cualquier tool
fuera del allowlist read-only levanta PermissionError (fail-closed)."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.tools.computer_use.desktop_tool import DesktopTool


def _recording_tool() -> tuple[DesktopTool, list[tuple[str, str, dict[str, Any]]]]:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def invoke(tool: str, args: dict[str, Any]) -> Any:
        calls.append(("invoke", tool, args))
        return {"ok": True}

    def invoke_readonly(tool: str, args: dict[str, Any]) -> Any:
        calls.append(("readonly", tool, args))
        return {"ok": True}

    return DesktopTool(invoke=invoke, invoke_readonly=invoke_readonly), calls


def test_screenshot_uses_invoke_readonly() -> None:
    tool, calls = _recording_tool()

    tool.screenshot("foo")

    assert calls == [("readonly", "take_screenshot", {"name": "foo"})]


def test_screenshot_ocr_uses_invoke_readonly() -> None:
    tool, calls = _recording_tool()

    tool.screenshot_ocr("foo")

    assert calls == [("readonly", "take_screenshot_with_ocr", {"name": "foo"})]


def test_list_windows_uses_invoke_readonly() -> None:
    tool, calls = _recording_tool()

    tool.list_windows()

    assert calls == [("readonly", "list_windows", {})]


def test_get_screen_size_uses_invoke_readonly() -> None:
    tool, calls = _recording_tool()

    tool.get_screen_size()

    assert calls == [("readonly", "get_screen_size", {})]


def test_click_uses_invoke() -> None:
    tool, calls = _recording_tool()

    tool.click(100, 200)

    assert calls == [("invoke", "click_screen", {"x": 100, "y": 200})]


def test_type_text_uses_invoke() -> None:
    tool, calls = _recording_tool()

    tool.type_text("hola")

    assert calls == [("invoke", "type_text", {"text": "hola"})]


def test_key_uses_invoke() -> None:
    tool, calls = _recording_tool()

    tool.key("ctrl+c")

    assert calls == [("invoke", "press_key", {"combo": "ctrl+c"})]


def test_mutating_tool_name_through_readonly_path_raises_permission_error() -> None:
    tool, _calls = _recording_tool()

    with pytest.raises(PermissionError):
        tool._call_readonly("click_screen", {})
