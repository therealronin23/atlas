"""Tests for GateFExecutor.run_read_external_file."""
from pathlib import Path
from typing import Any

import pytest

from atlas.core.contracts import RoutingLevel, Task, TaskSource
from atlas.core.orchestrator_parts.gate_f_executor import GateFExecutor
from atlas.security.external_fs_bridge import ExternalFsBridge


def _make_gfe(tmp_path: Path, **overrides: Any) -> GateFExecutor:
    """Create a minimal GateFExecutor with stubbed dependencies."""
    kwargs: dict[str, Any] = dict(
        workspace=tmp_path,
        executor=None,
        ssrf_bridge=None,
        merkle=None,
        gate_h=None,
        timetravel=lambda: None,
        bus=None,
        check_gate_h_allowed=lambda *a: None,
        record_receipt=lambda *a, **k: None,
        thermal_blocks=lambda: None,
    )
    kwargs.update(overrides)
    return GateFExecutor(**kwargs)


@pytest.fixture
def gfe(tmp_path: Path) -> GateFExecutor:
    return _make_gfe(tmp_path)


class TestRunReadExternalFile:
    """Test suite for GateFExecutor.run_read_external_file."""

    def test_file_inside_allowed_root(self, gfe: GateFExecutor, tmp_path: Path) -> None:
        """Case 1: File inside an allowed extra_root reads successfully."""
        # Create a test file inside tmp_path
        test_file = tmp_path / "test_file.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content, encoding="utf-8")

        # Override the fs_bridge with one that has tmp_path as an extra root
        gfe._fs_bridge = ExternalFsBridge(extra_roots={str(tmp_path)})

        result = gfe.run_read_external_file(str(test_file))

        assert result["path"] == str(test_file)
        assert result["allowed"] is True
        assert result["resolved_path"] == str(test_file.resolve())
        assert result["content"] == test_content
        assert result["error"] is None

    def test_file_outside_any_root_fail_closed(self, gfe: GateFExecutor, tmp_path: Path) -> None:
        """Case 2: File outside any root (default bridge, no extra_roots) is denied."""
        # Create a file outside tmp_path (use a sibling directory)
        outside_dir = tmp_path.parent / "outside_dir"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "outside_file.txt"
        outside_file.write_text("Should not be readable", encoding="utf-8")

        # Ensure the default fs_bridge has no extra_roots (fail-closed)
        gfe._fs_bridge = ExternalFsBridge()

        result = gfe.run_read_external_file(str(outside_file))

        assert result["path"] == str(outside_file)
        assert result["allowed"] is False
        assert result["content"] == ""
        assert result["error"] != ""
        assert result["error"] is not None

    def test_nonexistent_file_inside_allowed_root(self, gfe: GateFExecutor, tmp_path: Path) -> None:
        """Case 3: Non-existent file inside an allowed root returns allowed=True but error."""
        # Path to a non-existent file inside tmp_path
        nonexistent_file = tmp_path / "nonexistent_file.txt"

        # Override the fs_bridge with one that has tmp_path as an extra root
        gfe._fs_bridge = ExternalFsBridge(extra_roots={str(tmp_path)})

        result = gfe.run_read_external_file(str(nonexistent_file))

        assert result["path"] == str(nonexistent_file)
        assert result["allowed"] is True
        assert result["resolved_path"] == str(nonexistent_file.resolve())
        assert result["content"] == ""
        assert result["error"] != ""
        assert result["error"] is not None
        # Verify the error is an OSError (file not found)
        assert "No such file or directory" in result["error"] or "FileNotFoundError" in result["error"]


# ---------------------------------------------------------------------------
# execute_desktop_command (t3-1-universal-gui-operator)
# ---------------------------------------------------------------------------


class FakeDesktopTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def screenshot(self, name: str) -> dict[str, Any]:
        self.calls.append(("screenshot", (name,)))
        return {"path": f"/tmp/{name}.png"}

    def list_windows(self) -> list[str]:
        self.calls.append(("list_windows", ()))
        return ["window-1"]

    def click(self, x: int, y: int) -> dict[str, Any]:
        self.calls.append(("click", (x, y)))
        return {"clicked": [x, y]}

    def type_text(self, text: str) -> dict[str, Any]:
        self.calls.append(("type_text", (text,)))
        return {"typed": text}

    def key(self, combo: str) -> dict[str, Any]:
        self.calls.append(("key", (combo,)))
        return {"pressed": combo}


class _FakeDecision:
    def __init__(self, decision: str, reason: str = "test") -> None:
        self.decision = decision
        self.reason = reason


def _approved_task() -> Task:
    return Task(intent="desktop click", source=TaskSource.CLI, route=RoutingLevel.REQUIRES_APPROVAL)


