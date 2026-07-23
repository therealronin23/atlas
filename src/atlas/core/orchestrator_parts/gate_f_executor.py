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
        desktop_invoke: Callable[[str, dict[str, Any]], Any] | None = None,
        desktop_invoke_readonly: Callable[[str, dict[str, Any]], Any] | None = None,
        policy_evaluate: Callable[[Any], Any] | None = None,
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
        # t3-1-universal-gui-operator: narrow, no un cliente MCP propio —
        # en producción se envuelven sobre McpRegistry.dispatch (ver
        # Orchestrator.__init__). None por defecto: sin computer-control-mcp
        # cableado en la config MCP real (Fase 8, no en este entorno),
        # get_desktop_tool() falla honesto en vez de fingir que funciona.
        self._desktop_invoke = desktop_invoke
        self._desktop_invoke_readonly = desktop_invoke_readonly
        self._policy_evaluate = policy_evaluate
        self._browser_tool: Any | None = None
        self._editor_tool: Any | None = None
        self._vision_loop: Any | None = None
        self._desktop_tool: Any | None = None
        self._crawler_tool: Any | None = None
        self._fs_bridge: Any | None = None
        self._claude_code_tool: Any | None = None
        self._stirling_pdf_tool: Any | None = None
        self._image_gen_tool: Any | None = None
        self._video_gen_tool: Any | None = None
        self._home_assistant_tool: Any | None = None
        self._git_checkpoint_manager: Any | None = None

    # ------------------------------------------------------------------ tools
    def attach(
        self,
        *,
        browser: Any | None = None,
        editor: Any | None = None,
        vision_loop: Any | None = None,
        desktop: Any | None = None,
    ) -> None:
        if browser is not None:
            self._browser_tool = browser
        if editor is not None:
            self._editor_tool = editor
        if vision_loop is not None:
            self._vision_loop = vision_loop
        if desktop is not None:
            self._desktop_tool = desktop

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
            elif tool == "desktop":
                result = self.execute_desktop_command(action, args, task=task)
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

    def execute_desktop_command(
        self, action: str, args: dict[str, Any], *, task: Task | None = None,
    ) -> dict[str, Any]:
        """t3-1-universal-gui-operator. observe/windows son solo lectura
        (sin PolicyEngine). click/type/key mutan la pantalla real: además
        del requires_approval estático del parser (único punto de
        interacción humana, sin cambio de UX), se corrobora aquí contra
        PolicyEngine (capability computer_use.execute, pol_hard_computer_use)
        — si por un bug de wiring esto se invocara sin aprobación previa,
        PolicyEngine sigue en require_gate y aborta (fail-closed, defensa en
        profundidad, no sustituye el HITL de Gate F)."""
        desktop = self.get_desktop_tool()
        if action == "observe":
            return {"screenshot": desktop.screenshot(str(args.get("name") or "desktop"))}
        if action == "windows":
            return {"windows": desktop.list_windows()}

        self._check_desktop_policy(task)
        if action == "click":
            return {"result": desktop.click(int(args["x"]), int(args["y"]))}
        if action == "type":
            return {"result": desktop.type_text(str(args["text"]))}
        if action == "key":
            return {"result": desktop.key(str(args["combo"]))}
        raise RuntimeError(f"Unsupported desktop action: {action}")

    def _check_desktop_policy(self, task: Task | None) -> None:
        if self._policy_evaluate is None:
            return
        from atlas.fabric.models import UnlessCondition  # noqa: PLC0415
        from atlas.fabric.policy import PolicyRequest  # noqa: PLC0415

        approvals = (
            [UnlessCondition.GATE_APPROVED]
            if task is not None and task.route == RoutingLevel.REQUIRES_APPROVAL
            else []
        )
        decision = self._policy_evaluate(
            PolicyRequest(capability="computer_use.execute", approvals=approvals)
        )
        if decision.decision != "allow":
            raise RuntimeError(
                f"PolicyEngine denegó computer_use.execute: {decision.decision} "
                f"— {decision.reason}"
            )

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

    def get_crawler_tool(self) -> Any:
        if self._crawler_tool is None:
            from atlas.tools.crawler import CrawlerTool  # noqa: PLC0415

            self._crawler_tool = CrawlerTool(
                workspace=self._workspace,
                bridge=self._ssrf_bridge,
                merkle=self._merkle,
                allow_private_network=False,
            )
        return self._crawler_tool

    def run_web_crawl(self, url: str) -> dict[str, Any]:
        result = self.get_crawler_tool().crawl(url)
        return {
            "url": result.url, "success": result.success,
            "status_code": result.status_code, "markdown": result.markdown,
            "error": result.error,
        }

    def get_fs_bridge_tool(self) -> Any:
        if self._fs_bridge is None:
            from atlas.security.external_fs_bridge import ExternalFsBridge  # noqa: PLC0415

            self._fs_bridge = ExternalFsBridge()
        return self._fs_bridge

    def get_claude_code_tool(self) -> Any:
        if self._claude_code_tool is None:
            from atlas.tools.claude_code_tool import ClaudeCodeTool  # noqa: PLC0415

            self._claude_code_tool = ClaudeCodeTool(
                workspace=self._workspace,
                fs_bridge=self.get_fs_bridge_tool(),
                merkle=self._merkle,
            )
        return self._claude_code_tool

    def run_invoke_claude_code(
        self, task: str, cwd: str, permission_mode: str = "plan",
    ) -> dict[str, Any]:
        result = self.get_claude_code_tool().delegate(task, cwd, permission_mode=permission_mode)
        return {
            "task": result.task, "cwd": result.cwd, "success": result.success,
            "result_text": result.result_text, "cost_usd": result.cost_usd,
            "session_id": result.session_id, "error": result.error,
        }

    def get_stirling_pdf_tool(self) -> Any:
        if self._stirling_pdf_tool is None:
            from atlas.tools.stirling_pdf_tool import StirlingPdfTool  # noqa: PLC0415

            self._stirling_pdf_tool = StirlingPdfTool(
                fs_bridge=self.get_fs_bridge_tool(), merkle=self._merkle,
            )
        return self._stirling_pdf_tool

    def run_manipulate_pdf(
        self, operation: str, input_path: str, output_path: str, **params: str,
    ) -> dict[str, Any]:
        result = self.get_stirling_pdf_tool().run_operation(
            operation, input_path, output_path, **params,
        )
        return {
            "operation": result.operation, "input_path": result.input_path,
            "output_path": result.output_path, "success": result.success,
            "bytes_written": result.bytes_written, "error": result.error,
        }

    def get_image_gen_tool(self) -> Any:
        if self._image_gen_tool is None:
            from atlas.tools.image_gen_tool import ImageGenTool  # noqa: PLC0415

            self._image_gen_tool = ImageGenTool(
                fs_bridge=self.get_fs_bridge_tool(), merkle=self._merkle,
            )
        return self._image_gen_tool

    def run_image_generate(
        self, prompt: str, output_path: str, *, model: str = "fal-ai/flux/dev",
        aspect_ratio: str = "landscape",
    ) -> dict[str, Any]:
        result = self.get_image_gen_tool().generate(
            prompt, output_path, model=model, aspect_ratio=aspect_ratio,
        )
        return {
            "prompt": result.prompt, "model": result.model,
            "output_path": result.output_path, "success": result.success,
            "image_url": result.image_url, "bytes_written": result.bytes_written,
            "error": result.error,
        }

    def get_video_gen_tool(self) -> Any:
        if self._video_gen_tool is None:
            from atlas.tools.video_gen_tool import VideoGenTool  # noqa: PLC0415

            self._video_gen_tool = VideoGenTool(
                fs_bridge=self.get_fs_bridge_tool(), merkle=self._merkle,
            )
        return self._video_gen_tool

    def run_video_generate(
        self, prompt: str, output_path: str, *,
        model: str = "fal-ai/ltx-2.3-22b/text-to-video", aspect_ratio: str = "16:9",
    ) -> dict[str, Any]:
        result = self.get_video_gen_tool().generate(
            prompt, output_path, model=model, aspect_ratio=aspect_ratio,
        )
        return {
            "prompt": result.prompt, "model": result.model,
            "output_path": result.output_path, "success": result.success,
            "video_url": result.video_url, "bytes_written": result.bytes_written,
            "error": result.error,
        }

    def get_home_assistant_tool(self) -> Any:
        if self._home_assistant_tool is None:
            from atlas.tools.home_assistant_tool import HomeAssistantTool  # noqa: PLC0415

            self._home_assistant_tool = HomeAssistantTool(merkle=self._merkle)
        return self._home_assistant_tool

    def run_smart_home_query(
        self, action: str, *, domain: str = "", area: str = "", entity_id: str = "",
    ) -> dict[str, Any]:
        tool = self.get_home_assistant_tool()
        if action == "get_state":
            result = tool.get_state(entity_id)
        else:
            result = tool.list_entities(domain or None, area or None)
        return {"action": result.action, "success": result.success, "data": result.data, "error": result.error}

    def run_smart_home_control(
        self, domain: str, service: str, *, entity_id: str = "", data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.get_home_assistant_tool().call_service(
            domain, service, entity_id=entity_id or None, data=data,
        )
        return {"action": result.action, "success": result.success, "data": result.data, "error": result.error}

    def get_git_checkpoint_manager(self) -> Any:
        if self._git_checkpoint_manager is None:
            from atlas.core.git_checkpoint import GitCheckpointManager  # noqa: PLC0415

            self._git_checkpoint_manager = GitCheckpointManager(merkle=self._merkle)
        return self._git_checkpoint_manager

    def run_git_checkpoint_restore(
        self, repo_path: str, ref: str, run_count: int, kind: str,
    ) -> dict[str, Any]:
        """t1-git-checkpoint-agentic-wiring: `restore()` es DESTRUCTIVO (git
        reset --hard + clean -fd). Llegar aquí YA implica que el HITL de
        ADR-032/033 aprobó la mutación (dispatch_mutation solo llama esto tras
        aprobación); la guarda que queda es estructural, no de permisos:
        rechazar cualquier repo_path que no sea un worktree efímero real
        (nunca el checkout git principal) ANTES de tocar el disco."""
        from atlas.core.git_checkpoint import (  # noqa: PLC0415
            CheckpointEntry,
            GitCheckpointError,
            is_ephemeral_worktree,
        )

        path = Path(repo_path)
        if not is_ephemeral_worktree(path):
            return {
                "repo_path": repo_path, "ref": ref, "success": False,
                "error": (
                    f"{repo_path} no es un worktree efimero (.git no es un "
                    "fichero) - restore() nunca opera sobre el checkout git real."
                ),
            }
        if kind not in ("commit", "stash"):
            return {
                "repo_path": repo_path, "ref": ref, "success": False,
                "error": f"kind invalido {kind!r}: debe ser 'commit' o 'stash'",
            }
        checkpoint = CheckpointEntry(
            ref=ref, run_count=run_count, kind=kind,  # type: ignore[arg-type]
            created_at="",
        )
        try:
            self.get_git_checkpoint_manager().restore(path, checkpoint)
        except GitCheckpointError as exc:
            return {"repo_path": repo_path, "ref": ref, "success": False, "error": str(exc)}
        return {"repo_path": repo_path, "ref": ref, "run_count": run_count, "success": True, "error": None}

    def run_read_external_file(self, path: str) -> dict[str, Any]:
        decision = self.get_fs_bridge_tool().check(path)
        if not decision.allowed:
            return {
                "path": path, "allowed": False,
                "resolved_path": decision.resolved_path, "content": "",
                "error": decision.reason,
            }
        try:
            content = Path(decision.resolved_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {
                "path": path, "allowed": True,
                "resolved_path": decision.resolved_path, "content": "",
                "error": str(exc),
            }
        if len(content) > 20000:
            content = content[:20000] + "... [truncado]"
        return {
            "path": path, "allowed": True,
            "resolved_path": decision.resolved_path, "content": content,
            "error": None,
        }

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

    def get_desktop_tool(self) -> Any:
        if self._desktop_tool is None:
            if self._desktop_invoke is None or self._desktop_invoke_readonly is None:
                raise RuntimeError(
                    "DesktopTool no está cableado: falta desktop_invoke/"
                    "desktop_invoke_readonly (computer-control-mcp no está "
                    "en la config MCP real de este entorno — Fase 8/9 de "
                    "t3-1-universal-gui-operator, pendiente de un entorno "
                    "con Xvfb :99 + .venv-desktop)."
                )
            from atlas.tools.computer_use.desktop_tool import DesktopTool  # noqa: PLC0415

            self._desktop_tool = DesktopTool(
                invoke=self._desktop_invoke,
                invoke_readonly=self._desktop_invoke_readonly,
            )
        return self._desktop_tool
