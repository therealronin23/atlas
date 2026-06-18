"""Cluster de ejecución Gate F extraído del Orchestrator (cluster B).

Ejecuta comandos Gate F ya parseados y ruteados contra browser/editor/vision,
y posee el ciclo de vida (lazy) de esas tools. El *routing* y la aprobación
(estado compartido de approvals) permanecen en el Orchestrator; aquí solo vive
la ejecución pura. Extracción mecánica: mismas firmas, sin cambio de
comportamiento. Las deps del Orchestrator se inyectan por constructor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from atlas.core.contracts import RoutingLevel, Task, TaskStatus
from atlas.core.contracts import EventType
from atlas.core.orchestrator_parts.gate_f_parser import (
    resolve_path as _resolve_gate_f_path_fn,
)
from atlas.security.generated_code_policy import GeneratedCodePolicy


class GateFExecutor:
    def __init__(
        self,
        *,
        workspace: Path,
        executor: Any,
        ssrf_bridge: Any,
        merkle: Any,
        gate_h: Any,
        timetravel: Callable[[], Any],
        bus: Any,
        check_gate_h_allowed: Callable[[str, str | None], str | None],
        record_receipt: Callable[..., None],
        thermal_blocks: Callable[[], str | None],
    ) -> None:
        self._workspace = workspace
        self._executor = executor
        self._ssrf_bridge = ssrf_bridge
        self._merkle = merkle
        self._gate_h = gate_h
        # _timetravel es volátil en el Orchestrator (se reasigna al activar
        # Gate D); por eso se inyecta como getter lazy, no por valor.
        self._timetravel_get = timetravel
        self._bus = bus
        self._check_gate_h_allowed = check_gate_h_allowed
        self._record_receipt = record_receipt
        self._thermal_blocks = thermal_blocks
        self._browser_tool: Any | None = None
        self._editor_tool: Any | None = None
        self._vision_loop: Any | None = None

    # ------------------------------------------------------------------ tools
    def attach(
        self,
        *,
        browser: Any | None = None,
        editor: Any | None = None,
        vision_loop: Any | None = None,
    ) -> None:
        if browser is not None:
            self._browser_tool = browser
        if editor is not None:
            self._editor_tool = editor
        if vision_loop is not None:
            self._vision_loop = vision_loop

    def resolve_path(self, value: str) -> Path:
        return _resolve_gate_f_path_fn(self._workspace, value)

    # ------------------------------------------------------------------ execute
    def execute_task(self, task: Task) -> None:
        tool_key = task.tool_name or "gate_f"
        gate_h_block = self._check_gate_h_allowed(tool_key, task.id)
        if gate_h_block:
            task.transition(TaskStatus.FAILED)
            task.error = gate_h_block
            task.result = {"error": task.error, "paused": True}
            return

        thermal_block = self._thermal_blocks()
        if thermal_block:
            task.transition(TaskStatus.FAILED)
            task.error = thermal_block
            task.result = {"error": thermal_block, "thermal": True}
            return

        raw = task.metadata.get("gate_f_command")
        if not isinstance(raw, dict):
            raise RuntimeError("Gate F command metadata missing or invalid")
        tool = str(raw.get("tool", ""))
        action = str(raw.get("action", ""))
        args = raw.get("args", {})
        if not isinstance(args, dict):
            raise RuntimeError("Gate F command args missing or invalid")

        try:
            if tool == "browser":
                result = self.execute_browser_command(action, args)
            elif tool == "editor":
                result = self.execute_editor_command(action, args, task=task)
            elif tool == "vision":
                result = self.execute_vision_command(action, args)
            else:
                raise RuntimeError(f"Unknown Gate F tool: {tool}")
        except Exception as e:
            self._merkle.log(
                action="gate_f.tool_failed",
                agent=f"{tool}.{action}" if tool and action else "gate_f",
                result="failure",
                risk_level="moderate",
                payload={"error": str(e)[:500]},
                task_id=task.id,
            )
            self._gate_h.record_failure(
                tool_name=task.tool_name or "gate_f",
                failure_type="gate_f_execution",
                error=str(e),
                context={"tool": tool, "action": action, "args": args},
                task_id=task.id,
            )
            timetravel = self._timetravel_get()
            if timetravel is not None:
                timetravel.record_step(
                    task.id, "gate_h_failure",
                    {"tool": tool, "error": str(e)[:200]},
                )
            task.transition(TaskStatus.FAILED)
            task.error = str(e)
            self._bus.publish_type(EventType.TOOL_FAILED, {
                "task_id": task.id, "tool": task.tool_name, "error": str(e),
            }, task.id)
            return

        task.result = result
        self._merkle.log(
            action="tool.invoked",
            agent=task.tool_name or "gate_f",
            result="success",
            risk_level="medium" if task.route == RoutingLevel.REQUIRES_APPROVAL else "safe",
            payload={"tool": task.tool_name},
            task_id=task.id,
        )
        self._record_receipt(
            task,
            purpose=f"Gate F {tool}.{action}",
            safety_checks=["PermissionProfile", "AtlasExecutor", "GateH", "MerkleLogger"],
            approval_path="explicit" if task.route == RoutingLevel.REQUIRES_APPROVAL else "automatic",
        )
        task.transition(TaskStatus.DONE)
        self._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)

    def execute_browser_command(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        browser = self.get_browser_tool()
        if action == "navigate":
            return dict(browser.navigate(str(args["url"])).__dict__)
        if action == "screenshot":
            return dict(browser.screenshot(args.get("name")).__dict__)
        if action == "extract":
            return dict(browser.extract().__dict__)
        if action == "click":
            return dict(browser.click(str(args["selector"])).__dict__)
        if action == "fill":
            return dict(browser.fill(str(args["selector"]), str(args["value"])).__dict__)
        raise RuntimeError(f"Unsupported browser action: {action}")

    def execute_editor_command(
        self,
        action: str,
        args: dict[str, Any],
        *,
        task: Task | None = None,
    ) -> dict[str, Any]:
        editor = self.get_editor_tool()
        clearance = f"task:{task.id}" if task is not None else None
        if action == "read":
            return dict(editor.read_file(self.resolve_path(str(args["path"]))).__dict__)
        if action == "write":
            return dict(editor.write_file(
                self.resolve_path(str(args["path"])),
                str(args["content"]),
                clearance=clearance,
            ).__dict__)
        if action == "run":
            return self._execute_editor_run_command(
                task, args, editor, clearance=clearance,
            )
        if action == "apply_diff":
            return dict(editor.apply_diff(
                self.resolve_path(str(args["path"])),
                str(args["diff"]),
                clearance=clearance,
            ).__dict__)
        if action == "open":
            return dict(editor.open_project(self.resolve_path(str(args["path"]))).__dict__)
        raise RuntimeError(f"Unsupported editor action: {action}")

    def execute_vision_command(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        if action != "propose":
            raise RuntimeError(f"Unsupported vision action: {action}")
        proposal = self.get_vision_loop().propose_next(
            str(args.get("screenshot_name") or "vision_loop")
        )
        payload: dict[str, Any] = dict(proposal.__dict__)
        if proposal.requires_approval:
            self._merkle.log(
                action="vision.proposal_requires_approval",
                agent="orchestrator",
                result="pending",
                risk_level="medium",
                payload=payload,
            )
        return payload

    def _execute_editor_run_command(
        self,
        task: Task | None,
        args: dict[str, Any],
        editor: Any,
        *,
        clearance: str | None,
    ) -> dict[str, Any]:
        working_dir = self.resolve_path(str(args["working_dir"]))
        command = str(args["command"])
        generated = bool(args.get("generated"))

        if generated and task is not None:
            self._record_receipt(
                task,
                purpose="Generated editor run (pre-exec)",
                safety_checks=["GeneratedCodePolicy", "AST Guard", "AtlasExecutor"],
                approval_path="explicit",
            )
            self._validate_generated_script_source(command, working_dir)
            self._gate_h.assert_generated_reusable(command, task_id=task.id)

        result = editor.run_task(working_dir, command, clearance=clearance)
        out: dict[str, Any] = dict(result.__dict__)
        if generated and task is not None:
            out = self._execute_generated_editor_run(
                task,
                {"working_dir": str(working_dir), "command": command},
                out,
            )
        return out

    def _validate_generated_script_source(self, command: str, working_dir: Path) -> None:
        import shlex

        policy = GeneratedCodePolicy()
        for part in shlex.split(command):
            if not part.endswith(".py"):
                continue
            script = Path(part)
            if not script.is_absolute():
                script = (working_dir / script).resolve()
            if script.is_file():
                check = policy.check_generated_source(script.read_text(encoding="utf-8"))
                if not check.passed:
                    raise RuntimeError(f"GeneratedCodePolicy: {check.reason}")

    def _execute_generated_editor_run(
        self,
        task: Task,
        input_data: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = task.tool_name or "editor.run"
        validation = self._gate_h.audit_generated_run(
            tool_name,
            input_data,
            result,
            task_id=task.id,
            promote=True,
        )
        result = dict(result)
        result["gate_h"] = {
            "valid": validation.valid,
            "reasons": list(validation.reasons),
        }
        if not validation.valid:
            task.error = "; ".join(validation.reasons)
        return result

    # ------------------------------------------------------------------ lazy tools
    def get_browser_tool(self) -> Any:
        if self._browser_tool is None:
            from atlas.tools.browser import BrowserTool  # noqa: PLC0415

            self._browser_tool = BrowserTool(
                workspace=self._workspace,
                bridge=self._ssrf_bridge,
                merkle=self._merkle,
                allow_private_network=False,
            )
        return self._browser_tool

    def get_editor_tool(self) -> Any:
        if self._editor_tool is None:
            from atlas.tools.editor import EditorTool  # noqa: PLC0415

            self._editor_tool = EditorTool(
                workspace=self._workspace,
                executor=self._executor,
            )
        return self._editor_tool

    def get_vision_loop(self) -> Any:
        if self._vision_loop is None:
            from atlas.tools.computer_use.vision_loop import VisionLoop  # noqa: PLC0415

            self._vision_loop = VisionLoop(
                browser=self.get_browser_tool(),
                merkle=self._merkle,
            )
        return self._vision_loop
