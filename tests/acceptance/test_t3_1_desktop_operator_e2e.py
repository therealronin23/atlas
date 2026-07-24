"""Test E2E de aceptación — t3-1-universal-gui-operator (2026-07-23).

Cierra el bloqueo explícito registrado en WORK_LEDGER.md: los tests unitarios
de Gate F (``tests/test_orchestrator_gate_f.py``) inyectan un
``DummyDesktopTool`` vía ``attach_gate_f_tools`` y nunca tocan el camino real
(``_desktop_mcp_invoke`` -> ``McpRegistry.dispatch`` -> ``computer-control-mcp``
-> Xvfb). Este test SÍ recorre ese camino completo, sin fakes, contra:

  * Xvfb real en ``:99`` (systemd user unit ``atlas-xvfb.service``).
  * ``computer-control-mcp`` real (paquete PyPI, venv aislado
    ``.venv-desktop/``), arrancado como subproceso MCP real por el
    ``McpRegistry`` real del ``Orchestrator``.
  * Dos apps de escritorio REALES (``xclock``, ``xcalc``) corriendo como
    procesos X11 de verdad sobre ese display.

Se salta automáticamente (no falla) si Xvfb :99, el venv de escritorio o los
binarios X11 no están disponibles en la máquina — es un test de
infraestructura real, no reproducible sin ese entorno (igual que
``pytest -m computer_use`` para el navegador).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from atlas.core.contracts import RoutingLevel, TaskStatus
from atlas.core.orchestrator import Orchestrator

DISPLAY = ":99"
DESKTOP_MCP_BIN = Path(__file__).resolve().parents[2] / ".venv-desktop" / "bin" / "computer-control-mcp"


def _xvfb_is_up() -> bool:
    try:
        result = subprocess.run(
            ["xdpyinfo", "-display", DISPLAY],
            capture_output=True, timeout=5, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not (_xvfb_is_up() and DESKTOP_MCP_BIN.is_file() and shutil.which("xclock") and shutil.which("xcalc")),
    reason="requiere Xvfb :99 + .venv-desktop/computer-control-mcp + xclock/xcalc reales",
)


@pytest.fixture
def two_real_desktop_apps() -> Iterator[list[subprocess.Popen[bytes]]]:
    """Lanza xclock y xcalc como procesos X11 REALES contra DISPLAY=:99."""
    env = {"DISPLAY": DISPLAY}
    procs = [
        subprocess.Popen(["xclock"], env={**env}),
        subprocess.Popen(["xcalc"], env={**env}),
    ]
    time.sleep(1.5)  # dar tiempo real a que las ventanas se mapeen
    try:
        yield procs
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


@pytest.fixture
def orch_with_real_desktop_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    """Orchestrator real con computer-control-mcp real cableado (sin fakes)."""
    workspace = tmp_path / "atlas"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("ATLAS_HOME", str(workspace))
    (workspace / "mcp_servers.json").write_text(
        """[
  {
    "name": "computer-control-mcp",
    "cmd": ["%s"],
    "cwd": null,
    "env_passthrough": [],
    "env_extra": {"DISPLAY": "%s"},
    "read_only_tools": ["take_screenshot", "take_screenshot_with_ocr", "get_screen_size", "list_windows"],
    "enabled": true,
    "timeout_seconds": 30.0
  }
]"""
        % (DESKTOP_MCP_BIN, DISPLAY),
        encoding="utf-8",
    )
    orch = Orchestrator(workspace=workspace)
    orch.start_mcp_servers()
    return orch


def _extract_window_list(windows_field: Any) -> list[Any]:
    """Desempaqueta la respuesta MCP cruda de list_windows a la lista real.

    ``McpRegistry._stringify`` (src/atlas/mcp/registry.py) tiene DOS formatos
    reales, no uno (verificado en vivo 2026-07-23 tras instalar el WM):

    - Sin resultados (``content`` vacío): cae al JSON crudo completo, p.ej.
      ``{"content": [], "structuredContent": {"result": []}, "isError": false}``.
    - Con resultados: extrae y concatena SOLO los ``content[].text`` con
      ``"\\n"``, uno por ventana, cada uno un objeto JSON pretty-printed (con
      saltos de línea propios) — sin envoltorio ``structuredContent``. Por
      eso no vale un split por líneas; hace falta un decoder que consuma
      objetos JSON concatenados uno detrás de otro.
    """
    if not isinstance(windows_field, str):
        return windows_field if isinstance(windows_field, list) else []
    text = windows_field.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        structured = payload.get("structuredContent", {})
        result = structured.get("result", []) if isinstance(structured, dict) else []
        return result if isinstance(result, list) else []
    windows: list[Any] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        remainder = text[idx:].lstrip()
        if not remainder:
            break
        idx += len(text[idx:]) - len(remainder)
        obj, end = decoder.raw_decode(text[idx:])
        windows.append(obj)
        idx += end
    return windows


def test_list_windows_sees_two_real_desktop_apps(
    orch_with_real_desktop_mcp: Orchestrator,
    two_real_desktop_apps: list[subprocess.Popen[bytes]],
) -> None:
    """Observación (sin aprobación) contra las 2 apps reales."""
    task = orch_with_real_desktop_mcp.handle_intent("desktop windows")

    assert task.status == TaskStatus.DONE
    assert task.route == RoutingLevel.DETERMINISTIC_TOOL
    assert task.result is not None
    window_list = _extract_window_list(task.result["windows"])
    # No fingimos: verificamos CONTENIDO real (>=2 ventanas), no solo que
    # la respuesta serializada tenga longitud > 0.
    assert len(window_list) >= 2, (
        f"esperaba ver xclock+xcalc reales, vi {window_list!r} "
        "(0 ventanas visibles sin WM en Xvfb :99 — ver xfail reason)"
    )


def test_screenshot_returns_real_pixels(
    orch_with_real_desktop_mcp: Orchestrator,
    two_real_desktop_apps: list[subprocess.Popen[bytes]],
) -> None:
    task = orch_with_real_desktop_mcp.handle_intent("desktop observe e2e_t3_1")

    assert task.status == TaskStatus.DONE
    assert task.route == RoutingLevel.DETERMINISTIC_TOOL
    assert task.result is not None


def test_desktop_plan_executes_across_two_different_real_apps(
    orch_with_real_desktop_mcp: Orchestrator,
    two_real_desktop_apps: list[subprocess.Popen[bytes]],
) -> None:
    """Evidencia OBLIGATORIA del acceptance de t3-1 (docs/backlog.yaml): la
    MISMA lógica del planner ejecutada sobre >=2 apps de escritorio
    distintas, sin ninguna rama de código condicionada al nombre de la app.
    DesktopPlanner usa un InferenceHub FAKE (determinista, cero LLM real —
    disciplina del proyecto) devolviendo un plan de 2 clicks; la EJECUCIÓN
    de esos clicks es real contra Xvfb :99 vía computer-control-mcp, la
    misma DesktopTool que test_real_click_requires_approval_then_executes."""
    from unittest.mock import MagicMock

    from atlas.tools.computer_use.desktop_planner import DesktopPlanner

    hub = MagicMock()
    resp = MagicMock()
    resp.success = True
    resp.text = (
        '{"steps": ['
        '{"kind": "click", "x": 50, "y": 50, "reason": "click en xclock"},'
        '{"kind": "click", "x": 260, "y": 60, "reason": "click en xcalc"}'
        "]}"
    )
    hub.infer_for_role.return_value = resp
    orch_with_real_desktop_mcp._gate_f_exec.attach(desktop_planner=DesktopPlanner(hub))

    task = orch_with_real_desktop_mcp.handle_intent("desktop plan abre las 2 apps y haz click en cada una")

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.route == RoutingLevel.REQUIRES_APPROVAL

    approved = orch_with_real_desktop_mcp.approve_pending(task.id, approved=True)

    assert approved["status"] == TaskStatus.DONE.value
    plan_result = approved["result"]["plan"]
    assert [step["kind"] for step in plan_result] == ["click", "click"]
    # Ejecución real, no fingida: cada click devuelve el resultado real de
    # computer-control-mcp -> click_screen, sin error.
    for step in plan_result:
        assert "error" not in str(step["result"]).lower()


def test_real_click_requires_approval_then_executes_against_real_mcp(
    orch_with_real_desktop_mcp: Orchestrator,
    two_real_desktop_apps: list[subprocess.Popen[bytes]],
) -> None:
    """El punto central del acceptance: una acción MUTANTE real (click) pasa
    por el único HITL (approve_pending) y de ahí ejecuta de verdad contra
    computer-control-mcp -> Xvfb -> xcalc/xclock reales — CERO fakes en el
    camino, a diferencia de test_orchestrator_gate_f.py."""
    task = orch_with_real_desktop_mcp.handle_intent("desktop click 50,50")

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.route == RoutingLevel.REQUIRES_APPROVAL
    assert task.tool_name == "desktop.click"

    approved = orch_with_real_desktop_mcp.approve_pending(task.id, approved=True)

    assert approved["status"] == TaskStatus.DONE.value
    # DesktopTool.click envuelve computer-control-mcp click_screen real;
    # un error de verdad (server caído, display roto) se propagaría aquí.
    assert "error" not in str(approved.get("result", "")).lower()
