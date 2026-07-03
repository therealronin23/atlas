"""Tests for src/atlas/core/self_maintenance/self_build_runner.py."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from atlas.core.self_maintenance.backlog import BacklogItem
from atlas.core.self_maintenance.self_build_runner import SelfBuildRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(**overrides: object) -> BacklogItem:
    base: dict[str, object] = dict(
        id="f2-6a-caller-wiring-personal-factual",
        title="f2-6 follow-up: cablear memory_class",
        why="Sin cablear, la capacidad es teórica.",
        targets=("src/atlas/knowledge/", "src/atlas/mcp/memory_trunk.py"),
        acceptance="rutas add_from_knowledge_src/add_from_user_preference; suite verde.",
        priority=2,
        status="pending",
        test_cmd=None,
    )
    base.update(overrides)
    return BacklogItem(**base)  # type: ignore[arg-type]


def _write_backlog_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "backlog.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# derive_test_cmd
# ---------------------------------------------------------------------------


def test_derive_test_cmd_uses_explicit_field(tmp_path: Path) -> None:
    """Si el BacklogItem trae test_cmd explícito, se usa tal cual."""
    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item(test_cmd=("pytest", "tests/test_explicit.py", "-q"))

    cmd = runner.derive_test_cmd(item)

    assert cmd == ["pytest", "tests/test_explicit.py", "-q"]


def test_derive_test_cmd_finds_convention_named_test(tmp_path: Path) -> None:
    """Sin test_cmd explícito: busca tests/test_{id con guiones->guion_bajo}*.py."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    expected_name = "test_f2_6a_caller_wiring_personal_factual.py"
    (tests_dir / expected_name).write_text("def test_x(): pass\n", encoding="utf-8")

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item()

    cmd = runner.derive_test_cmd(item)

    assert cmd == ["pytest", f"tests/{expected_name}", "-q"]


def test_derive_test_cmd_falls_back_to_full_suite(tmp_path: Path) -> None:
    """Sin test_cmd explícito y sin test específico por convención: suite completa."""
    (tmp_path / "tests").mkdir()

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item()

    cmd = runner.derive_test_cmd(item)

    assert cmd == ["pytest", "-q"]


# ---------------------------------------------------------------------------
# run_item
# ---------------------------------------------------------------------------


def test_run_item_success_calls_propose_with_self_audit_origin(tmp_path: Path) -> None:
    """CodeCycle/ToolCoder exitoso -> propose() con origin=self_audit y evidence."""
    (tmp_path / "tests").mkdir()
    # Simular un repo git real minimo para que git diff funcione dentro de run_item.
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    # Cambio real no comiteado, simulando lo que dejaría ToolCoder tras editar.
    (tmp_path / "README.md").write_text("hello\nmodified\n", encoding="utf-8")

    fake_coder_result = MagicMock()
    fake_coder_result.success = True
    fake_coder_result.iterations = 1
    fake_coder_result.files_changed = ["README.md"]
    fake_coder_result.test_output = "1 passed"
    fake_coder_result.error = None

    tool_coder_cls = MagicMock()
    tool_coder_cls.return_value.code.return_value = fake_coder_result

    cold_update_manager = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-123"
    cold_update_manager.propose.return_value = proposal

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=tool_coder_cls,
    )
    item = _item()

    result = runner.run_item(item)

    assert result["status"] == "proposed"
    assert result["item_id"] == item.id
    assert result["proposal_id"] == "proposal-123"

    cold_update_manager.propose.assert_called_once()
    _, kwargs = cold_update_manager.propose.call_args
    assert kwargs["origin"] == "self_audit"
    assert kwargs["evidence"]["backlog_item_id"] == item.id
    assert "cycle_result" in kwargs["evidence"]


