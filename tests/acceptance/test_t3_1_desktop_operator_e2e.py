"""Aceptación de seguridad y runtime — t3-1 universal GUI operator.

La implementación de Gate F y el adaptador desktop están presentes, pero el
ejecutable third-party ``computer-control-mcp`` no tiene todavía el artefacto,
hash, receipt e aislamiento exigidos por ADR-075/ADC-WO-116. Por ello se
prueban dos carriles sin falsear el estado:

* la cuarentena pre-spawn es una aceptación de seguridad siempre activa;
* los E2E funcionales reales se conservan y solo corren cuando Sentinel admite
  el artefacto exacto. Mientras ADC-WO-124 esté abierto se saltan como
  ``CONTRADICTED``, nunca como evidencia de producto vivo.

Los E2E admitidos recorren ``_desktop_mcp_invoke`` ->
``McpRegistry.dispatch`` -> ``computer-control-mcp`` -> Xvfb, con xclock y
xcalc reales. No se concede ninguna excepción por basename, ruta o fixture.
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
_QUARANTINE_REASON = "third-party executable"
_ADC_WO_124_SKIP = (
    "ADC-WO-124 / CONTRADICTED: computer-control-mcp no está admitido aún "
    "mediante artefacto+hash+scan+aislamiento+receipt Merkle+HITL de ADR-075"
)


def _xvfb_is_up() -> bool:
    try:
        result = subprocess.run(
            ["xdpyinfo", "-display", DISPLAY],
            capture_output=True, timeout=5, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


requires_real_desktop_infrastructure = pytest.mark.skipif(
    not (
        _xvfb_is_up()
        and DESKTOP_MCP_BIN.is_file()
        and shutil.which("xclock")
        and shutil.which("xcalc")
    ),
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


def _configured_desktop_orchestrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Orchestrator:
    """Construye el wiring real sin arrancar todavía el ejecutable externo."""
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
    return Orchestrator(workspace=workspace)


def _sentinel_quarantine_record(orch: Orchestrator) -> dict[str, Any] | None:
    for record in reversed(orch.audit_tail(50)):
        payload = record.get("payload", {})
        if (
            record.get("action") == "sentinel.server_vetoed"
            and isinstance(payload, dict)
            and payload.get("server") == "computer-control-mcp"
        ):
            return record
    return None


def test_unreceipted_desktop_mcp_is_audited_and_quarantined_pre_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADC-WO-116: la configuración histórica no puede crear un proceso."""
    orch = _configured_desktop_orchestrator(tmp_path, monkeypatch)
    spawned: list[str] = []

    def forbidden_factory(config: Any) -> Any:
        spawned.append(str(config.name))
        raise AssertionError("Sentinel debía vetar antes de crear el transporte")

    orch._mcp._factory = forbidden_factory
    orch.start_mcp_servers()

    record = _sentinel_quarantine_record(orch)
    assert spawned == []
    assert orch._mcp._transports == {}
    assert record is not None
    assert record["result"] == "blocked"
    assert _QUARANTINE_REASON in str(record["payload"]["detail"]).lower()
    assert not any(
        item.get("action") == "mcp.server_start_requested"
        for item in orch.audit_tail(50)
    )


@pytest.fixture
def orch_with_real_desktop_mcp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Orchestrator:
    """Arranca el MCP real únicamente si la admisión gobernada ya existe."""
    orch = _configured_desktop_orchestrator(tmp_path, monkeypatch)
    orch.start_mcp_servers()
    if "computer-control-mcp" not in orch._mcp._transports:
        record = _sentinel_quarantine_record(orch)
        if record is not None and _QUARANTINE_REASON in str(
            record["payload"]["detail"]
        ).lower():
            pytest.skip(_ADC_WO_124_SKIP)
        pytest.fail(
            "computer-control-mcp no alcanzó el transporte y no existe un "
            "veto Sentinel clasificable como ADC-WO-124"
        )
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


@requires_real_desktop_infrastructure
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


@requires_real_desktop_infrastructure
def test_screenshot_returns_real_pixels(
    orch_with_real_desktop_mcp: Orchestrator,
    two_real_desktop_apps: list[subprocess.Popen[bytes]],
) -> None:
    task = orch_with_real_desktop_mcp.handle_intent("desktop observe e2e_t3_1")

    assert task.status == TaskStatus.DONE
    assert task.route == RoutingLevel.DETERMINISTIC_TOOL
    assert task.result is not None
    screenshot = task.result["screenshot"]
    assert isinstance(screenshot, str)
    assert screenshot.strip()
    assert not screenshot.lower().startswith("error:")


@requires_real_desktop_infrastructure
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


@requires_real_desktop_infrastructure
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
