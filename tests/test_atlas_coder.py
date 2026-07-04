"""
Tests para AtlasCoder — todo mockeado, sin red ni InferenceHub real.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.core.atlas_coder import AtlasCoder


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_hub(response_text: str, success: bool = True):
    hub = MagicMock()
    resp = MagicMock()
    resp.success = success
    resp.text = response_text
    resp.error = None if success else "error de prueba"
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def _sr_block(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_code_applies_edit_and_passes(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def hello():\n    return 'old'\n")

    hub = _make_hub(_sr_block("def hello():\n    return 'old'", "def hello():\n    return 'new'"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia hello",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert result.iterations == 1
    assert "new" in f.read_text()


def test_code_iterates_on_test_failure(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    # El hub siempre devuelve un bloque que no modifica nada relevante
    # (SEARCH no encontrado), pero lo que importa es que test_cmd siempre falla.
    hub = _make_hub(_sr_block("x = 1", "x = 2"))

    max_iter = 2
    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea que nunca pasa tests",
        context_files=["foo.py"],
        test_cmd=["false"],
        max_iterations=max_iter,
    )

    assert result.success is False
    assert result.iterations == max_iter


def test_code_stops_on_infer_failure(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("pass\n")

    hub = _make_hub("", success=False)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea cualquiera",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is False
    assert result.error is not None
    assert result.iterations == 1


def test_code_skips_unfound_search_block(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def real():\n    pass\n")

    # El bloque SEARCH contiene texto que NO existe en foo.py
    hub = _make_hub(_sr_block("texto_que_no_existe_nunca", "reemplazo"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    # No debe lanzar excepción; con test_cmd=["true"] debería ser success=True
    result = coder.code(
        task="tarea con bloque inválido",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True


def test_code_applies_edit_with_wrong_indentation(tmp_path):
    """Técnica Aider (cascada de match tolerante): si el SEARCH no calza exacto
    por indentación pero SÍ línea a línea ignorando whitespace, se aplica
    respetando la indentación real del archivo."""
    f = tmp_path / "foo.py"
    f.write_text("class Foo:\n    def bar(self):\n        return 'old'\n")

    # El modelo manda el bloque con MENOS indentación de la real (2 espacios en
    # vez de 8) — un match exacto fallaría, pero línea a línea (stripped) calza.
    hub = _make_hub(_sr_block("return 'old'", "return 'new'"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia el valor de retorno",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    content = f.read_text()
    assert "return 'new'" in content
    # La indentación real del archivo (8 espacios) se preserva
    assert "        return 'new'" in content


def test_code_rejects_ambiguous_reindent_match(tmp_path):
    """Si hay >1 ventana que calza línea-a-línea (ignorando whitespace) y el
    match exacto NO existe (count==0), el fallback tolerante debe rechazar por
    ambigüedad — fail-closed, no adivinar cuál de las dos es la correcta."""
    f = tmp_path / "foo.py"
    original = "  y = 5\n    y = 5\n"
    f.write_text(original)

    # Indentación con tab: no calza EXACTO en ninguna línea (count==0), pero
    # sí calza línea-a-línea ignorando whitespace en AMBAS líneas → ambiguo.
    hub = _make_hub(_sr_block("\ty = 5", "y = 6"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea con SEARCH ambiguo tras normalizar indentación",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert f.read_text() == original


def test_code_applies_multiple_blocks(tmp_path):
    fa = tmp_path / "a.py"
    fb = tmp_path / "b.py"
    fa.write_text("A_OLD = 1\n")
    fb.write_text("B_OLD = 2\n")

    two_blocks = (
        _sr_block("A_OLD = 1", "A_NEW = 1")
        + "\n\n"
        + _sr_block("B_OLD = 2", "B_NEW = 2")
    )
    hub = _make_hub(two_blocks)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="actualiza ambas constantes",
        context_files=["a.py", "b.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert "A_NEW" in fa.read_text()
    assert "B_NEW" in fb.read_text()


# ---------------------------------------------------------------------------
# Slice 2 — contexto institucional inyectado en el prompt
# ---------------------------------------------------------------------------

def _stub_hub():
    """Hub mínimo que devuelve respuesta vacía (sin edits)."""
    return _make_hub("")


class TestInstitutionalContext:
    """Slice 2 — contexto institucional inyectado en el prompt."""

    def test_institutional_section_reads_agents_md(self, tmp_path):
        """AGENTS.md existente aparece en la sección institucional."""
        (tmp_path / "AGENTS.md").write_text("# manía: no hacer X\n", encoding="utf-8")
        coder = AtlasCoder(hub=_stub_hub(), repo_root=tmp_path)
        section = coder._build_institutional_section()
        assert "AGENTS.md" in section
        assert "manía: no hacer X" in section

    def test_institutional_section_empty_if_no_files(self, tmp_path):
        """Sin archivos institucionales → sección vacía (prompt no se rompe)."""
        coder = AtlasCoder(hub=_stub_hub(), repo_root=tmp_path)
        section = coder._build_institutional_section()
        assert section == ""

    def test_institutional_section_truncates_long_files(self, tmp_path):
        """Archivos > 3000 chars se truncan para no saturar el contexto."""
        (tmp_path / "AGENTS.md").write_text("x" * 5000, encoding="utf-8")
        coder = AtlasCoder(hub=_stub_hub(), repo_root=tmp_path)
        section = coder._build_institutional_section()
        assert "[truncado]" in section
        assert len(section) < 4500

    def test_institutional_section_override_per_call(self, tmp_path):
        """institutional_context_files en code() sobreescribe el valor del constructor."""
        (tmp_path / "custom.md").write_text("# custom context\n", encoding="utf-8")
        target = tmp_path / "foo.py"
        target.write_text("x = 1\n", encoding="utf-8")

        captured_prompts: list[str] = []

        class _CapturingHub:
            def infer(self, req):
                captured_prompts.append(req.prompt)
                from atlas.core.inference_hub import InferenceResponse, InferenceLevel
                return InferenceResponse(
                    success=True, text="", provider="stub", model="stub",
                    level=InferenceLevel.L1, latency_ms=0,
                )

            def infer_for_role(self, role, req):
                return self.infer(req)

        coder = AtlasCoder(hub=_CapturingHub(), repo_root=tmp_path)
        coder.code(
            task="tarea test",
            context_files=["foo.py"],
            test_cmd=["python", "-c", "exit(0)"],
            max_iterations=1,
            institutional_context_files=["custom.md"],
        )
        assert captured_prompts, "El hub debería haber recibido al menos un prompt"
        assert "custom context" in captured_prompts[0]
        assert "AGENTS.md" not in captured_prompts[0]

    def test_institutional_file_with_matching_conditional_rule_included(self, tmp_path):
        """Técnica #11 cableada (2026-07-02, cross-audit Cursor): un archivo
        institucional con frontmatter applies_to se incluye si algún
        context_file matchea, y el frontmatter se filtra del prompt."""
        (tmp_path / "custom.md").write_text(
            "---\napplies_to: [\"*.py\"]\n---\nregla condicional python\n",
            encoding="utf-8",
        )
        coder = AtlasCoder(
            hub=_stub_hub(), repo_root=tmp_path,
            institutional_context_files=["custom.md"],
        )
        section = coder._build_institutional_section(context_files=["src/foo.py"])
        assert "regla condicional python" in section
        assert "applies_to" not in section

    def test_institutional_file_with_non_matching_conditional_rule_excluded(self, tmp_path):
        (tmp_path / "custom.md").write_text(
            "---\napplies_to: [\"*.rs\"]\n---\nregla solo rust\n",
            encoding="utf-8",
        )
        coder = AtlasCoder(
            hub=_stub_hub(), repo_root=tmp_path,
            institutional_context_files=["custom.md"],
        )
        section = coder._build_institutional_section(context_files=["src/foo.py"])
        assert section == ""


# ---------------------------------------------------------------------------
# Técnica #1 — linter bloqueante (patrón SWE-agent str_replace_editor)
# ---------------------------------------------------------------------------

def test_code_rejects_edit_that_breaks_python_syntax(tmp_path):
    """Si la edición produce un SyntaxError, se rechaza (no se escribe) y el
    archivo queda intacto — no se aplica código roto aunque el SEARCH calce."""
    f = tmp_path / "foo.py"
    f.write_text("def hello():\n    return 1\n")

    # El REPLACE es sintácticamente inválido (paréntesis sin cerrar).
    hub = _make_hub(_sr_block("return 1", "return foo(("))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea que produce syntax error",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True  # el bloque se rechaza, no se aplica; test_cmd=true igual pasa
    assert f.read_text() == "def hello():\n    return 1\n"


def test_code_accepts_valid_python_edit(tmp_path):
    """Control: una edición sintácticamente válida SÍ se aplica (el linter no
    bloquea código correcto)."""
    f = tmp_path / "foo.py"
    f.write_text("def hello():\n    return 1\n")

    hub = _make_hub(_sr_block("return 1", "return 2"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia el valor de retorno",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert "return 2" in f.read_text()


def test_code_ignores_syntax_check_for_non_python_files(tmp_path):
    """Archivos no-.py no pasan por el linter — cualquier texto se acepta."""
    f = tmp_path / "notes.md"
    f.write_text("# old title\n")

    hub = _make_hub(_sr_block("# old title", "# ((( invalid python but valid md"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia el título",
        context_files=["notes.md"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert "invalid python but valid md" in f.read_text()


# ---------------------------------------------------------------------------
# Técnica #12/#19 — rutas protegidas (fail-closed, sin excepción)
# ---------------------------------------------------------------------------

def test_code_rejects_protected_git_path(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")

    hub = _make_hub(_sr_block("[core]", "[core]\nmalicious = true"))
    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="intenta editar .git/config",
        context_files=[".git/config"],
        test_cmd=["true"],
    )

    assert result.success is False
    assert "protegidas" in result.error
    assert result.iterations == 0  # rechazado ANTES de llamar al modelo
    hub.infer.assert_not_called()
    hub.infer_for_role.assert_not_called()


def test_code_rejects_protected_env_path(tmp_path):
    (tmp_path / ".env").write_text("SECRET=123\n")

    hub = _make_hub(_sr_block("SECRET=123", "SECRET=456"))
    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="intenta editar .env",
        context_files=[".env"],
        test_cmd=["true"],
    )

    assert result.success is False
    assert "protegidas" in result.error
    assert (tmp_path / ".env").read_text() == "SECRET=123\n"


def test_code_allows_normal_paths_alongside_protected_check(tmp_path):
    """Control: rutas normales no se bloquean por el guard de rutas protegidas."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _make_hub(_sr_block("x = 1", "x = 2"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert "x = 2" in f.read_text()


