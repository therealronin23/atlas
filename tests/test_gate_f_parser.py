"""Tests unitarios y adversariales para gate_f_parser.

Cubre: resolve_path (contención al workspace), parse_browser_command,
parse_editor_command, parse_vision_command, parse_gate_f_command y
split_payload (incluyendo bordes y casos de inyección).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.orchestrator_parts.gate_f_parser import (
    GateFCommand,
    parse_browser_command,
    parse_desktop_command,
    parse_editor_command,
    parse_gate_f_command,
    parse_vision_command,
    resolve_path,
    split_payload,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WORKSPACE = Path("/workspace/project")


def _no_generated(working_dir: str, command: str) -> bool:  # noqa: ARG001
    return False


# ---------------------------------------------------------------------------
# split_payload
# ---------------------------------------------------------------------------


class TestSplitPayload:
    def test_no_separator_returns_stripped(self) -> None:
        left, right = split_payload("  hello  ")
        assert left == "hello"
        assert right is None

    def test_with_separator(self) -> None:
        left, right = split_payload("path/to/file :: content here")
        assert left == "path/to/file"
        assert right == "content here"

    def test_empty_string(self) -> None:
        left, right = split_payload("")
        assert left == ""
        assert right is None

    def test_separator_at_start(self) -> None:
        left, right = split_payload(":: value")
        assert left == ""
        assert right == "value"

    def test_separator_at_end(self) -> None:
        left, right = split_payload("key ::")
        assert left == "key"
        assert right == ""

    def test_multiple_double_colons_only_first_split(self) -> None:
        left, right = split_payload("a :: b :: c")
        assert left == "a"
        assert right == "b :: c"

    def test_injected_newline_in_value_passes_through(self) -> None:
        """split_payload no filtra newlines; el contrato es solo particionar."""
        left, right = split_payload("selector :: value\ninjected")
        assert left == "selector"
        assert right == "value\ninjected"


# ---------------------------------------------------------------------------
# resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_relative_inside_workspace(self) -> None:
        result = resolve_path(WORKSPACE, "subdir/file.txt")
        assert str(result).startswith(str(WORKSPACE))

    def test_relative_traversal_dotdot(self) -> None:
        """Traversal con ../ debe ser rechazado con ValueError."""
        with pytest.raises(ValueError, match="escapa del workspace"):
            resolve_path(WORKSPACE, "../../etc/passwd")

    def test_absolute_path_outside_workspace(self) -> None:
        """Ruta absoluta fuera del workspace debe rechazarse con ValueError."""
        with pytest.raises(ValueError, match="escapa del workspace"):
            resolve_path(WORKSPACE, "/etc/passwd")

    def test_absolute_path_inside_workspace(self) -> None:
        """Ruta absoluta dentro del workspace debe aceptarse."""
        inner = str(WORKSPACE / "subdir/file.txt")
        result = resolve_path(WORKSPACE, inner)
        assert str(result).startswith(str(WORKSPACE))

    def test_url_encoded_traversal(self) -> None:
        """..%2f no es decodificado por Path — queda literal, no escapa."""
        result = resolve_path(WORKSPACE, "..%2fetc%2fpasswd")
        # Path no decodifica URL encoding, así que %2f no actúa como /
        # El resultado debe quedar dentro del workspace.
        assert str(result).startswith(str(WORKSPACE)), (
            f"resolve_path con '..%2fetc%2fpasswd' produjo {result}"
        )

    def test_tilde_expansion(self) -> None:
        """Tilde en input no confiable debe rechazarse con ValueError."""
        with pytest.raises(ValueError, match="tilde"):
            resolve_path(WORKSPACE, "~/.ssh/id_rsa")

    def test_dot_path_stays_inside(self) -> None:
        result = resolve_path(WORKSPACE, ".")
        assert str(result).startswith(str(WORKSPACE))


# ---------------------------------------------------------------------------
# parse_browser_command
# ---------------------------------------------------------------------------


class TestParseBrowserCommand:
    def test_navigate_returns_command(self) -> None:
        cmd = parse_browser_command("navigate", "https://example.com")
        assert cmd is not None
        assert cmd.action == "navigate"
        assert cmd.args["url"] == "https://example.com"
        assert cmd.requires_approval is True

    def test_navigate_aliases(self) -> None:
        for alias in ("nav", "open", "abrir", "navegar"):
            cmd = parse_browser_command(alias, "https://x.com")
            assert cmd is not None, f"alias {alias!r} falló"

    def test_navigate_empty_rest_returns_none(self) -> None:
        assert parse_browser_command("navigate", "") is None

    def test_screenshot_no_name(self) -> None:
        cmd = parse_browser_command("screenshot", "")
        assert cmd is not None
        assert cmd.action == "screenshot"
        assert cmd.args["name"] is None
        assert cmd.requires_approval is False

    def test_screenshot_with_name(self) -> None:
        cmd = parse_browser_command("screenshot", "home_page")
        assert cmd is not None
        assert cmd.args["name"] == "home_page"

    def test_screenshot_alias_captura(self) -> None:
        cmd = parse_browser_command("captura", "")
        assert cmd is not None
        assert cmd.action == "screenshot"

    def test_extract_returns_command(self) -> None:
        cmd = parse_browser_command("extract", "")
        assert cmd is not None
        assert cmd.action == "extract"
        assert cmd.requires_approval is False

    def test_click_requires_selector(self) -> None:
        assert parse_browser_command("click", "") is None
        cmd = parse_browser_command("click", "#btn")
        assert cmd is not None
        assert cmd.args["selector"] == "#btn"
        assert cmd.requires_approval is True

    def test_fill_valid(self) -> None:
        cmd = parse_browser_command("fill", "#input :: secret")
        assert cmd is not None
        assert cmd.args["selector"] == "#input"
        assert cmd.args["value"] == "secret"
        assert cmd.requires_approval is True

    def test_fill_missing_separator_returns_none(self) -> None:
        assert parse_browser_command("fill", "#input") is None

    def test_fill_empty_selector_returns_none(self) -> None:
        assert parse_browser_command("fill", " :: value") is None

    def test_unknown_action_returns_none(self) -> None:
        assert parse_browser_command("hack", "anything") is None

    def test_navigate_javascript_url(self) -> None:
        """javascript: URIs son aceptadas — documentado como comportamiento actual."""
        cmd = parse_browser_command("navigate", "javascript:alert(1)")
        # El parser no filtra esquemas; depende del ejecutor. Registro explícito.
        assert cmd is not None
        assert cmd.requires_approval is True  # Al menos requiere aprobación


# ---------------------------------------------------------------------------
# parse_editor_command
# ---------------------------------------------------------------------------


class TestParseEditorCommand:
    def test_read_valid(self) -> None:
        cmd = parse_editor_command("read", "src/main.py", is_generated_tool_run=_no_generated)
        assert cmd is not None
        assert cmd.action == "read"
        assert cmd.args["path"] == "src/main.py"
        assert cmd.requires_approval is False

    def test_read_empty_path_returns_none(self) -> None:
        assert parse_editor_command("read", "", is_generated_tool_run=_no_generated) is None

    def test_read_alias_lee(self) -> None:
        cmd = parse_editor_command("lee", "file.txt", is_generated_tool_run=_no_generated)
        assert cmd is not None
        assert cmd.action == "read"

    def test_write_valid(self) -> None:
        cmd = parse_editor_command("write", "out.txt :: hello world", is_generated_tool_run=_no_generated)
        assert cmd is not None
        assert cmd.action == "write"
        assert cmd.args["path"] == "out.txt"
        assert cmd.args["content"] == "hello world"
        assert cmd.requires_approval is True

    def test_write_no_separator_returns_none(self) -> None:
        assert parse_editor_command("write", "out.txt", is_generated_tool_run=_no_generated) is None

    def test_write_empty_path_returns_none(self) -> None:
        assert parse_editor_command("write", " :: content", is_generated_tool_run=_no_generated) is None

    def test_run_valid(self) -> None:
        cmd = parse_editor_command("run", "/workspace :: pytest", is_generated_tool_run=_no_generated)
        assert cmd is not None
        assert cmd.action == "run"
        assert cmd.args["working_dir"] == "/workspace"
        assert cmd.args["command"] == "pytest"
        assert cmd.requires_approval is True

    def test_run_generated_flag(self) -> None:
        def always_generated(wd: str, c: str) -> bool:  # noqa: ARG001
            return True

        cmd = parse_editor_command("run", "/w :: ls", is_generated_tool_run=always_generated)
        assert cmd is not None
        assert cmd.args["generated"] is True
        assert "Gate H" in cmd.reason

    def test_run_missing_separator_returns_none(self) -> None:
        assert parse_editor_command("run", "/workspace", is_generated_tool_run=_no_generated) is None

    def test_apply_diff_valid(self) -> None:
        cmd = parse_editor_command(
            "apply_diff", "file.py :: @@ -1 +1 @@ -old +new",
            is_generated_tool_run=_no_generated,
        )
        assert cmd is not None
        assert cmd.action == "apply_diff"
        assert cmd.args["path"] == "file.py"
        assert "@@" in cmd.args["diff"]

    def test_apply_diff_no_diff_returns_none(self) -> None:
        assert parse_editor_command("apply_diff", "file.py", is_generated_tool_run=_no_generated) is None

    def test_open_valid(self) -> None:
        cmd = parse_editor_command("open", "project/", is_generated_tool_run=_no_generated)
        assert cmd is not None
        assert cmd.action == "open"
        assert cmd.requires_approval is True

    def test_unknown_action_returns_none(self) -> None:
        assert parse_editor_command("delete", "file.py", is_generated_tool_run=_no_generated) is None

    def test_read_traversal_path_stored_verbatim(self) -> None:
        """parse_editor_command guarda el path tal cual sin contenerlo.

        Documenta que la sanitización debe ocurrir en el ejecutor, no aquí.
        """
        cmd = parse_editor_command("read", "../../etc/passwd", is_generated_tool_run=_no_generated)
        assert cmd is not None
        assert cmd.args["path"] == "../../etc/passwd"


# ---------------------------------------------------------------------------
# parse_vision_command
# ---------------------------------------------------------------------------


class TestParseVisionCommand:
    def test_propose_no_name(self) -> None:
        cmd = parse_vision_command("propose", "")
        assert cmd is not None
        assert cmd.action == "propose"
        assert cmd.args["screenshot_name"] == "vision_loop"
        assert cmd.requires_approval is False

    def test_propose_with_name(self) -> None:
        cmd = parse_vision_command("propose", "my_screenshot")
        assert cmd is not None
        assert cmd.args["screenshot_name"] == "my_screenshot"

    def test_propose_aliases(self) -> None:
        for alias in ("proposal", "observa", "observe"):
            cmd = parse_vision_command(alias, "")
            assert cmd is not None, f"alias {alias!r} falló"

    def test_unknown_action_returns_none(self) -> None:
        assert parse_vision_command("execute", "") is None


# ---------------------------------------------------------------------------
# parse_desktop_command (t3-1-universal-gui-operator)
# ---------------------------------------------------------------------------


class TestParseDesktopCommand:
    def test_observe_no_name(self) -> None:
        cmd = parse_desktop_command("observe", "")
        assert cmd is not None
        assert cmd.tool == "desktop"
        assert cmd.action == "observe"
        assert cmd.args["name"] == "desktop"
        assert cmd.requires_approval is False

    def test_observe_with_name(self) -> None:
        cmd = parse_desktop_command("observe", "my_screenshot")
        assert cmd is not None
        assert cmd.args["name"] == "my_screenshot"

    def test_observe_aliases(self) -> None:
        for alias in ("screenshot", "observa", "captura"):
            cmd = parse_desktop_command(alias, "")
            assert cmd is not None, f"alias {alias!r} falló"
            assert cmd.requires_approval is False

    def test_windows(self) -> None:
        cmd = parse_desktop_command("windows", "")
        assert cmd is not None
        assert cmd.action == "windows"
        assert cmd.requires_approval is False

    def test_click_valid_coords(self) -> None:
        cmd = parse_desktop_command("click", "100,200")
        assert cmd is not None
        assert cmd.action == "click"
        assert cmd.args == {"x": 100, "y": 200}
        assert cmd.requires_approval is True

    def test_click_with_spaces_around_coords(self) -> None:
        cmd = parse_desktop_command("click", " 100 , 200 ")
        assert cmd is not None
        assert cmd.args == {"x": 100, "y": 200}

    def test_click_malformed_coords_returns_none(self) -> None:
        assert parse_desktop_command("click", "not,coords") is None
        assert parse_desktop_command("click", "100") is None
        assert parse_desktop_command("click", "") is None

    def test_type_text(self) -> None:
        cmd = parse_desktop_command("type", "hola mundo")
        assert cmd is not None
        assert cmd.args == {"text": "hola mundo"}
        assert cmd.requires_approval is True

    def test_type_empty_returns_none(self) -> None:
        assert parse_desktop_command("type", "") is None

    def test_key_combo(self) -> None:
        cmd = parse_desktop_command("key", "ctrl+c")
        assert cmd is not None
        assert cmd.args == {"combo": "ctrl+c"}
        assert cmd.requires_approval is True

    def test_plan_instruction(self) -> None:
        cmd = parse_desktop_command("plan", "abre la calculadora")
        assert cmd is not None
        assert cmd.args == {"instruction": "abre la calculadora"}
        assert cmd.requires_approval is True

    def test_unknown_action_returns_none(self) -> None:
        assert parse_desktop_command("execute", "") is None


# ---------------------------------------------------------------------------
# parse_gate_f_command (integración)
# ---------------------------------------------------------------------------


class TestParseGateFCommand:
    def _parse(self, intent: str) -> GateFCommand | None:
        return parse_gate_f_command(intent, is_generated_tool_run=_no_generated)

    def test_empty_returns_none(self) -> None:
        assert self._parse("") is None
        assert self._parse("   ") is None

    def test_single_word_returns_none(self) -> None:
        assert self._parse("browser") is None

    def test_unknown_tool_returns_none(self) -> None:
        assert self._parse("shell rm -rf /") is None

    def test_browser_navigate(self) -> None:
        cmd = self._parse("browser navigate https://example.com")
        assert cmd is not None
        assert cmd.tool == "browser"
        assert cmd.action == "navigate"

    def test_editor_write(self) -> None:
        cmd = self._parse("editor write foo.txt :: bar")
        assert cmd is not None
        assert cmd.tool == "editor"
        assert cmd.action == "write"

    def test_vision_propose(self) -> None:
        cmd = self._parse("vision propose")
        assert cmd is not None
        assert cmd.tool == "vision"

    def test_desktop_click(self) -> None:
        cmd = self._parse("desktop click 100,200")
        assert cmd is not None
        assert cmd.tool == "desktop"
        assert cmd.action == "click"
        assert cmd.requires_approval is True

    def test_desktop_observe(self) -> None:
        cmd = self._parse("desktop observe")
        assert cmd is not None
        assert cmd.tool == "desktop"
        assert cmd.requires_approval is False

    def test_case_insensitive_tool(self) -> None:
        cmd = self._parse("BROWSER navigate https://x.com")
        assert cmd is not None
        assert cmd.tool == "browser"

    def test_malformed_no_action(self) -> None:
        """'browser ' con acción vacía — el strip hace que action sea vacío."""
        assert self._parse("browser ") is None

    def test_extra_whitespace(self) -> None:
        cmd = self._parse("  browser   navigate   https://example.com  ")
        # El parser stripea la intención pero el split es por primer espacio
        # en tail; el resultado puede diferir. Lo importante es que no crashea.
        # Si parsea, la URL puede tener espacios extra en el frente — aceptable.
        assert cmd is None or cmd.tool == "browser"

    def test_injected_newline_in_intent(self) -> None:
        """Newlines en la intención no deben causar ejecución inesperada."""
        cmd = self._parse("browser navigate https://good.com\nbrowser navigate https://evil.com")
        # Debe parsear solo la primera URL (con el newline incluido) o None.
        assert cmd is None or cmd.tool == "browser"
        if cmd is not None:
            assert "\n" in cmd.args.get("url", "") or cmd.args.get("url", "").startswith("https://good.com")
