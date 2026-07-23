"""
Tests — ToolCoder: bucle de código agéntico por TOOL-CALLING (no completación
de texto). El modelo llama herramientas estructuradas (read_file/str_replace/
create_file) con argumentos JSON validados por la API — la corrupción de
delimitadores que mató 8 tareas delegadas NO PUEDE ocurrir aquí.

Reutiliza: InferenceHub ADR-031 (tools/messages/tool_calls), los guardrails de
la sesión (rutas protegidas, match único fail-closed, linter bloqueante).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from atlas.core.tool_coder import ToolCoder


class _ScriptedHub:
    """Hub falso que devuelve una secuencia de respuestas con tool_calls
    (formato normalizado ADR-031: {id, name, arguments(str JSON)})."""

    def __init__(self, turns: list[list[dict] | None]):
        # cada turno: lista de tool_calls, o None = respuesta final sin tools
        self._turns = turns
        self._i = 0
        self.requests: list = []

    def infer(self, req):
        from atlas.core.inference_hub import InferenceResponse, InferenceLevel
        self.requests.append(req)
        turn = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return InferenceResponse(
            success=True, text="" if turn else "listo",
            provider="stub", model="stub", level=InferenceLevel.L1,
            latency_ms=0, tool_calls=turn or [],
        )

    def infer_for_role(self, role, req):
        return self.infer(req)


def _tc(name: str, **arguments) -> dict:
    return {"id": f"call_{name}", "name": name, "arguments": json.dumps(arguments)}


def test_str_replace_tool_applies_edit(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,  # el modelo termina
    ])

    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"])

    assert result.success is True
    assert f.read_text() == "x = 2\n"
    assert "foo.py" in result.files_changed


def test_create_file_tool(tmp_path: Path):
    hub = _ScriptedHub([
        [_tc("create_file", path="nuevo.py", content="y = 1\n")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="crea nuevo.py", context_files=[], test_cmd=["true"])

    assert result.success is True
    assert (tmp_path / "nuevo.py").read_text() == "y = 1\n"


def test_create_file_rejects_overwrite_of_nontrivial_existing_file(tmp_path: Path):
    """Bug real encontrado en swarm-medición (2026-07-02, tarea multi-pieza):
    pedido 'añade una función SIN borrar nada', el modelo llamó create_file
    sobre un archivo de 338 líneas y lo dejó en 34 — destruyó todo el
    contenido no relacionado. Es EXACTAMENTE el modo de fallo que el usuario
    describió ('le pido pegar código y borran el archivo entero'). create_file
    es para archivos NUEVOS; sobre un archivo existente no trivial, rechaza
    fail-closed y sugiere str_replace — el modelo se corrige en el siguiente
    turno en vez de destruir contenido silenciosamente."""
    f = tmp_path / "big.py"
    f.write_text("\n".join(f"def f{i}(): return {i}" for i in range(50)) + "\n")
    hub = _ScriptedHub([
        [_tc("create_file", path="big.py", content="def nuevo(): return 1\n")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="añade una función sin borrar nada", context_files=["big.py"], test_cmd=["true"])

    # El archivo original NO se tocó
    assert "def f0(): return 0" in f.read_text()
    assert "def f49(): return 49" in f.read_text()
    tool_msgs = [
        m for req in hub.requests if req.messages
        for m in req.messages if m.get("role") == "tool"
    ]
    assert any("str_replace" in str(m.get("content", "")) for m in tool_msgs)


def test_create_file_allows_overwrite_of_trivial_existing_file(tmp_path: Path):
    """Un archivo existente pero trivial (pocas líneas) SÍ puede sobrescribirse
    — el guardrail apunta a evitar destrucción de contenido sustancial, no a
    prohibir toda reescritura."""
    f = tmp_path / "small.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("create_file", path="small.py", content="x = 2\n")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="cambia small.py", context_files=["small.py"], test_cmd=["true"])

    assert result.success is True
    assert f.read_text() == "x = 2\n"


def test_str_replace_ambiguous_returns_structured_error(tmp_path: Path):
    """Match no-único → la tool devuelve ERROR ESTRUCTURADO al modelo (no
    aplica a ciegas) — el modelo puede corregirse en el siguiente turno."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\nx = 1\n")

    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"])

    assert f.read_text() == "x = 1\nx = 1\n"  # sin cambios
    # El mensaje de error llegó al modelo como resultado de la tool
    tool_msgs = [
        m for req in hub.requests if req.messages
        for m in req.messages if m.get("role") == "tool"
    ]
    assert any("2 veces" in str(m.get("content", "")) or "único" in str(m.get("content", "")).lower()
               for m in tool_msgs)