# ---------------------------------------------------------------------------
# Técnica #14 — repo-map (firmas + PageRank) inyectado en el prompt
# ---------------------------------------------------------------------------

def test_code_injects_repo_map_when_requested(tmp_path):
    """repo_map_files construye el mapa e inyecta las firmas de símbolos
    referenciados fuera de context_files."""
    (tmp_path / "utils.py").write_text("def helper(x):\n    return x * 2\n")
    target = tmp_path / "main.py"
    target.write_text("from utils import helper\nresult = helper(1)\n")

    captured_prompts: list[str] = []

    class _CapturingHub:
        def infer(self, req):
            captured_prompts.append(req.prompt)
            from atlas.core.inference_hub import InferenceResponse, InferenceLevel
            return InferenceResponse(
                success=True, text="", provider="stub", model="stub",
                level=InferenceLevel.L1, latency_ms=0,
            )

        def infer_for_role(self, role, req):
            return self.infer(req)

    coder = AtlasCoder(hub=_CapturingHub(), repo_root=tmp_path)
    coder.code(
        task="tarea test",
        context_files=["main.py"],
        test_cmd=["true"],
        max_iterations=1,
        repo_map_files=["main.py", "utils.py"],
    )

    assert captured_prompts
    assert "Mapa del repo" in captured_prompts[0]
    assert "def helper(x)" in captured_prompts[0]


