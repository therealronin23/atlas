"""
Tests de verificación — Tarea D (técnica #20, Codex CLI): descubrimiento
jerárquico de archivos institucionales — además de los del repo_root, si
existe un AGENTS.md en el directorio del PRIMER context_file (o ancestros
entre medias hasta repo_root), también se incluye (el más específico gana
posición al final = mayor prioridad de lectura).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.core.atlas_coder import AtlasCoder


def _stub_hub():
    hub = MagicMock()
    resp = MagicMock()
    resp.success = True
    resp.text = ""
    resp.error = None
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def test_discovers_agents_md_in_subdirectory(tmp_path):
    """AGENTS.md en el subdirectorio del context_file se descubre además del raíz."""
    (tmp_path / "AGENTS.md").write_text("# regla raiz\n", encoding="utf-8")
    sub = tmp_path / "src" / "modulo"
    sub.mkdir(parents=True)
    (sub / "AGENTS.md").write_text("# regla especifica del modulo\n", encoding="utf-8")
    (sub / "code.py").write_text("x = 1\n", encoding="utf-8")

    coder = AtlasCoder(hub=_stub_hub(), repo_root=tmp_path)
    section = coder._build_institutional_section(
        context_files=["src/modulo/code.py"]
    )

    assert "regla raiz" in section
    assert "regla especifica del modulo" in section


def test_no_subdirectory_agents_md_keeps_current_behavior(tmp_path):
    """Sin AGENTS.md en subdirectorios, comportamiento idéntico al actual."""
    (tmp_path / "AGENTS.md").write_text("# solo raiz\n", encoding="utf-8")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "code.py").write_text("x = 1\n", encoding="utf-8")

    coder = AtlasCoder(hub=_stub_hub(), repo_root=tmp_path)
    section = coder._build_institutional_section(context_files=["src/code.py"])

    assert "solo raiz" in section
    assert section.count("### ") == 1  # solo un archivo institucional


def test_without_context_files_argument_backwards_compatible(tmp_path):
    """Llamar sin context_files (firma antigua) sigue funcionando."""
    (tmp_path / "AGENTS.md").write_text("# raiz\n", encoding="utf-8")
    coder = AtlasCoder(hub=_stub_hub(), repo_root=tmp_path)
    section = coder._build_institutional_section()
    assert "raiz" in section
