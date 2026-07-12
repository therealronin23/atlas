"""Tests for src/atlas/core/self_maintenance/self_build_runner.py."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest
import yaml

from atlas.core.self_maintenance.backlog import BacklogItem
from atlas.core.self_maintenance.self_build_runner import (
    SelfBuildRunner,
    _write_worktree_evaluator_file,
)

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


def _init_repo(tmp_path: Path, files: dict[str, str]) -> None:
    """Repo git real minimo con `files` commiteados en HEAD."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)


def _coder_result(
    *,
    success: bool,
    files_changed: list[str] | None = None,
    error: str | None = None,
) -> MagicMock:
    fake = MagicMock()
    fake.success = success
    fake.iterations = 1
    fake.files_changed = files_changed or []
    fake.test_output = "1 passed" if success else "FAILED"
    fake.error = error
    fake.suspicious_no_op = False
    return fake


class _RecordingCoderFactory:
    """Doble de tool_coder_factory: captura el repo_root que recibe ToolCoder
    y ejecuta on_code(repo_root) como side effect real de coder.code()."""

    def __init__(self, on_code: Callable[[Path], MagicMock]) -> None:
        self._on_code = on_code
        self.repo_roots: list[Path] = []
        self.code_calls = 0

    def __call__(self, hub: object, *, repo_root: Path) -> MagicMock:
        root = Path(repo_root)
        self.repo_roots.append(root)
        coder = MagicMock()

        def _code(*args: object, **kwargs: object) -> MagicMock:
            self.code_calls += 1
            return self._on_code(root)

        coder.code.side_effect = _code
        return coder


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


def test_derive_test_cmd_resolves_bare_python_to_sys_executable(tmp_path: Path) -> None:
    """`python` a pelo NO existe en este sistema (solo python3/venv) — tercera
    aparición del mismo bug (install del catálogo del tronco, y el test_cmd
    que otra sesión escribió en backlog.yaml la noche del 2026-07-10, con dos
    fallos reales 'test_cmd no encontrado'). Un test_cmd explícito que empiece
    por python/python3 se resuelve a sys.executable; el resto se respeta."""
    import sys

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item(test_cmd=("python", "-m", "mypy", "src/atlas/"))

    cmd = runner.derive_test_cmd(item)

    assert cmd == [sys.executable, "-m", "mypy", "src/atlas/"]


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

    # sys.executable -m pytest, no "pytest" a pelo: la colección de la suite
    # depende de cwd en sys.path (2026-07-09, tests/benchmarks importa scripts)
    assert cmd == [sys.executable, "-m", "pytest", f"tests/{expected_name}", "-q"]


def test_derive_test_cmd_maps_file_target(tmp_path: Path) -> None:
    """Sin test_cmd explícito y sin match por id: si un target es un
    fichero .py, se mapea a tests/test_{stem}*.py (2026-07-10, entre el
    glob por id y el fallback a suite completa)."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_memory_trunk.py").write_text("def test_x(): pass\n", encoding="utf-8")

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item(id="no-id-match-here", targets=("src/atlas/mcp/memory_trunk.py",))

    cmd = runner.derive_test_cmd(item)

    assert cmd == [sys.executable, "-m", "pytest", "tests/test_memory_trunk.py", "-q"]


def test_derive_test_cmd_maps_directory_target(tmp_path: Path) -> None:
    """Target-directorio (termina en '/'): mapea cada .py DIRECTO del
    directorio (sin recursión) a su test por convención."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_extractor.py").write_text("def test_x(): pass\n", encoding="utf-8")

    src_dir = tmp_path / "src" / "atlas" / "knowledge"
    src_dir.mkdir(parents=True)
    (src_dir / "extractor.py").write_text("x = 1\n", encoding="utf-8")

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item(id="no-id-match-here", targets=("src/atlas/knowledge/",))

    cmd = runner.derive_test_cmd(item)

    assert cmd == [sys.executable, "-m", "pytest", "tests/test_extractor.py", "-q"]