class TestExecuteDesktopCommand:
    def test_observe_uses_desktop_screenshot(self, tmp_path: Path) -> None:
        desktop = FakeDesktopTool()
        gfe = _make_gfe(tmp_path)
        gfe.attach(desktop=desktop)

        result = gfe.execute_desktop_command("observe", {"name": "foo"})

        assert result == {"screenshot": {"path": "/tmp/foo.png"}}
        assert desktop.calls == [("screenshot", ("foo",))]

    def test_observe_defaults_name(self, tmp_path: Path) -> None:
        desktop = FakeDesktopTool()
        gfe = _make_gfe(tmp_path)
        gfe.attach(desktop=desktop)

        gfe.execute_desktop_command("observe", {})

        assert desktop.calls == [("screenshot", ("desktop",))]

    def test_windows_uses_desktop_list_windows(self, tmp_path: Path) -> None:
        desktop = FakeDesktopTool()
        gfe = _make_gfe(tmp_path)
        gfe.attach(desktop=desktop)

        result = gfe.execute_desktop_command("windows", {})

        assert result == {"windows": ["window-1"]}
        assert desktop.calls == [("list_windows", ())]

    def test_click_without_policy_evaluate_executes_directly(self, tmp_path: Path) -> None:
        """Sin PolicyEngine inyectado (default None): comportamiento previo
        intacto, solo requires_approval estático del parser aplica."""
        desktop = FakeDesktopTool()
        gfe = _make_gfe(tmp_path)
        gfe.attach(desktop=desktop)

        result = gfe.execute_desktop_command("click", {"x": 1, "y": 2})

        assert result == {"result": {"clicked": [1, 2]}}

    def test_type_and_key_dispatch(self, tmp_path: Path) -> None:
        desktop = FakeDesktopTool()
        gfe = _make_gfe(tmp_path)
        gfe.attach(desktop=desktop)

        assert gfe.execute_desktop_command("type", {"text": "hola"}) == {"result": {"typed": "hola"}}
        assert gfe.execute_desktop_command("key", {"combo": "ctrl+c"}) == {"result": {"pressed": "ctrl+c"}}

    def test_unsupported_action_raises(self, tmp_path: Path) -> None:
        gfe = _make_gfe(tmp_path)
        gfe.attach(desktop=FakeDesktopTool())

        with pytest.raises(RuntimeError, match="Unsupported desktop action"):
            gfe.execute_desktop_command("scroll", {})

    def test_click_denied_by_policy_engine_raises_before_executing(self, tmp_path: Path) -> None:
        desktop = FakeDesktopTool()

        def deny_policy(_req: Any) -> _FakeDecision:
            return _FakeDecision("require_gate", "sin aprobación de gate")

        gfe = _make_gfe(tmp_path, policy_evaluate=deny_policy)
        gfe.attach(desktop=desktop)

        with pytest.raises(RuntimeError, match="PolicyEngine denegó"):
            gfe.execute_desktop_command("click", {"x": 1, "y": 2})

        assert desktop.calls == [], "no debe ejecutar la acción real si PolicyEngine deniega"

    def test_click_allowed_by_policy_engine_when_task_already_approved(self, tmp_path: Path) -> None:
        from atlas.fabric.models import UnlessCondition

        captured: list[Any] = []

        def allow_policy(req: Any) -> _FakeDecision:
            captured.append(req)
            return _FakeDecision("allow")

        desktop = FakeDesktopTool()
        gfe = _make_gfe(tmp_path, policy_evaluate=allow_policy)
        gfe.attach(desktop=desktop)

        result = gfe.execute_desktop_command("click", {"x": 1, "y": 2}, task=_approved_task())

        assert result == {"result": {"clicked": [1, 2]}}
        assert captured[0].capability == "computer_use.execute"
        assert captured[0].approvals == [UnlessCondition.GATE_APPROVED]

    def test_click_without_approved_task_sends_no_gate_approved(self, tmp_path: Path) -> None:
        """Si execute_desktop_command se invocara sin que la tarea pasara por
        aprobación (bug de wiring), PolicyEngine no recibe GATE_APPROVED —
        require_gate por defecto sigue bloqueando, fail-closed."""
        captured: list[Any] = []

        def require_gate_policy(req: Any) -> _FakeDecision:
            captured.append(req)
            return _FakeDecision("require_gate")

        gfe = _make_gfe(tmp_path, policy_evaluate=require_gate_policy)
        gfe.attach(desktop=FakeDesktopTool())

        with pytest.raises(RuntimeError):
            gfe.execute_desktop_command("click", {"x": 1, "y": 2})

        assert captured[0].approvals == []

    def test_observe_and_windows_skip_policy_engine(self, tmp_path: Path) -> None:
        def exploding_policy(_req: Any) -> _FakeDecision:
            raise AssertionError("observaciones de solo lectura no deben consultar PolicyEngine")

        gfe = _make_gfe(tmp_path, policy_evaluate=exploding_policy)
        gfe.attach(desktop=FakeDesktopTool())

        gfe.execute_desktop_command("observe", {})
        gfe.execute_desktop_command("windows", {})


class TestGetDesktopTool:
    def test_raises_clear_error_when_not_wired(self, tmp_path: Path) -> None:
        gfe = _make_gfe(tmp_path)

        with pytest.raises(RuntimeError, match="DesktopTool no está cableado"):
            gfe.get_desktop_tool()

    def test_builds_desktop_tool_from_injected_invoke_callables(self, tmp_path: Path) -> None:
        calls: list[tuple[str, str, dict[str, Any]]] = []

        gfe = _make_gfe(
            tmp_path,
            desktop_invoke=lambda tool, args: calls.append(("invoke", tool, args)),
            desktop_invoke_readonly=lambda tool, args: calls.append(("readonly", tool, args)),
        )

        tool = gfe.get_desktop_tool()
        tool.list_windows()

        assert calls == [("readonly", "list_windows", {})]
        assert gfe.get_desktop_tool() is tool, "lazy: la misma instancia se reutiliza"