def test_expand_targets_directory_becomes_py_files(tmp_path: Path) -> None:
    """Un target que termina en '/' (directorio) se expande a sus .py — ToolCoder
    espera rutas de fichero, no directorios (bug real encontrado al correr en vivo)."""
    pkg = tmp_path / "src" / "atlas" / "knowledge"
    pkg.mkdir(parents=True)
    (pkg / "base.py").write_text("", encoding="utf-8")
    (pkg / "sources.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    expanded = runner._expand_targets(("src/atlas/knowledge/", "src/atlas/mcp/memory_trunk.py"))

    assert "src/atlas/mcp/memory_trunk.py" in expanded
    assert all(not t.endswith("/") for t in expanded)
    assert "src/atlas/knowledge/base.py" in expanded
    assert "src/atlas/knowledge/sources.py" in expanded
    assert "src/atlas/knowledge/__init__.py" in expanded


def test_run_item_failure_reverts_dirty_files_left_by_tool_coder(tmp_path: Path) -> None:
    """Bug real encontrado en vivo: si ToolCoder ensucia ficheros (trackeados o
    nuevos) durante un intento que termina fallando, run_item debe dejar el
    árbol de trabajo EXACTAMENTE como estaba — nunca residuos a medias."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.py"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    def _dirty_side_effect(*args: object, **kwargs: object) -> MagicMock:
        # Simula lo que hizo ToolCoder en vivo: tocar un fichero fuera del
        # alcance del item Y modificar uno trackeado, antes de fallar.
        tracked.write_text("modificado a medias\n", encoding="utf-8")
        (tmp_path / "leftover_untracked.py").write_text("residuo\n", encoding="utf-8")
        fake = MagicMock()
        fake.success = False
        fake.iterations = 3
        fake.files_changed = []
        fake.test_output = "FAILED"
        fake.error = "tests no pasaron"
        return fake

    tool_coder_cls = MagicMock()
    tool_coder_cls.return_value.code.side_effect = _dirty_side_effect

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
        tool_coder_factory=tool_coder_cls,
    )
    result = runner.run_item(_item())

    assert result["status"] == "failed"
    assert tracked.read_text(encoding="utf-8") == "original\n"
    assert not (tmp_path / "leftover_untracked.py").exists()


def test_run_item_failure_does_not_call_propose(tmp_path: Path) -> None:
    """Resultado fallido de ToolCoder -> NUNCA llama a propose(); status=failed."""
    (tmp_path / "tests").mkdir()

    fake_coder_result = MagicMock()
    fake_coder_result.success = False
    fake_coder_result.iterations = 3
    fake_coder_result.files_changed = []
    fake_coder_result.test_output = "FAILED tests/test_x.py"
    fake_coder_result.error = "tests no pasaron"

    tool_coder_cls = MagicMock()
    tool_coder_cls.return_value.code.return_value = fake_coder_result

    cold_update_manager = MagicMock()

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=tool_coder_cls,
    )
    item = _item()

    result = runner.run_item(item)

    assert result["status"] == "failed"
    assert result["item_id"] == item.id
    assert result["proposal_id"] is None
    assert "detail" in result
    cold_update_manager.propose.assert_not_called()


# ---------------------------------------------------------------------------
# update_backlog_status
# ---------------------------------------------------------------------------


def test_update_backlog_status_changes_only_target_item(tmp_path: Path) -> None:
    """Reescribe SOLO el status del item indicado; el resto del YAML intacto."""
    backlog_path = _write_backlog_yaml(
        tmp_path,
        """\
        items:
          - id: item-a
            title: "Item A"
            why: "reason A"
            targets: ["src/foo.py"]
            acceptance: "acc A"
            priority: 2
            status: pending
          - id: item-b
            title: "Item B"
            why: "reason B"
            targets: ["src/bar.py"]
            acceptance: "acc B"
            priority: 1
            status: pending
        """,
    )
    before = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
        backlog_path=backlog_path,
    )
    runner.update_backlog_status("item-b", "doing")

    after = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))

    # Solo item-b cambia de status; item-a y el resto de campos de item-b intactos.
    assert after["items"][0] == before["items"][0]
    assert after["items"][1]["status"] == "doing"
    changed_b = dict(after["items"][1])
    del changed_b["status"]
    original_b = dict(before["items"][1])
    del original_b["status"]
    assert changed_b == original_b