def test_derive_test_cmd_unions_id_glob_and_targets(tmp_path: Path) -> None:
    """El match por id (slug del item.id) y los matches por targets se
    unen, deduplicados, en un único comando pytest con ambas rutas."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    id_test_name = "test_f2_6a_caller_wiring_personal_factual.py"
    (tests_dir / id_test_name).write_text("def test_x(): pass\n", encoding="utf-8")
    (tests_dir / "test_memory_trunk.py").write_text("def test_x(): pass\n", encoding="utf-8")

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    # id por defecto de _item() coincide con id_test_name; targets por
    # defecto incluyen src/atlas/mcp/memory_trunk.py.
    item = _item()

    cmd = runner.derive_test_cmd(item)

    assert cmd == [
        sys.executable, "-m", "pytest",
        f"tests/{id_test_name}", "tests/test_memory_trunk.py", "-q",
    ]


def test_derive_test_cmd_falls_back_to_full_suite(tmp_path: Path) -> None:
    """Sin test_cmd explícito, sin match por id Y sin targets utilizables:
    suite completa con la MISMA invocación que el pre-commit (python -m
    pytest tests/), no `pytest -q` a pelo — esa colecciona benchmarks
    rotos. item() por defecto trae targets, pero ninguno resuelve a un
    test real en este tmp_path vacío, así que el fallback sigue disparando."""
    (tmp_path / "tests").mkdir()

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item()

    cmd = runner.derive_test_cmd(item)

    assert cmd == [sys.executable, "-m", "pytest", "tests/", "-q"]


# ---------------------------------------------------------------------------
# run_item
# ---------------------------------------------------------------------------


def test_run_item_success_calls_propose_with_self_audit_origin(tmp_path: Path) -> None:
    """CodeCycle/ToolCoder exitoso -> propose() con origin=self_audit y evidence."""
    (tmp_path / "tests").mkdir()
    _init_repo(tmp_path, {"README.md": "hello\n"})

    def _on_code(repo_root: Path) -> MagicMock:
        # Lo que dejaría ToolCoder tras editar — en el worktree que recibió.
        (repo_root / "README.md").write_text("hello\nmodified\n", encoding="utf-8")
        return _coder_result(success=True, files_changed=["README.md"])

    factory = _RecordingCoderFactory(_on_code)

    cold_update_manager = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-123"
    cold_update_manager.propose.return_value = proposal

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=factory,
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


def test_run_item_failure_leaves_live_tree_clean_and_no_orphan_worktrees(
    tmp_path: Path,
) -> None:
    """Un intento fallido de ToolCoder (que ensució su worktree efímero) no
    deja NI residuos en el árbol vivo NI worktrees huérfanos — la limpieza es
    destruir el worktree, no revertir el árbol vivo."""
    _init_repo(tmp_path, {"tracked.py": "original\n"})

    def _on_code(repo_root: Path) -> MagicMock:
        # ToolCoder ensucia SU worktree antes de fallar — irrelevante para el
        # árbol vivo, que ya no comparte con nadie.
        (repo_root / "tracked.py").write_text("modificado a medias\n", encoding="utf-8")
        (repo_root / "leftover_untracked.py").write_text("residuo\n", encoding="utf-8")
        return _coder_result(success=False, error="tests no pasaron")

    factory = _RecordingCoderFactory(_on_code)
    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
        tool_coder_factory=factory,
    )
    result = runner.run_item(_item())

    assert result["status"] == "failed"
    assert (tmp_path / "tracked.py").read_text(encoding="utf-8") == "original\n"
    assert not (tmp_path / "leftover_untracked.py").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    )
    assert status.stdout.strip() == ""
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    )
    assert len([ln for ln in listing.stdout.splitlines() if ln.strip()]) == 1


def test_run_item_failure_does_not_call_propose(tmp_path: Path) -> None:
    """Resultado fallido de ToolCoder -> NUNCA llama a propose(); status=failed."""
    (tmp_path / "tests").mkdir()
    _init_repo(tmp_path, {"README.md": "hello\n"})

    factory = _RecordingCoderFactory(
        lambda repo_root: _coder_result(success=False, error="tests no pasaron"),
    )
    cold_update_manager = MagicMock()

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=factory,
    )
    item = _item()

    result = runner.run_item(item)

    assert result["status"] == "failed"
    assert result["item_id"] == item.id
    assert result["proposal_id"] is None
    assert "detail" in result
    assert factory.code_calls == 1  # falló el coder, no la creación del worktree
    cold_update_manager.propose.assert_not_called()


def test_run_item_without_git_repo_fails_closed(tmp_path: Path) -> None:
    """Sin repo git no hay worktree efímero posible -> fail-closed: status
    failed SIN llegar a ejecutar ToolCoder ni proponer nada."""
    (tmp_path / "tests").mkdir()

    factory = _RecordingCoderFactory(
        lambda repo_root: _coder_result(success=True),
    )
    cold_update_manager = MagicMock()

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=factory,
    )

    result = runner.run_item(_item())

    assert result["status"] == "failed"
    assert result["proposal_id"] is None
    assert "worktree" in str(result["detail"])
    assert factory.code_calls == 0
    cold_update_manager.propose.assert_not_called()


def test_run_item_runs_tool_coder_in_ephemeral_worktree_and_patches_from_it(
    tmp_path: Path,
) -> None:
    """run_item NUNCA ejecuta ToolCoder sobre el árbol de trabajo vivo: le da
    un worktree git efímero, el patch propuesto sale de ESE worktree
    (incluyendo ficheros NUEVOS), el árbol vivo queda limpio y no sobrevive
    ningún worktree huérfano."""
    _init_repo(tmp_path, {"module.py": "x = 1\n"})

    def _on_code(repo_root: Path) -> MagicMock:
        (repo_root / "module.py").write_text("x = 2\n", encoding="utf-8")
        (repo_root / "new_helper.py").write_text("y = 3\n", encoding="utf-8")
        return _coder_result(success=True, files_changed=["module.py", "new_helper.py"])

    factory = _RecordingCoderFactory(_on_code)
    cold_update_manager = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-wt"
    cold_update_manager.propose.return_value = proposal

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=factory,
    )
    result = runner.run_item(_item())

    assert result["status"] == "proposed"
    # ToolCoder recibió un worktree efímero, no el árbol vivo.
    assert factory.repo_roots
    assert factory.repo_roots[0].resolve() != tmp_path.resolve()
    # El patch propuesto sale del worktree e incluye también el fichero nuevo.
    _, kwargs = cold_update_manager.propose.call_args
    assert kwargs["origin"] == "self_audit"
    patch_text = Path(kwargs["patch_path"]).read_text(encoding="utf-8")
    assert "x = 2" in patch_text
    assert "new_helper.py" in patch_text
    # Árbol vivo intacto y limpio.
    assert (tmp_path / "module.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (tmp_path / "new_helper.py").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    )
    assert status.stdout.strip() == ""
    # Sin worktrees huérfanos.
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    )
    assert len([ln for ln in listing.stdout.splitlines() if ln.strip()]) == 1
    # El patch es aplicable con git apply sobre HEAD (formato que consumirá
    # ColdUpdateManager._apply_patch), incluido el fichero NUEVO.
    apply_check = subprocess.run(
        ["git", "apply", "--check", str(kwargs["patch_path"])],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert apply_check.returncode == 0, apply_check.stderr


def test_run_item_failure_preserves_preexisting_operator_work_in_live_tree(
    tmp_path: Path,
) -> None:
    """Regresión del incidente '9 YAML regenerados': trabajo sin commitear que
    aparece en el árbol VIVO durante el run (un operador humano u otro agente
    concurrente) debe sobrevivir INTACTO a un run_item fallido. El antiguo
    _revert_new_changes hacía `git checkout --` / unlink() de todo lo que no
    estuviera en su baseline — destruyendo ese trabajo concurrente."""
    _init_repo(tmp_path, {"tracked.py": "original\n"})
    tracked = tmp_path / "tracked.py"

    def _on_code(repo_root: Path) -> MagicMock:
        # Trabajo concurrente del operador en el árbol VIVO, a mitad del run.
        tracked.write_text("trabajo del operador sin commitear\n", encoding="utf-8")
        (tmp_path / "operator_untracked.md").write_text(
            "apuntes del operador\n", encoding="utf-8",
        )
        return _coder_result(success=False, error="tests no pasaron")

    factory = _RecordingCoderFactory(_on_code)
    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
        tool_coder_factory=factory,
    )

    result = runner.run_item(_item())

    assert result["status"] == "failed"
    assert factory.code_calls == 1
    assert tracked.read_text(encoding="utf-8") == "trabajo del operador sin commitear\n"
    operator_untracked = tmp_path / "operator_untracked.md"
    assert operator_untracked.read_text(encoding="utf-8") == "apuntes del operador\n"


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


# ---------------------------------------------------------------------------
# run_item_with_evolution / _evaluate_candidate_in_worktree
# ---------------------------------------------------------------------------


def _init_repo_with_target(tmp_path: Path, target_rel: str, target_code: str) -> None:
    """Repo git real minimo con un fichero objetivo commiteado en HEAD."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    target_path = tmp_path / target_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(target_code, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)


