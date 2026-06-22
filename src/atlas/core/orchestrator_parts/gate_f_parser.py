"""Parsers de comandos Gate F (browser/editor/vision) + resolución de paths.

Extraído de ``Orchestrator`` (refactor god-object slice 3, 2026-05-30).
Solo la cara **declarativa** del router se mueve aquí (parsers puros, sin
estado). La ejecución (que toca Merkle, GateH, executor, bus, lazy tools y
aprobaciones) sigue en ``Orchestrator`` por ahora — extraerla requeriría
inyectar ~10 colaboradores y se hará en una iteración posterior si aporta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class GateFCommand:
    tool: str
    action: str
    args: dict[str, Any]
    requires_approval: bool
    reason: str


def split_payload(rest: str) -> tuple[str, str | None]:
    left, sep, right = rest.partition("::")
    if not sep:
        return rest.strip(), None
    return left.strip(), right.lstrip()


def parse_browser_command(action: str, rest: str) -> GateFCommand | None:
    if action in {"navigate", "nav", "open", "abrir", "navegar"} and rest:
        return GateFCommand(
            tool="browser", action="navigate", args={"url": rest},
            requires_approval=True,
            reason="Browser navigation touches an external page.",
        )
    if action in {"screenshot", "captura"}:
        return GateFCommand(
            tool="browser", action="screenshot", args={"name": rest or None},
            requires_approval=False,
            reason="Browser screenshot observes current page only.",
        )
    if action in {"extract", "extrae", "leer"}:
        return GateFCommand(
            tool="browser", action="extract", args={},
            requires_approval=False,
            reason="Browser extract observes current page only.",
        )
    if action == "click" and rest:
        return GateFCommand(
            tool="browser", action="click", args={"selector": rest},
            requires_approval=True,
            reason="Browser click mutates page state.",
        )
    if action == "fill" and rest:
        selector, value = split_payload(rest)
        if selector and value is not None:
            return GateFCommand(
                tool="browser", action="fill",
                args={"selector": selector, "value": value},
                requires_approval=True,
                reason="Browser fill mutates page state.",
            )
    return None


def parse_editor_command(
    action: str,
    rest: str,
    *,
    is_generated_tool_run: Callable[[str, str], bool],
) -> GateFCommand | None:
    if action in {"read", "lee", "leer"} and rest:
        return GateFCommand(
            tool="editor", action="read", args={"path": rest},
            requires_approval=False,
            reason="Editor read is observational and still goes through AtlasExecutor.",
        )
    if action in {"write", "escribe"} and rest:
        path, content = split_payload(rest)
        if path and content is not None:
            return GateFCommand(
                tool="editor", action="write",
                args={"path": path, "content": content},
                requires_approval=True,
                reason="Editor write changes filesystem state.",
            )
    if action in {"run", "run_task"} and rest:
        working_dir, command = split_payload(rest)
        if working_dir and command is not None:
            generated = is_generated_tool_run(working_dir, command)
            return GateFCommand(
                tool="editor", action="run",
                args={
                    "working_dir": working_dir,
                    "command": command,
                    "generated": generated,
                },
                requires_approval=True,
                reason="Editor run executes a command."
                + (" (Gate H generated audit)" if generated else ""),
            )
    if action == "apply_diff" and rest:
        path, diff_text = split_payload(rest)
        if path and diff_text is not None:
            return GateFCommand(
                tool="editor", action="apply_diff",
                args={"path": path, "diff": diff_text},
                requires_approval=True,
                reason="Editor apply_diff changes filesystem state.",
            )
    if action == "open" and rest:
        return GateFCommand(
            tool="editor", action="open", args={"path": rest},
            requires_approval=True,
            reason="Editor open launches a host process.",
        )
    return None


def parse_vision_command(action: str, rest: str) -> GateFCommand | None:
    if action in {"propose", "proposal", "observa", "observe"}:
        return GateFCommand(
            tool="vision", action="propose",
            args={"screenshot_name": rest or "vision_loop"},
            requires_approval=False,
            reason="Vision loop proposes an action but does not execute it.",
        )
    return None


def parse_gate_f_command(
    intent: str,
    *,
    is_generated_tool_run: Callable[[str, str], bool],
) -> GateFCommand | None:
    """Parser mínimo y explícito para Gate F.

    Formatos aceptados:
      - browser navigate <url>
      - browser screenshot [name]
      - browser extract
      - browser click <selector>
      - browser fill <selector> :: <value>
      - editor read <path>
      - editor write <path> :: <content>
      - editor run <working_dir> :: <command>
      - editor apply_diff <path> :: <unified diff>
      - editor open <path>
      - vision propose [screenshot_name]
    """
    text = intent.strip()
    if not text:
        return None
    head, sep, tail = text.partition(" ")
    if not sep:
        return None
    tool = head.lower()
    if tool not in {"browser", "editor", "vision"}:
        return None
    action, _, rest = tail.strip().partition(" ")
    action = action.lower()
    rest = rest.strip()
    if tool == "browser":
        return parse_browser_command(action, rest)
    if tool == "editor":
        return parse_editor_command(
            action, rest, is_generated_tool_run=is_generated_tool_run,
        )
    return parse_vision_command(action, rest)


def resolve_path(workspace: Path, value: str) -> Path:
    """Resuelve *value* relativo a *workspace* y garantiza contención.

    Reglas (fail-closed, input no confiable):
    - Tilde (~) en input externo se rechaza: expanduser() podría escapar.
    - Rutas absolutas se aceptan solo si ya están bajo *workspace*.
    - Traversal relativo (../../) se detecta tras resolve() y se rechaza.
    Lanza ValueError si el path resultante escapa del workspace.
    """
    # Rechazar tilde explícita: expanduser sobre input no confiable escapa.
    if value.startswith("~"):
        raise ValueError(
            f"resolve_path: tilde en input no confiable rechazado: {value!r}"
        )

    workspace_resolved = workspace.resolve()
    raw = Path(value)

    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (workspace_resolved / raw).resolve()

    # Verificar contención estricta.
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError:
        raise ValueError(
            f"resolve_path: path {candidate!r} escapa del workspace "
            f"{workspace_resolved!r} (input: {value!r})"
        )

    return candidate