def test_code_omits_repo_map_section_by_default(tmp_path):
    """Sin repo_map_files (default None), no se escanea nada — opt-in explícito."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _make_hub(_sr_block("x = 1", "x = 2"))

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea sin repo-map",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True  # comportamiento normal, sin cambios


# ---------------------------------------------------------------------------
# Técnica #18 — edit_format="apply_patch" (envelope OpenAI Codex CLI / Cline)
# ---------------------------------------------------------------------------

def _patch_hub(patch_text: str, success: bool = True):
    hub = MagicMock()
    resp = MagicMock()
    resp.success = success
    resp.text = patch_text
    resp.error = None if success else "error de prueba"
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def test_code_apply_patch_updates_existing_file(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def hello():\n    return 'old'\n")

    patch = (
        "*** Begin Patch\n"
        "*** Update File: foo.py\n"
        "@@\n"
        " def hello():\n"
        "-    return 'old'\n"
        "+    return 'new'\n"
        "*** End Patch\n"
    )
    hub = _patch_hub(patch)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia el valor de retorno",
        context_files=["foo.py"],
        test_cmd=["true"],
        edit_format="apply_patch",
    )

    assert result.success is True
    assert "return 'new'" in f.read_text()


def test_code_apply_patch_adds_new_file(tmp_path):
    patch = (
        "*** Begin Patch\n"
        "*** Add File: nuevo.py\n"
        "+x = 1\n"
        "*** End Patch\n"
    )
    hub = _patch_hub(patch)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="crea un archivo nuevo",
        context_files=[],
        test_cmd=["true"],
        edit_format="apply_patch",
    )

    assert result.success is True
    assert (tmp_path / "nuevo.py").read_text() == "x = 1\n"


def test_code_apply_patch_deletes_file(tmp_path):
    (tmp_path / "gone.py").write_text("x = 1\n")
    patch = "*** Begin Patch\n*** Delete File: gone.py\n*** End Patch\n"
    hub = _patch_hub(patch)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="borra el archivo",
        context_files=[],
        test_cmd=["true"],
        edit_format="apply_patch",
    )

    assert result.success is True
    assert not (tmp_path / "gone.py").exists()


def test_code_apply_patch_rejects_protected_path(tmp_path):
    patch = (
        "*** Begin Patch\n"
        "*** Add File: .env\n"
        "+SECRET=leaked\n"
        "*** End Patch\n"
    )
    hub = _patch_hub(patch)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="intenta crear .env",
        context_files=[],
        test_cmd=["true"],
        edit_format="apply_patch",
    )

    assert result.success is True  # la operación se ignora, no falla el run
    assert not (tmp_path / ".env").exists()


def test_code_apply_patch_lint_gate_rejects_broken_syntax(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: foo.py\n"
        "@@\n"
        "-x = 1\n"
        "+x = ((( broken\n"
        "*** End Patch\n"
    )
    hub = _patch_hub(patch)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="edición que rompe sintaxis",
        context_files=["foo.py"],
        test_cmd=["true"],
        edit_format="apply_patch",
    )

    assert result.success is True
    assert f.read_text() == "x = 1\n"  # no se escribió el contenido roto


def test_code_rejects_invalid_edit_format(tmp_path):
    hub = _patch_hub("")
    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea", context_files=[], test_cmd=["true"], edit_format="xml",
    )
    assert result.success is False
    assert "edit_format" in result.error


# ---------------------------------------------------------------------------
# Técnica #4 — apply-model separado (Cursor/Continue/Aider architect/Cline Plan-Act)
# ---------------------------------------------------------------------------

class _TwoCallHub:
    """Hub que distingue la llamada de edición (infer_for_role edit) de la
    llamada del apply-model (infer_for_role apply)."""

    def __init__(self, edit_text: str, apply_text: str):
        self._edit_text = edit_text
        self._apply_text = apply_text
        self.apply_calls = 0

    def infer(self, req):
        return self.infer_for_role("edit", req)

    def infer_for_role(self, role, req):
        from atlas.core.inference_hub import InferenceResponse, InferenceLevel
        if role == "apply":
            self.apply_calls += 1
            text = self._apply_text
        else:
            text = self._edit_text
        return InferenceResponse(
            success=True, text=text, provider="stub", model="stub",
            level=InferenceLevel.L1, latency_ms=0,
        )


def test_code_apply_model_fallback_rescues_failed_search_block(tmp_path):
    """Si el SEARCH no calza y use_apply_model=True + 1 solo context_file,
    delega en el modelo apply que reescribe el archivo completo."""
    f = tmp_path / "foo.py"
    f.write_text("def hello():\n    return 'old'\n")

    edit_text = _sr_block("texto_que_no_calza_nunca", "reemplazo")
    apply_text = "def hello():\n    return 'new'\n"
    hub = _TwoCallHub(edit_text, apply_text)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia el valor de retorno",
        context_files=["foo.py"],
        test_cmd=["true"],
        use_apply_model=True,
    )

    assert result.success is True
    assert "return 'new'" in f.read_text()
    assert hub.apply_calls == 1


def test_code_apply_model_fallback_disabled_by_default(tmp_path):
    """Sin use_apply_model=True (default), un SEARCH fallido NO invoca el
    modelo apply — comportamiento idéntico al anterior."""
    f = tmp_path / "foo.py"
    f.write_text("def hello():\n    return 'old'\n")

    edit_text = _sr_block("texto_que_no_calza_nunca", "reemplazo")
    hub = _TwoCallHub(edit_text, "no debería llamarse")

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea con bloque inválido",
        context_files=["foo.py"],
        test_cmd=["true"],
    )

    assert result.success is True
    assert hub.apply_calls == 0
    assert f.read_text() == "def hello():\n    return 'old'\n"


def test_code_apply_model_fallback_skipped_with_multiple_files(tmp_path):
    """Con más de 1 context_file, el fallback se salta (evita ambigüedad de
    a qué archivo pertenece el bloque fallido) — no llama al modelo apply."""
    fa = tmp_path / "a.py"
    fb = tmp_path / "b.py"
    fa.write_text("x = 1\n")
    fb.write_text("y = 1\n")

    edit_text = _sr_block("texto_que_no_calza_nunca", "reemplazo")
    hub = _TwoCallHub(edit_text, "no debería llamarse")

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea con bloque inválido y 2 archivos",
        context_files=["a.py", "b.py"],
        test_cmd=["true"],
        use_apply_model=True,
    )

    assert result.success is True
    assert hub.apply_calls == 0


def test_code_apply_model_fallback_respects_lint_gate(tmp_path):
    """Si el modelo apply produce sintaxis rota, no se escribe (mismo linter
    bloqueante de siempre)."""
    f = tmp_path / "foo.py"
    original = "x = 1\n"
    f.write_text(original)

    edit_text = _sr_block("texto_que_no_calza_nunca", "reemplazo")
    apply_text = "x = ((( broken\n"
    hub = _TwoCallHub(edit_text, apply_text)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea con apply-model que rompe sintaxis",
        context_files=["foo.py"],
        test_cmd=["true"],
        use_apply_model=True,
    )

    assert result.success is True
    assert f.read_text() == original


# ---------------------------------------------------------------------------
# _run_council — fix synthesis_recorder (Cónclave nunca destilaba veredictos)
# ---------------------------------------------------------------------------


def test_run_council_passes_synthesis_recorder_when_lesson_store_present(tmp_path):
    from unittest.mock import patch
    from atlas.core.lesson_store import LessonStore

    store = LessonStore(tmp_path / "lessons")
    coder = AtlasCoder(MagicMock(), repo_root=tmp_path, lesson_store=store)

    captured = {}

    def _fake_convene(*args, **kwargs):
        captured.update(kwargs)
        from atlas.core.verify import Evidence, Verdict
        return Evidence(verdict=Verdict.PASS)

    with patch("atlas.core.deliberation_council.convene_for_decision", _fake_convene):
        coder._run_council("tarea", "contexto")

    assert "synthesis_recorder" in captured
    assert captured["synthesis_recorder"] is not None


def test_run_council_passes_none_recorder_without_lesson_store(tmp_path):
    from unittest.mock import patch

    coder = AtlasCoder(MagicMock(), repo_root=tmp_path)  # sin lesson_store

    captured = {}

    def _fake_convene(*args, **kwargs):
        captured.update(kwargs)
        from atlas.core.verify import Evidence, Verdict
        return Evidence(verdict=Verdict.PASS)

    with patch("atlas.core.deliberation_council.convene_for_decision", _fake_convene):
        coder._run_council("tarea", "contexto")

    assert captured.get("synthesis_recorder") is None