_GOOD_CODE = "def add(a, b):\n    return a + b\n"
_BAD_CODE = "def add(a, b):\n    return a - b\n"

# test_cmd barato y real: importa el modulo objetivo (via sys.path) y
# verifica el contrato. Se ejecuta de verdad dentro del worktree efimero.
_TEST_CMD = [
    "python3",
    "-c",
    (
        "import sys; sys.path.insert(0, '.'); "
        "import target_mod as m; "
        "assert m.add(2, 3) == 5, 'add() incorrecto'"
    ),
]


def test_evaluate_candidate_in_worktree_scores_passing_candidate(tmp_path: Path) -> None:
    """Candidato que hace pasar el test real -> {'score': 1.0}."""
    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )

    result = runner._evaluate_candidate_in_worktree(
        "target_mod.py", _GOOD_CODE, _TEST_CMD, "HEAD",
    )

    assert result == {"score": 1.0}


def test_evaluate_candidate_in_worktree_scores_failing_candidate(tmp_path: Path) -> None:
    """Candidato que rompe el test real -> {'score': 0.0}."""
    _init_repo_with_target(tmp_path, "target_mod.py", _GOOD_CODE)

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )

    result = runner._evaluate_candidate_in_worktree(
        "target_mod.py", _BAD_CODE, _TEST_CMD, "HEAD",
    )

    assert result == {"score": 0.0}


