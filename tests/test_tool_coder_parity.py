"""
ToolCoder — paridad con AtlasCoder para las técnicas que SÍ aplican al
tool-calling (repo_map #14, git auto-commit #16). apply-model (#4) y
edit_format alternativo (#18) son MOOT para ToolCoder: resuelven problemas
específicos de la completación de texto (SEARCH/REPLACE mal aplicado,
delimitadores corruptos) que no existen cuando el formato lo valida la API.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from atlas.core.tool_coder import ToolCoder
from tests.test_tool_coder import _tc


class _CapturingHub:
    def __init__(self):
        self.requests = []

    def infer(self, req):
        from atlas.core.inference_hub import InferenceResponse, InferenceLevel
        self.requests.append(req)
        return InferenceResponse(
            success=True, text="listo", provider="stub", model="stub",
            level=InferenceLevel.L1, latency_ms=0, tool_calls=[],
        )

    def infer_for_role(self, role, req):
        return self.infer(req)


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "foo.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_code_injects_repo_map_when_requested(tmp_path: Path):
    (tmp_path / "utils.py").write_text("def helper(x):\n    return x * 2\n")
    (tmp_path / "main.py").write_text("from utils import helper\nresult = helper(1)\n")

    hub = _CapturingHub()
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(
        task="tarea test", context_files=["main.py"], test_cmd=["true"],
        max_iterations=1, repo_map_files=["main.py", "utils.py"],
    )

    assert hub.requests
    content = hub.requests[0].messages[0]["content"]
    assert "Mapa del repo" in content
    assert "def helper(x)" in content


def test_code_omits_repo_map_section_by_default(tmp_path: Path):
    (tmp_path / "foo.py").write_text("x = 1\n")
    hub = _CapturingHub()
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="tarea sin repo-map", context_files=["foo.py"], test_cmd=["true"], max_iterations=1)

    assert hub.requests
    content = hub.requests[0].messages[0]["content"]
    assert "Mapa del repo" not in content


def test_auto_commit_creates_commit_on_success(tmp_path: Path):
    repo = _git_repo(tmp_path)

    class _Hub:
        def __init__(self):
            self._i = 0

        def infer(self, req):
            from atlas.core.inference_hub import InferenceResponse, InferenceLevel
            self._i += 1
            if self._i == 1:
                tc = _tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")
                return InferenceResponse(
                    success=True, text="", provider="stub", model="stub",
                    level=InferenceLevel.L1, latency_ms=0, tool_calls=[tc],
                )
            return InferenceResponse(
                success=True, text="listo", provider="stub", model="stub",
                level=InferenceLevel.L1, latency_ms=0, tool_calls=[],
            )

        def infer_for_role(self, role, req):
            return self.infer(req)

    coder = ToolCoder(_Hub(), repo_root=repo)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"], auto_commit=True,
    )

    assert result.success is True
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "[atlas-coder]" in log
    assert "cambia x" in log


def test_institutional_section_reads_agents_md(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("# manía: no hacer X\n", encoding="utf-8")
    coder = ToolCoder(hub=_CapturingHub(), repo_root=tmp_path)
    section = coder._build_institutional_section()
    assert "AGENTS.md" in section
    assert "manía: no hacer X" in section


def test_institutional_section_empty_if_no_files(tmp_path: Path):
    coder = ToolCoder(hub=_CapturingHub(), repo_root=tmp_path)
    section = coder._build_institutional_section()
    assert section == ""


def test_institutional_section_truncates_long_files(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("x" * 5000, encoding="utf-8")
    coder = ToolCoder(hub=_CapturingHub(), repo_root=tmp_path)
    section = coder._build_institutional_section()
    assert "[truncado]" in section
    assert len(section) < 4500


def test_institutional_section_discovers_hierarchical_agents_md(tmp_path: Path):
    """Técnica #20 (Codex CLI), confirmada dos veces más en el cross-audit
    2026-07-02 (Codex agents_md.rs, Cursor AGENTS.md anidado): además del
    AGENTS.md raíz, se incluye el de los directorios ancestros del primer
    context_file — el más específico gana posición al final."""
    (tmp_path / "AGENTS.md").write_text("regla raiz\n", encoding="utf-8")
    sub = tmp_path / "src" / "modulo"
    sub.mkdir(parents=True)
    (sub / "AGENTS.md").write_text("regla especifica del modulo\n", encoding="utf-8")
    (sub / "code.py").write_text("x = 1\n", encoding="utf-8")

    coder = ToolCoder(hub=_CapturingHub(), repo_root=tmp_path)
    section = coder._build_institutional_section(context_files=["src/modulo/code.py"])

    assert "regla raiz" in section
    assert "regla especifica del modulo" in section


def test_institutional_section_injected_in_prompt(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("# custom institutional\n", encoding="utf-8")
    (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")

    hub = _CapturingHub()
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="tarea", context_files=["foo.py"], test_cmd=["true"], max_iterations=1)

    assert hub.requests
    content = hub.requests[0].messages[0]["content"]
    assert "custom institutional" in content


def test_institutional_file_with_matching_conditional_rule_included(tmp_path: Path):
    (tmp_path / "custom.md").write_text(
        "---\napplies_to: [\"*.py\"]\n---\nregla condicional python\n", encoding="utf-8",
    )
    coder = ToolCoder(
        hub=_CapturingHub(), repo_root=tmp_path,
        institutional_context_files=["custom.md"],
    )
    section = coder._build_institutional_section(context_files=["src/foo.py"])
    assert "regla condicional python" in section
    assert "applies_to" not in section


def test_institutional_file_with_non_matching_conditional_rule_excluded(tmp_path: Path):
    (tmp_path / "custom.md").write_text(
        "---\napplies_to: [\"*.rs\"]\n---\nregla solo rust\n", encoding="utf-8",
    )
    coder = ToolCoder(
        hub=_CapturingHub(), repo_root=tmp_path,
        institutional_context_files=["custom.md"],
    )
    section = coder._build_institutional_section(context_files=["src/foo.py"])
    assert section == ""


def test_auto_commit_disabled_by_default(tmp_path: Path):
    repo = _git_repo(tmp_path)

    class _Hub:
        def __init__(self):
            self._i = 0

        def infer(self, req):
            from atlas.core.inference_hub import InferenceResponse, InferenceLevel
            self._i += 1
            if self._i == 1:
                tc = _tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")
                return InferenceResponse(
                    success=True, text="", provider="stub", model="stub",
                    level=InferenceLevel.L1, latency_ms=0, tool_calls=[tc],
                )
            return InferenceResponse(
                success=True, text="listo", provider="stub", model="stub",
                level=InferenceLevel.L1, latency_ms=0, tool_calls=[],
            )

        def infer_for_role(self, role, req):
            return self.infer(req)

    coder = ToolCoder(_Hub(), repo_root=repo)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"])

    assert result.success is True
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "[atlas-coder]" not in log
