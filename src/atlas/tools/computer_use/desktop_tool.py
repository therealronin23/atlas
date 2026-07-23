"""
Atlas Core — DesktopTool (Gate F/desktop, t3-1-universal-gui-operator).

Wrapper fino sobre el servidor MCP `computer-control-mcp`
(docs/design/mcp_catalog.yaml, status verificado — GUI mouse/keyboard/OCR
contra el display VIRTUAL Xvfb :99, nunca el real). No abre un cliente MCP
propio: recibe `invoke`/`invoke_readonly` como callables narrow inyectados
por el caller (mismo estilo que check_gate_h_allowed/record_receipt en
GateFExecutor), construidos en producción sobre McpRegistry.dispatch (el
cliente MCP real que el Orchestrator ya posee).

Solo las 4 tools documentadas por nombre en el catálogo como read_only
pasan por `invoke_readonly`; cualquier otra pasa por `invoke` (mutante,
requiere aprobación — ver desktop_action.py). Fail-closed: intentar colar
una tool no documentada como read-only por el camino `invoke_readonly`
levanta PermissionError, nunca se ejecuta a ciegas.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

READ_ONLY_DESKTOP_TOOLS: frozenset[str] = frozenset(
    {"take_screenshot", "take_screenshot_with_ocr", "get_screen_size", "list_windows"}
)


class DesktopTool:
    def __init__(
        self,
        *,
        invoke: Callable[[str, dict[str, Any]], Any],
        invoke_readonly: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        self._invoke = invoke
        self._invoke_readonly = invoke_readonly

    def screenshot(self, name: str = "desktop") -> Any:
        return self._call_readonly("take_screenshot", {"name": name})

    def screenshot_ocr(self, name: str = "desktop") -> Any:
        return self._call_readonly("take_screenshot_with_ocr", {"name": name})

    def list_windows(self) -> Any:
        return self._call_readonly("list_windows", {})

    def get_screen_size(self) -> Any:
        return self._call_readonly("get_screen_size", {})

    def click(self, x: int, y: int) -> Any:
        return self._call_mutating("click_screen", {"x": x, "y": y})

    def type_text(self, text: str) -> Any:
        return self._call_mutating("type_text", {"text": text})

    def key(self, combo: str) -> Any:
        return self._call_mutating("press_key", {"combo": combo})

    def _call_readonly(self, tool: str, args: dict[str, Any]) -> Any:
        if tool not in READ_ONLY_DESKTOP_TOOLS:
            raise PermissionError(
                f"{tool!r} no está en READ_ONLY_DESKTOP_TOOLS — no se puede "
                "invocar por el camino de solo lectura (fail-closed)."
            )
        return self._invoke_readonly(tool, args)

    def _call_mutating(self, tool: str, args: dict[str, Any]) -> Any:
        return self._invoke(tool, args)