def test_evaluate_candidate_in_worktree_always_cleans_worktree(tmp_path: Path) -> None:
    """Tras evaluar un candidato, no debe quedar ningun worktree huerfano."""
    _init_repo_with_target(tmp_path, "target_mod.py", _GOOD_CODE)

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )

    runner._evaluate_candidate_in_worktree("target_mod.py", _GOOD_CODE, _TEST_CMD, "HEAD")
    runner._evaluate_candidate_in_worktree("target_mod.py", _BAD_CODE, _TEST_CMD, "HEAD")

    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    lines = [ln for ln in listing.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1  # solo el worktree principal, ninguno efimero sobrevive


def test_run_item_with_evolution_no_targets_falls_back_without_calling_gate(tmp_path: Path) -> None:
    """Item sin targets -> cae a run_item() sin llamar a evolution_gate.evolve()."""
    (tmp_path / "tests").mkdir()
    _init_repo(tmp_path, {"README.md": "hello\n"})

    factory = _RecordingCoderFactory(
        lambda repo_root: _coder_result(success=False, error="no paso"),
    )
    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
        tool_coder_factory=factory,
    )
    item = _item(targets=())

    gate = MagicMock()

    result = runner.run_item_with_evolution(item, evolution_gate=gate)

    gate.evolve.assert_not_called()
    assert factory.code_calls == 1
    assert result["status"] == "failed"