def test_protected_path_rejected_via_tool(tmp_path: Path):
    hub = _ScriptedHub([
        [_tc("create_file", path=".env", content="SECRET=x\n")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="intenta crear .env", context_files=[], test_cmd=["true"])
    assert not (tmp_path / ".env").exists()


def test_lint_gate_rejects_broken_python(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = ((( roto")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="rompe foo", context_files=["foo.py"], test_cmd=["true"])
    assert f.read_text() == "x = 1\n"


def test_read_file_tool_returns_content(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("contenido_secreto = 42\n")
    hub = _ScriptedHub([
        [_tc("read_file", path="foo.py")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="lee foo", context_files=[], test_cmd=["true"])

    tool_msgs = [
        m for req in hub.requests if req.messages
        for m in req.messages if m.get("role") == "tool"
    ]
    assert any("contenido_secreto" in str(m.get("content", "")) for m in tool_msgs)


def test_read_file_tool_on_directory_returns_error_not_crash(tmp_path: Path):
    """IsADirectoryError (2026-07-03): el modelo puede pedir leer un directorio
    por error — antes reventaba toda la sesión con una excepción sin capturar."""
    (tmp_path / "a_dir").mkdir()
    hub = _ScriptedHub([
        [_tc("read_file", path="a_dir")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="lee a_dir", context_files=[], test_cmd=["true"])

    tool_msgs = [
        m for req in hub.requests if req.messages
        for m in req.messages if m.get("role") == "tool"
    ]
    assert any("es un directorio" in str(m.get("content", "")) for m in tool_msgs)


def test_test_failure_feeds_back_and_retries(tmp_path: Path):
    """Tests fallan tras el primer turno → el error vuelve al modelo, que
    corrige en el segundo intento."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    marker = tmp_path / "attempt2"
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,  # fin intento 1 → tests fallan (marker no existe)
        [_tc("create_file", path="attempt2", content="ok")],
        None,  # fin intento 2 → tests pasan (marker existe)
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="haz que exista attempt2",
        context_files=["foo.py"],
        test_cmd=["test", "-f", str(marker)],
        max_iterations=2,
    )

    assert result.success is True
    assert result.iterations == 2


def test_non_string_content_returns_structured_error(tmp_path: Path):
    """Bug real encontrado en swarm (2026-07-02): un modelo que devuelve
    `content` como objeto JSON (no string) crasheaba con TypeError crudo en
    ast.parse — rompía TODO el worker en vez de dar un error estructurado que
    el modelo pudiera corregir en el siguiente turno (mismo principio que el
    resto de guardrails de esta clase)."""
    hub = _ScriptedHub([
        [_tc("create_file", path="x.py", content={"not": "a string"})],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="crea x.py", context_files=[], test_cmd=["true"])

    assert not (tmp_path / "x.py").exists()
    tool_msgs = [
        m for req in hub.requests if req.messages
        for m in req.messages if m.get("role") == "tool"
    ]
    assert any("content" in str(m.get("content", "")) and "string" in str(m.get("content", "")).lower()
               for m in tool_msgs)


def test_non_string_old_str_returns_structured_error(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str=["x", "="], new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"])

    assert f.read_text() == "x = 1\n"
    tool_msgs = [
        m for req in hub.requests if req.messages
        for m in req.messages if m.get("role") == "tool"
    ]
    assert any("string" in str(m.get("content", "")).lower() for m in tool_msgs)


def test_max_tool_turns_guard(tmp_path: Path, monkeypatch):
    """Un modelo que llama tools sin parar no cicla infinito — corta en el
    límite de turnos (stuck guard del bucle agéntico). El techo se pina por
    entorno (ATLAS_TOOL_MAX_TURNS), que es a la vez el test del override."""
    monkeypatch.setenv("ATLAS_TOOL_MAX_TURNS", "10")
    hub = _ScriptedHub([
        [_tc("read_file", path="no_existe.py")],  # siempre la misma llamada
    ] * 50)
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="loop", context_files=[], test_cmd=["false"], max_iterations=1)

    assert result.success is False
    # nunca más del techo pinado de llamadas al hub por iteración
    assert len(hub.requests) <= 12


def test_turn_limit_with_real_edits_salvages_via_tests(tmp_path: Path, monkeypatch):
    """2026-07-09: el corte por techo de turnos era terminal y descartaba
    ediciones reales sin correr los tests. Ahora, si hubo cambios, se prueban:
    modelo que edita bien pero nunca da respuesta final → success si tests OK."""
    monkeypatch.setenv("ATLAS_TOOL_MAX_TURNS", "3")
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        [_tc("read_file", path="foo.py")],  # sigue llamando tools…
        [_tc("read_file", path="foo.py")],  # …hasta agotar el techo
    ] * 2)
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"], max_iterations=1)

    assert result.success is True
    assert f.read_text() == "x = 2\n"
    assert "foo.py" in result.files_changed


def test_repair_json_arguments_passthrough_valid():
    assert ToolCoder._repair_json_arguments('{"path": "a.py"}') == '{"path": "a.py"}'


def test_repair_json_arguments_strips_trailing_garbage():
    # Caso real 2026-07-09: JSON válido + basura pegada ("Extra data") crasheaba
    # litellm/ollama_pt al reproducir el historial en el turno siguiente.
    repaired = ToolCoder._repair_json_arguments('{"path": "a.py"}<|tool_end|>extra')
    assert json.loads(repaired) == {"path": "a.py"}


def test_repair_json_arguments_unparseable_returns_empty_object():
    assert ToolCoder._repair_json_arguments("no es json") == "{}"
    assert ToolCoder._repair_json_arguments("") == "{}"


def test_sandbox_tests_import_sandbox_tree_not_real_repo(tmp_path: Path):
    """2026-07-09: con sandbox, el install editable del venv hacía que los tests
    importaran el paquete del repo REAL — median el código equivocado. El
    subprocess de tests debe ver el src del sandbox en PYTHONPATH."""
    import sys as _sys

    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("X = 1\n")

    hub = _ScriptedHub([
        [_tc("str_replace", path="src/mypkg/__init__.py", old_str="X = 1", new_str="X = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    # El test SOLO pasa si `import mypkg` resuelve dentro del árbol donde el
    # coder editó (el sandbox) — mypkg no está instalado en el venv.
    result = coder.code(
        task="sube X a 2",
        context_files=["src/mypkg/__init__.py"],
        test_cmd=[_sys.executable, "-c", "import mypkg, sys; sys.exit(0 if mypkg.X == 2 else 1)"],
        sandbox=True,
    )

    assert result.success is True
    # El árbol real recibe el sync-back del fichero verificado…
    assert (pkg / "__init__.py").read_text() == "X = 2\n"


def test_sandbox_failure_leaves_real_tree_untouched(tmp_path: Path):
    """Al fallo en sandbox, el árbol real no se toca (riesgo task_078a59b1)."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 99")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["false"],
        max_iterations=1, sandbox=True,
    )

    assert result.success is False
    assert f.read_text() == "x = 1\n"


# ----------------------------------------------------------------------
# t1-toolcoder-process-sandbox: BwrapJail opt-in para test_cmd en sandbox.
# _create_sandbox solo aislaba RUTA (copia en tmp); estos tests demuestran
# que, con el flag activo, la ejecución pasa por BwrapJail.run_command en
# vez de subprocess directo — y que sin el flag (default) el comportamiento
# actual no cambia (deuda explícita, no relajada en silencio).
# ----------------------------------------------------------------------


def test_jail_flag_off_by_default_uses_direct_subprocess(tmp_path: Path, monkeypatch):
    """Sin ATLAS_TOOL_CODER_JAIL, el test_cmd del sandbox sigue corriendo por
    subprocess directo — BwrapJail nunca se construye."""
    import atlas.core.tool_coder as tool_coder_mod

    monkeypatch.delenv("ATLAS_TOOL_CODER_JAIL", raising=False)
    ctor_calls: list[tuple] = []
    monkeypatch.setattr(
        tool_coder_mod, "BwrapJail",
        lambda *a, **k: ctor_calls.append((a, k)) or MagicMock(),
    )

    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        max_iterations=1, sandbox=True,
    )

    assert result.success is True
    assert ctor_calls == [], "BwrapJail no debe construirse sin el flag opt-in"


def test_jail_flag_on_routes_sandbox_test_cmd_through_bwrap(tmp_path: Path, monkeypatch):
    """Con ATLAS_TOOL_CODER_JAIL=1, el test_cmd dentro del sandbox pasa por
    BwrapJail.run_command en vez de subprocess directo sobre el directorio
    temporal (acceptance criteria del backlog)."""
    import atlas.core.tool_coder as tool_coder_mod
    from atlas.security.bwrap_jail import BwrapResult

    monkeypatch.setenv("ATLAS_TOOL_CODER_JAIL", "1")

    fake_jail = MagicMock(spec=tool_coder_mod.BwrapJail)
    fake_jail.run_command.return_value = BwrapResult(0, "ok\n", "", 3)
    ctor_calls: list[tuple] = []

    def _fake_ctor(*args, **kwargs):
        ctor_calls.append((args, kwargs))
        return fake_jail

    monkeypatch.setattr(tool_coder_mod, "BwrapJail", _fake_ctor)

    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["pytest"],
        max_iterations=1, sandbox=True,
    )

    assert result.success is True
    assert ctor_calls, "BwrapJail no fue construido — la ejecución no pasó por el jail"
    fake_jail.run_command.assert_called_once()
    args, kwargs = fake_jail.run_command.call_args
    assert args[0] == ["pytest"]
    assert kwargs["working_dir_writable"] is True
    assert str(kwargs["working_dir"]).startswith(tempfile.gettempdir())
    assert kwargs["extra_env"]["PYTHONPATH"]


def test_jail_flag_on_without_bwrap_fails_closed(tmp_path: Path, monkeypatch):
    """Fail-closed: con el flag activo pero bwrap no disponible, la tarea
    falla con error explícito — no degrada en silencio a subprocess directo."""
    import atlas.core.tool_coder as tool_coder_mod
    from atlas.security.bwrap_jail import BwrapUnavailableError

    monkeypatch.setenv("ATLAS_TOOL_CODER_JAIL", "1")

    def _raise(*a, **k):
        raise BwrapUnavailableError("bwrap no está en PATH")

    monkeypatch.setattr(tool_coder_mod, "BwrapJail", _raise)

    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        max_iterations=1, sandbox=True,
    )

    assert result.success is False
    assert "bwrap" in (result.error or "").lower()
    assert f.read_text() == "x = 1\n"  # mismo invariante que sandbox_failure


def test_jail_flag_ignored_without_sandbox(tmp_path: Path, monkeypatch):
    """El flag solo aplica dentro del sandbox de _create_sandbox; sin
    sandbox=True no hay directorio temporal que aislar y BwrapJail no se
    construye (el test_cmd corre sobre el árbol real, como hoy)."""
    import atlas.core.tool_coder as tool_coder_mod

    monkeypatch.setenv("ATLAS_TOOL_CODER_JAIL", "1")
    ctor_calls: list[tuple] = []
    monkeypatch.setattr(
        tool_coder_mod, "BwrapJail",
        lambda *a, **k: ctor_calls.append((a, k)) or MagicMock(),
    )

    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        max_iterations=1, sandbox=False,
    )

    assert result.success is True
    assert ctor_calls == []