def test_run_item_with_evolution_gate_not_succeeded_falls_back_to_run_item(tmp_path: Path) -> None:
    """evolve() devuelve succeeded=False -> cae al camino normal (ToolCoder)."""
    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)
    (tmp_path / "tests").mkdir()

    def _on_code(repo_root: Path) -> MagicMock:
        # Simula lo que haria ToolCoder de verdad: dejar un cambio real en
        # SU worktree para que git diff tenga algo que proponer.
        (repo_root / "target_mod.py").write_text(_GOOD_CODE, encoding="utf-8")
        return _coder_result(success=True, files_changed=["target_mod.py"])

    factory = _RecordingCoderFactory(_on_code)

    cold_update_manager = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-fallback"
    cold_update_manager.propose.return_value = proposal

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=factory,
    )
    item = _item(targets=("target_mod.py",))

    gate = MagicMock()
    gate.evolve.return_value = MagicMock(succeeded=False, best_score=0.0, best_code="")

    result = runner.run_item_with_evolution(item, evolution_gate=gate)

    gate.evolve.assert_called_once()
    assert factory.code_calls == 1
    assert result["status"] == "proposed"
    assert result["proposal_id"] == "proposal-fallback"


def test_run_item_with_evolution_zero_score_falls_back_to_run_item(tmp_path: Path) -> None:
    """evolve() succeeded=True pero best_score=0.0 -> tampoco hay mejora real, cae a run_item()."""
    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)
    (tmp_path / "tests").mkdir()

    fake_coder_result = MagicMock()
    fake_coder_result.success = False
    fake_coder_result.iterations = 1
    fake_coder_result.files_changed = []
    fake_coder_result.test_output = "FAILED"
    fake_coder_result.error = "no mejoro"

    tool_coder_cls = MagicMock()
    tool_coder_cls.return_value.code.return_value = fake_coder_result

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
        tool_coder_factory=tool_coder_cls,
    )
    item = _item(targets=("target_mod.py",))

    gate = MagicMock()
    gate.evolve.return_value = MagicMock(succeeded=True, best_score=0.0, best_code=_GOOD_CODE)

    result = runner.run_item_with_evolution(item, evolution_gate=gate)

    tool_coder_cls.return_value.code.assert_called_once()
    assert result["status"] == "failed"


def test_run_item_with_evolution_success_proposes_with_evolution_metadata(tmp_path: Path) -> None:
    """evolve() succeeded=True con best_score>0 -> escribe codigo, genera patch,
    propone a ColdUpdate con origin=self_audit y evidence con evolution_score."""
    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)
    (tmp_path / "tests").mkdir()

    cold_update_manager = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-evo"
    cold_update_manager.propose.return_value = proposal

    tool_coder_cls = MagicMock()  # no debe usarse en el camino exitoso

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=tool_coder_cls,
    )
    item = _item(targets=("target_mod.py",))

    gate = MagicMock()
    gate.evolve.return_value = MagicMock(succeeded=True, best_score=1.0, best_code=_GOOD_CODE)

    result = runner.run_item_with_evolution(item, evolution_gate=gate)

    assert result["status"] == "proposed"
    assert result["item_id"] == item.id
    assert result["proposal_id"] == "proposal-evo"
    tool_coder_cls.return_value.code.assert_not_called()

    cold_update_manager.propose.assert_called_once()
    _, kwargs = cold_update_manager.propose.call_args
    assert kwargs["origin"] == "self_audit"
    assert kwargs["evidence"]["backlog_item_id"] == item.id
    assert kwargs["evidence"]["evolution_score"] == 1.0
    assert kwargs["evidence"]["method"] == "evolution_gate"

    # No queda ningun worktree efimero huerfano tras el ciclo completo.
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    lines = [ln for ln in listing.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1


def test_run_item_with_evolution_success_leaves_live_tree_untouched(tmp_path: Path) -> None:
    """El patch de la evolución se genera en un worktree efímero: el árbol de
    trabajo VIVO no se toca nunca — ni siquiera en el camino exitoso (antes se
    escribía best_code directamente sobre el target real para poder hacer
    git diff, dejando el árbol vivo sucio)."""
    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)
    (tmp_path / "tests").mkdir()

    cold_update_manager = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-evo-clean"
    cold_update_manager.propose.return_value = proposal

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=cold_update_manager,
        tool_coder_factory=MagicMock(),
    )
    item = _item(targets=("target_mod.py",))

    gate = MagicMock()
    gate.evolve.return_value = MagicMock(succeeded=True, best_score=1.0, best_code=_GOOD_CODE)

    result = runner.run_item_with_evolution(item, evolution_gate=gate)

    assert result["status"] == "proposed"
    # El patch propuesto contiene el candidato ganador...
    _, kwargs = cold_update_manager.propose.call_args
    patch_text = Path(kwargs["patch_path"]).read_text(encoding="utf-8")
    assert "return a + b" in patch_text
    # ...pero el árbol vivo queda EXACTAMENTE como estaba, limpio.
    assert (tmp_path / "target_mod.py").read_text(encoding="utf-8") == _BAD_CODE
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    )
    assert status.stdout.strip() == ""


# ---------------------------------------------------------------------------
# _write_worktree_evaluator_file — regresion del bug real de openevolve
# (inspect.getsource() sobre un closure/metodo revienta: sin closure vars,
# sin imports externos. Ver EvolutionGate.evolve() / self_build_runner.py).
# ---------------------------------------------------------------------------


def test_write_worktree_evaluator_file_has_module_level_evaluate(tmp_path: Path) -> None:
    """El fichero generado no es un closure: es texto plano autocontenido
    con un 'evaluate(program_path)' a nivel de modulo y sin 'self'."""
    path = _write_worktree_evaluator_file(tmp_path, "target_mod.py", ["true"], "HEAD")
    try:
        source = path.read_text(encoding="utf-8")
        assert "def evaluate(program_path):" in source
        assert "self." not in source
        assert "self,\n" not in source
    finally:
        path.unlink(missing_ok=True)


def test_write_worktree_evaluator_file_runs_isolated_and_scores_like_the_original(
    tmp_path: Path,
) -> None:
    """Regresion directa del bug: cargar el fichero generado en un modulo
    FRESCO (import_module, sin closures ni globals de este test) y llamar a
    su evaluate() debe dar la MISMA puntuacion que _evaluate_candidate_in_worktree
    para el mismo candidato — asi es exactamente como lo invoca openevolve."""
    import importlib.util

    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )

    evaluator_path = _write_worktree_evaluator_file(tmp_path, "target_mod.py", _TEST_CMD, "HEAD")
    candidate_path = tmp_path / "candidate.py"
    candidate_path.write_text(_GOOD_CODE, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location("generated_evaluator", evaluator_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # falla aqui si hubiera closures/imports rotos

        isolated_result = module.evaluate(str(candidate_path))
        direct_result = runner._evaluate_candidate_in_worktree(
            "target_mod.py", _GOOD_CODE, _TEST_CMD, "HEAD",
        )

        assert isolated_result == {"score": 1.0}
        assert isolated_result == direct_result
    finally:
        evaluator_path.unlink(missing_ok=True)


def test_run_item_with_evolution_evaluator_file_is_a_path_and_is_cleaned_up(
    tmp_path: Path,
) -> None:
    """evolution_gate.evolve() recibe una ruta de fichero (str), NO un
    callable/closure — y ese fichero temporal desaparece tras la corrida,
    tanto si evolve() tuvo exito como si no."""
    _init_repo_with_target(tmp_path, "target_mod.py", _BAD_CODE)
    (tmp_path / "tests").mkdir()

    runner = SelfBuildRunner(
        repo_root=tmp_path, hub=MagicMock(), cold_update_manager=MagicMock(),
    )
    item = _item(targets=("target_mod.py",))

    seen_path_during_call: dict[str, str] = {}

    def _fake_evolve(*, initial_code: str, evaluator: object) -> MagicMock:
        assert isinstance(evaluator, str)
        seen_path_during_call["path"] = evaluator
        assert Path(evaluator).exists()
        assert "def evaluate(program_path):" in Path(evaluator).read_text(encoding="utf-8")
        return MagicMock(succeeded=False, best_score=0.0, best_code="")

    gate = MagicMock()
    gate.evolve.side_effect = _fake_evolve

    runner.run_item_with_evolution(item, evolution_gate=gate)

    gate.evolve.assert_called_once()
    assert not Path(seen_path_during_call["path"]).exists()  # limpiado tras la corrida
