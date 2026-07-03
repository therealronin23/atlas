"""ADR-025 ColdUpdateManager tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.cold_update_manager import ColdUpdateManager
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def mini_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    return root


@pytest.fixture
def mgr(mini_project: Path, tmp_path: Path) -> ColdUpdateManager:
    ws = tmp_path / "atlas"
    ws.mkdir()
    merkle = MerkleLogger(ws / "memory" / "audit")
    return ColdUpdateManager(
        mini_project,
        merkle,
        store_dir=tmp_path / "cold-store",
    )


def test_propose_and_validate_patch(mgr: ColdUpdateManager, tmp_path: Path) -> None:
    patch = tmp_path / "add.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/src/atlas/marker.txt\n@@ -0,0 +1 @@\n+cold\n",
        encoding="utf-8",
    )
    proposal = mgr.propose("test patch", patch)
    assert proposal.status == "proposed"
    assert Path(proposal.worktree_path).exists()

    from unittest.mock import patch as mock_patch

    from atlas.core.validation_runner import ValidationReport

    fake_report = ValidationReport(
        passed=True,
        pytest_exit=0,
        mypy_exit=0,
        pytest_summary="1 passed",
        mypy_summary="Success",
    )
    with mock_patch("atlas.core.cold_update_manager.ValidationRunner") as vr_cls:
        vr_cls.return_value.run.return_value = fake_report
        report = mgr.validate(proposal.id)
    assert report.passed
    assert mgr.get(proposal.id).status == "validated"
    assert mgr.get(proposal.id).origin == "manual"
    assert mgr.get(proposal.id).risk == "medium"


def test_approve_requires_validation(mgr: ColdUpdateManager, tmp_path: Path) -> None:
    patch = tmp_path / "p2.patch"
    patch.write_text("--- a/tests/test_dummy.py\n+++ b/tests/test_dummy.py\n@@ -1 +1 @@\n-def test_ok():\n+def test_ok():\n     assert True\n")
    p = mgr.propose("x", patch)
    with pytest.raises(RuntimeError, match="validacion previa"):
        mgr.approve(p.id)


def test_self_audit_metadata_and_evidence_persist(
    mgr: ColdUpdateManager,
    tmp_path: Path,
) -> None:
    patch = tmp_path / "self.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/docs/self.txt\n@@ -0,0 +1 @@\n+self-audit\n",
        encoding="utf-8",
    )
    proposal = mgr.propose(
        "self audit candidate",
        patch,
        origin="self_audit",
        risk="low",
        evidence={"finding": "docs_drift"},
    )
    assert proposal.origin == "self_audit"
    assert proposal.risk == "low"
    assert proposal.evidence["finding"] == "docs_drift"

    updated = mgr.attach_evidence(proposal.id, {"validation_note": "ok"})
    assert updated.evidence["finding"] == "docs_drift"
    assert updated.evidence["validation_note"] == "ok"


def _validated_proposal(mgr: ColdUpdateManager, tmp_path: Path, name: str):
    from unittest.mock import patch as mock_patch

    from atlas.core.validation_runner import ValidationReport

    patch = tmp_path / f"{name}.patch"
    patch.write_text(
        f"--- /dev/null\n+++ b/src/atlas/{name}.txt\n@@ -0,0 +1 @@\n+{name}\n",
        encoding="utf-8",
    )
    proposal = mgr.propose(name, patch)
    ok = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0)
    with mock_patch("atlas.core.cold_update_manager.ValidationRunner") as vr:
        vr.return_value.run.return_value = ok
        mgr.validate(proposal.id)
    return proposal


def test_patch_stored_outside_worktree(mgr: ColdUpdateManager, tmp_path: Path) -> None:
    patch = tmp_path / "p.patch"
    patch.write_text("--- /dev/null\n+++ b/src/atlas/m.txt\n@@ -0,0 +1 @@\n+m\n", encoding="utf-8")
    proposal = mgr.propose("x", patch)
    # El patch vive en el store root, no dentro del worktree (para sobrevivir al teardown).
    assert Path(proposal.patch_path).exists()
    assert Path(proposal.worktree_path) not in Path(proposal.patch_path).parents


def test_apply_tears_down_worktree_but_keeps_patch(mgr: ColdUpdateManager, tmp_path: Path) -> None:
    from unittest.mock import patch as mock_patch

    from atlas.core.validation_runner import ValidationReport

    proposal = _validated_proposal(mgr, tmp_path, "applyme")
    mgr.approve(proposal.id)
    ok = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0)
    with mock_patch("atlas.core.cold_update_manager.ValidationRunner") as vr:
        vr.return_value.run.return_value = ok
        mgr.apply(proposal.id)
    assert mgr.get(proposal.id).status == "applied"
    assert not Path(proposal.worktree_path).exists()  # worktree destruido
    assert Path(proposal.patch_path).exists()          # patch sobrevive
    # rollback sigue funcionando sin el worktree
    assert mgr.rollback_applied(proposal.id) is True
    assert mgr.get(proposal.id).status == "rolled_back"


def test_reject_tears_down_worktree(mgr: ColdUpdateManager, tmp_path: Path) -> None:
    patch = tmp_path / "r.patch"
    patch.write_text("--- /dev/null\n+++ b/src/atlas/r.txt\n@@ -0,0 +1 @@\n+r\n", encoding="utf-8")
    proposal = mgr.propose("x", patch)
    mgr.reject(proposal.id, "no")
    assert mgr.get(proposal.id).status == "rejected"
    assert not Path(proposal.worktree_path).exists()


def test_forensics_populated_on_failed_validate(tmp_path: Path) -> None:
    from atlas.core.validation_runner import ValidationReport

    ws = tmp_path / "atlas"
    ws.mkdir()
    merkle = MerkleLogger(ws / "memory" / "audit")

    root = tmp_path / "project"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "tests").mkdir()

    fail_report = ValidationReport(
        passed=False,
        pytest_exit=1,
        mypy_exit=0,
        pytest_summary="FAILED tests/test_x.py::test_foo - AssertionError",
        mypy_summary="",
    )
    pass_report = ValidationReport(
        passed=True,
        pytest_exit=0,
        mypy_exit=0,
        pytest_summary="1 passed",
        mypy_summary="Success",
    )

    call_count = 0

    def fake_factory(p: Path):
        class _Runner:
            def run(self):
                nonlocal call_count
                call_count += 1
                return fail_report if call_count == 1 else pass_report
        return _Runner()

    store = tmp_path / "cold-store"
    mgr_f = ColdUpdateManager(root, merkle, store_dir=store, runner_factory=fake_factory)

    patch_fail = tmp_path / "fail.patch"
    patch_fail.write_text("--- /dev/null\n+++ b/src/atlas/f.txt\n@@ -0,0 +1 @@\n+f\n", encoding="utf-8")
    p_fail = mgr_f.propose("fail case", patch_fail)
    mgr_f.validate(p_fail.id)

    fetched_fail = mgr_f.get(p_fail.id)
    assert fetched_fail.status == "failed"
    assert fetched_fail.forensics
    assert fetched_fail.forensics["pytest_summary"] == fail_report.pytest_summary
    assert fetched_fail.forensics["mypy_summary"] == fail_report.mypy_summary
    assert fetched_fail.forensics["pytest_exit"] == 1
    assert fetched_fail.forensics["mypy_exit"] == 0
    assert "timestamp" in fetched_fail.forensics

    patch_pass = tmp_path / "pass.patch"
    patch_pass.write_text("--- /dev/null\n+++ b/src/atlas/g.txt\n@@ -0,0 +1 @@\n+g\n", encoding="utf-8")
    p_pass = mgr_f.propose("pass case", patch_pass)
    mgr_f.validate(p_pass.id)

    fetched_pass = mgr_f.get(p_pass.id)
    assert fetched_pass.status == "validated"
    assert fetched_pass.forensics == {}


def test_forensics_retrocompat_missing_field(tmp_path: Path) -> None:
    """proposals.json sin 'forensics' debe cargarse sin error."""
    import json

    ws = tmp_path / "atlas"
    ws.mkdir()
    merkle = MerkleLogger(ws / "memory" / "audit")
    root = tmp_path / "project"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "tests").mkdir()

    store = tmp_path / "cold-store"
    store.mkdir()

    old_proposal = {
        "id": "abc123",
        "intent": "old proposal",
        "status": "proposed",
        "worktree_path": str(tmp_path / "wt"),
        "patch_path": str(tmp_path / "p.patch"),
        "base_ref": "HEAD",
        "origin": "manual",
        "risk": "medium",
        "evidence": {},
        "validation": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    (store / "proposals.json").write_text(
        json.dumps({"proposals": [old_proposal]}), encoding="utf-8"
    )

    mgr_retro = ColdUpdateManager(root, merkle, store_dir=store)
    p = mgr_retro.get("abc123")
    assert p is not None
    assert p.forensics == {}


def test_propose_rejects_invalid_origin_and_risk(
    mgr: ColdUpdateManager,
    tmp_path: Path,
) -> None:
    patch = tmp_path / "bad.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/docs/bad.txt\n@@ -0,0 +1 @@\n+bad\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="origin"):
        mgr.propose("bad origin", patch, origin="daemon")
    with pytest.raises(ValueError, match="risk"):
        mgr.propose("bad risk", patch, risk="unknown")


# ---------------------------------------------------------------------------
# Helpers para tests de reintento flaky
# ---------------------------------------------------------------------------

def _make_git_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """Crea un repo git mínimo y una propuesta de worktree con diff tests/ vacío."""
    import subprocess
    from atlas.core.git_env import clean_git_env

    root = tmp_path / "gitproject"
    root.mkdir()
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")

    env = clean_git_env()
    # Inicializar repo y commit inicial con todo el contenido.
    subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, env=env,
                   capture_output=True, check=True)

    # El "worktree" simulado es una copia del repo sin modificar tests/.
    wt = tmp_path / "worktree-sim"
    import shutil
    shutil.copytree(root, wt)
    return root, wt


def _make_report(passed: bool, pytest_exit: int = 0) -> "ValidationReport":
    from atlas.core.validation_runner import ValidationReport
    return ValidationReport(
        passed=passed,
        pytest_exit=pytest_exit,
        mypy_exit=0,
        pytest_summary="1 passed" if passed else "FAILED test_x",
        mypy_summary="",
    )


def _mgr_with_git_wt(tmp_path: Path, runner_factory):
    """ColdUpdateManager apuntando a un proyecto git, usando runner_factory fake."""
    from atlas.logging.merkle_logger import MerkleLogger
    root, _ = _make_git_worktree(tmp_path)
    ws = tmp_path / "atlas"
    ws.mkdir(exist_ok=True)
    merkle = MerkleLogger(ws / "memory" / "audit")
    store = tmp_path / "cold-store"
    return ColdUpdateManager(root, merkle, store_dir=store, runner_factory=runner_factory)


class TestFlakySuspectRetry:
    """Prueba el lazo de reintento SUSPECT_FLAKY."""

    def _propose(self, mgr: ColdUpdateManager, tmp_path: Path, name: str = "x"):
        patch = tmp_path / f"{name}.patch"
        patch.write_text(
            f"--- /dev/null\n+++ b/src/atlas/{name}.txt\n@@ -0,0 +1 @@\n+{name}\n",
            encoding="utf-8",
        )
        return mgr.propose(name, patch)

    def test_flaky_retry_passes(self, tmp_path: Path) -> None:
        """pytest falla 1a vez, tests/ sin cambios → reintenta → pasa → validated."""
        calls: list[bool] = []

        def factory(p: Path):
            class _R:
                def run(self):
                    result = _make_report(passed=len(calls) > 0, pytest_exit=0 if len(calls) > 0 else 1)
                    calls.append(result.passed)
                    return result
            return _R()

        mgr = _mgr_with_git_wt(tmp_path, factory)
        proposal = self._propose(mgr, tmp_path)
        report = mgr.validate(proposal.id)

        assert report.passed
        p = mgr.get(proposal.id)
        assert p.status == "validated"
        assert p.forensics.get("flaky_suspect") is True
        assert "retry" in p.forensics
        assert len(calls) == 2

    def test_flaky_retry_fails(self, tmp_path: Path) -> None:
        """pytest falla ambas veces, tests/ sin cambios → failed con forense de ambos."""
        calls: list[int] = []

        def factory(p: Path):
            class _R:
                def run(self):
                    calls.append(1)
                    return _make_report(passed=False, pytest_exit=1)
            return _R()

        mgr = _mgr_with_git_wt(tmp_path, factory)
        proposal = self._propose(mgr, tmp_path)
        report = mgr.validate(proposal.id)

        assert not report.passed
        p = mgr.get(proposal.id)
        assert p.status == "failed"
        assert p.forensics.get("flaky_suspect") is True
        assert "retry" in p.forensics
        assert len(calls) == 2

    def test_no_retry_when_tests_diff_not_empty(self, tmp_path: Path) -> None:
        """diff tests/ no vacío → NO reintenta aunque pytest falle."""
        calls: list[int] = []

        def factory(p: Path):
            class _R:
                def run(self):
                    calls.append(1)
                    return _make_report(passed=False, pytest_exit=1)
            return _R()

        root, _ = _make_git_worktree(tmp_path)
        ws = tmp_path / "atlas"
        ws.mkdir(exist_ok=True)
        from atlas.logging.merkle_logger import MerkleLogger
        merkle = MerkleLogger(ws / "memory" / "audit")
        store = tmp_path / "cold-store2"
        mgr = ColdUpdateManager(root, merkle, store_dir=store, runner_factory=factory)

        # Patch que añade un fichero bajo tests/ → diff no vacío.
        patch = tmp_path / "tests_change.patch"
        patch.write_text(
            "--- /dev/null\n+++ b/tests/test_new.py\n@@ -0,0 +1 @@\n+def test_new(): pass\n",
            encoding="utf-8",
        )
        proposal = mgr.propose("tests change", patch)
        # git apply ya escribió tests/test_new.py en el worktree como fichero
        # no rastreado → git ls-files --others lo verá → diff no vacío.

        mgr.validate(proposal.id)
        p = mgr.get(proposal.id)
        assert p.status == "failed"
        assert not p.forensics.get("flaky_suspect")
        assert len(calls) == 1  # sin reintento

    def test_no_retry_when_only_mypy_fails(self, tmp_path: Path) -> None:
        """pytest_exit==0 pero mypy falla → NO reintenta."""
        calls: list[int] = []

        def factory(p: Path):
            class _R:
                def run(self):
                    calls.append(1)
                    from atlas.core.validation_runner import ValidationReport
                    return ValidationReport(
                        passed=False,
                        pytest_exit=0,
                        mypy_exit=1,
                        pytest_summary="1 passed",
                        mypy_summary="error: ...",
                    )
            return _R()

        mgr = _mgr_with_git_wt(tmp_path, factory)
        proposal = self._propose(mgr, tmp_path, "mypy_case")
        mgr.validate(proposal.id)
        p = mgr.get(proposal.id)
        assert p.status == "failed"
        assert not p.forensics.get("flaky_suspect")
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# Tests de commit-con-evidencia
# ---------------------------------------------------------------------------

def _make_git_repo_for_apply(tmp_path: Path) -> tuple[Path, "ColdUpdateManager"]:
    """Repo git mínimo con un commit inicial; runner_factory fakeada."""
    import subprocess
    from atlas.core.git_env import clean_git_env
    from atlas.core.validation_runner import ValidationReport
    from atlas.logging.merkle_logger import MerkleLogger

    root = tmp_path / "gitapply"
    root.mkdir()
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")

    env = clean_git_env()
    subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, env=env,
                   capture_output=True, check=True)

    ok = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0,
                          pytest_summary="1 passed", mypy_summary="Success")

    def fake_factory(p: Path):
        class _R:
            def run(self):
                return ok
        return _R()

    ws = tmp_path / "atlas"
    ws.mkdir(exist_ok=True)
    merkle = MerkleLogger(ws / "memory" / "audit")
    store = tmp_path / "cold-store-apply"
    mgr = ColdUpdateManager(root, merkle, store_dir=store, runner_factory=fake_factory)
    return root, mgr


def test_commit_with_evidence_advances_head(tmp_path: Path) -> None:
    """Tras apply en repo git, HEAD avanza y el mensaje contiene la evidencia."""
    import subprocess
    from atlas.core.git_env import clean_git_env

    root, mgr = _make_git_repo_for_apply(tmp_path)

    env = clean_git_env()
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()

    patch = tmp_path / "ev.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/src/atlas/evidence.txt\n@@ -0,0 +1 @@\n+evidence\n",
        encoding="utf-8",
    )
    proposal = mgr.propose("test evidence commit", patch, origin="self_audit", risk="low")
    mgr.validate(proposal.id)
    mgr.approve(proposal.id)
    result = mgr.apply(proposal.id)

    assert result["status"] == "applied"

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head_after != head_before, "HEAD no avanzó tras apply"

    commit_msg = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=root, env=env, capture_output=True, text=True, check=True
    ).stdout
    assert "verdict: passed" in commit_msg
    assert "pytest_exit: 0" in commit_msg
    assert "mypy_exit: 0" in commit_msg
    assert "origin: self_audit" in commit_msg
    assert proposal.id in commit_msg


def test_commit_skipped_for_non_git_root(tmp_path: Path) -> None:
    """Root sin .git → commit omitido, apply sigue devolviendo 'applied'."""
    from atlas.core.validation_runner import ValidationReport
    from atlas.logging.merkle_logger import MerkleLogger

    root = tmp_path / "nongit"
    root.mkdir()
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")

    ok = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0)

    def fake_factory(p: Path):
        class _R:
            def run(self):
                return ok
        return _R()

    ws = tmp_path / "atlas"
    ws.mkdir(exist_ok=True)
    merkle = MerkleLogger(ws / "memory" / "audit")
    store = tmp_path / "cold-store-ng"
    mgr = ColdUpdateManager(root, merkle, store_dir=store, runner_factory=fake_factory)

    patch = tmp_path / "ng.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/src/atlas/ng.txt\n@@ -0,0 +1 @@\n+ng\n",
        encoding="utf-8",
    )
    proposal = mgr.propose("non-git test", patch)
    mgr.validate(proposal.id)
    mgr.approve(proposal.id)
    result = mgr.apply(proposal.id)

    assert result["status"] == "applied"
    p = mgr.get(proposal.id)
    assert "commit_error" not in p.forensics


# ---------------------------------------------------------------------------
# T6 — Enrutamiento de anomalías SUSPECT_FLAKY al decisor (ADR-040)
# ---------------------------------------------------------------------------

def _flaky_always_fail_factory():
    """Runner factory que siempre devuelve pytest_exit=1 (ambos intentos fallan)."""
    from atlas.core.validation_runner import ValidationReport as _VR

    def factory(p: Path):
        class _R:
            def run(self):
                return _VR(
                    passed=False,
                    pytest_exit=1,
                    mypy_exit=0,
                    pytest_summary="FAILED test_x",
                    mypy_summary="",
                )
        return _R()
    return factory


def _mgr_with_decider(tmp_path: Path, decider, name: str = "col") -> "ColdUpdateManager":
    """ColdUpdateManager con git repo y decisor inyectado."""
    import subprocess
    from atlas.core.git_env import clean_git_env

    root = tmp_path / f"proj_{name}"
    root.mkdir()
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    env = clean_git_env()
    subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, env=env,
                   capture_output=True, check=True)

    from atlas.logging.merkle_logger import MerkleLogger
    ws = tmp_path / f"atlas_{name}"
    ws.mkdir(exist_ok=True)
    merkle = MerkleLogger(ws / "memory" / "audit")
    store = tmp_path / f"store_{name}"
    return ColdUpdateManager(
        root, merkle, store_dir=store,
        runner_factory=_flaky_always_fail_factory(),
        decider=decider,
    )


class TestAnomalyRouting:
    """T6: SUSPECT_FLAKY persistente se enruta al decisor con forense en context."""

    def _propose_src_patch(self, mgr: "ColdUpdateManager", tmp_path: Path, name: str = "a"):
        patch = tmp_path / f"{name}.patch"
        patch.write_text(
            f"--- /dev/null\n+++ b/src/atlas/{name}.txt\n@@ -0,0 +1 @@\n+{name}\n",
            encoding="utf-8",
        )
        return mgr.propose(f"intent for {name}", patch)

    def test_no_decider_no_route(self, tmp_path: Path) -> None:
        """Sin decisor inyectado el comportamiento es idéntico al actual (retrocompat)."""
        mgr = _mgr_with_decider(tmp_path, decider=None, name="nd")
        proposal = self._propose_src_patch(mgr, tmp_path, "nd")
        mgr.validate(proposal.id)
        p = mgr.get(proposal.id)
        assert p.status == "failed"
        assert p.forensics.get("flaky_suspect") is True
        assert "anomaly_verdict" not in p.forensics

    def test_human_decider_gets_forensics_in_context(self, tmp_path: Path) -> None:
        """HumanDecider fake → RequiresHuman; context lleva la forense."""
        from atlas.core.decider.decider import (
            DecisionAction,
            RequiresHuman,
            Verdict,
        )
        from collections.abc import Mapping

        captured: list[dict] = []

        class FakeHumanDecider:
            def decide(
                self,
                action: DecisionAction,
                sanctioned_intent: str,
                context: Mapping[str, object],
            ) -> Verdict:
                captured.append(dict(context))
                return RequiresHuman(reason="anomalia flaky: requiere revisión humana")

        mgr = _mgr_with_decider(tmp_path, decider=FakeHumanDecider(), name="hd")
        proposal = self._propose_src_patch(mgr, tmp_path, "hd")
        mgr.validate(proposal.id)

        # El decisor fue llamado
        assert len(captured) == 1
        ctx = captured[0]
        # El context lleva la forense
        assert "forensics" in ctx
        forensics = ctx["forensics"]
        assert forensics.get("flaky_suspect") is True
        assert "retry" in forensics
        assert ctx["proposal_id"] == proposal.id
        assert ctx["intent"] == f"intent for hd"

        # El verdict queda registrado en forensics de la propuesta
        p = mgr.get(proposal.id)
        assert "anomaly_verdict" in p.forensics
        assert "RequiresHuman" in p.forensics["anomaly_verdict"]

    def test_autonomous_decider_gets_forensics_in_context(self, tmp_path: Path) -> None:
        """AutonomousDecider fake → decide por invariantes; context lleva la forense."""
        from atlas.core.decider.decider import (
            Allow,
            DecisionAction,
            Verdict,
        )
        from collections.abc import Mapping

        captured: list[dict] = []

        class FakeAutonomousDecider:
            def decide(
                self,
                action: DecisionAction,
                sanctioned_intent: str,
                context: Mapping[str, object],
            ) -> Verdict:
                captured.append(dict(context))
                # Decisor autónomo: Allow para anomalías de bajo impacto
                return Allow(reason="invariante: anomalia reversible, risk=none")

        mgr = _mgr_with_decider(tmp_path, decider=FakeAutonomousDecider(), name="ad")
        proposal = self._propose_src_patch(mgr, tmp_path, "ad")
        mgr.validate(proposal.id)

        assert len(captured) == 1
        ctx = captured[0]
        assert "forensics" in ctx
        forensics = ctx["forensics"]
        assert forensics.get("flaky_suspect") is True
        assert "retry" in forensics

        p = mgr.get(proposal.id)
        assert "anomaly_verdict" in p.forensics
        assert "Allow" in p.forensics["anomaly_verdict"]

    def test_happy_path_no_anomaly_route(self, tmp_path: Path) -> None:
        """Propuesta que pasa validación → NO se llama al decisor de anomalías."""
        from atlas.core.decider.decider import DecisionAction, Verdict
        from collections.abc import Mapping

        called: list[bool] = []

        class SpyDecider:
            def decide(
                self,
                action: DecisionAction,
                sanctioned_intent: str,
                context: Mapping[str, object],
            ) -> Verdict:
                called.append(True)
                from atlas.core.decider.decider import Allow
                return Allow()

        from atlas.core.validation_runner import ValidationReport as _VR2
        ok = _VR2(passed=True, pytest_exit=0, mypy_exit=0,
                  pytest_summary="1 passed", mypy_summary="")

        def ok_factory(p: Path):
            class _R:
                def run(self):
                    return ok
            return _R()

        # Construir mgr con spy decider y factory que siempre pasa
        import subprocess
        from atlas.core.git_env import clean_git_env
        from atlas.logging.merkle_logger import MerkleLogger

        root = tmp_path / "proj_happy"
        root.mkdir()
        (root / "src" / "atlas").mkdir(parents=True)
        (root / "src" / "atlas" / "__init__.py").write_text("")
        (root / "tests").mkdir()
        (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        env = clean_git_env()
        subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env,
                       capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, env=env,
                       capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=root, env=env,
                       capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=root, env=env,
                       capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, env=env,
                       capture_output=True, check=True)

        ws = tmp_path / "atlas_happy"
        ws.mkdir(exist_ok=True)
        merkle = MerkleLogger(ws / "memory" / "audit")
        store = tmp_path / "store_happy"
        mgr = ColdUpdateManager(
            root, merkle, store_dir=store,
            runner_factory=ok_factory,
            decider=SpyDecider(),
        )

        patch = tmp_path / "happy.patch"
        patch.write_text(
            "--- /dev/null\n+++ b/src/atlas/happy.txt\n@@ -0,0 +1 @@\n+happy\n",
            encoding="utf-8",
        )
        proposal = mgr.propose("happy path", patch)
        mgr.validate(proposal.id)

        p = mgr.get(proposal.id)
        assert p.status == "validated"
        assert called == []  # decisor de anomalías NO fue llamado


# ---------------------------------------------------------------------------
# G0.6 — Auto-apply tipo-1 sin HITL
# ---------------------------------------------------------------------------

def _make_git_repo_tier1(tmp_path: Path, name: str = "tier1proj"):
    """Repo git mínimo con commit inicial para tests tipo-1."""
    import subprocess
    from atlas.core.git_env import clean_git_env

    root = tmp_path / name
    root.mkdir()
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    # Archivo con una línea de solo espacios al final — objetivo del patch tipo-1.
    (root / "hello.py").write_text("x = 1\ny = 2\n   \n")

    env = clean_git_env()
    subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, env=env,
                   capture_output=True, check=True)
    return root


def _ok_runner_factory():
    """Runner factory que siempre devuelve passed=True."""
    from atlas.core.validation_runner import ValidationReport

    ok = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0,
                          pytest_summary="1 passed", mypy_summary="Success")

    def factory(p: Path):
        class _R:
            def run(self):
                return ok
        return _R()

    return factory


def _whitespace_only_patch() -> str:
    """Diff que elimina una línea de solo espacios de hello.py (tipo-1 whitespace)."""
    return (
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -1,3 +1,2 @@\n"
        " x = 1\n"
        " y = 2\n"
        "-   \n"
    )


def _code_change_patch() -> str:
    """Diff con cambio de código real (no tipo-1)."""
    return (
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-x = 1\n"
        "+x = 42\n"
        " y = 2\n"
        "    \n"
    )


class TestTier1AutoApply:
    """G0.6 — auto-apply tipo-1 reversible sin HITL."""

    def _build_mgr(self, tmp_path: Path, name: str = "t1"):
        from atlas.logging.merkle_logger import MerkleLogger

        root = _make_git_repo_tier1(tmp_path, name)
        ws = tmp_path / f"atlas_{name}"
        ws.mkdir(exist_ok=True)
        merkle = MerkleLogger(ws / "memory" / "audit")
        store = tmp_path / f"store_{name}"
        mgr = ColdUpdateManager(
            root, merkle, store_dir=store,
            runner_factory=_ok_runner_factory(),
        )
        return root, mgr, merkle

    def _propose_ws_patch(self, mgr: ColdUpdateManager, tmp_path: Path, name: str = "ws"):
        """Propone un patch whitespace-only con origin=swarm."""
        patch_file = tmp_path / f"{name}.patch"
        patch_file.write_text(_whitespace_only_patch(), encoding="utf-8")
        return mgr.propose(f"strip trailing ws {name}", patch_file, origin="swarm", risk="low")

    def test_tier1_auto_apply_whitespace_patch_passes(self, tmp_path: Path) -> None:
        """Patch whitespace-only + origin=swarm → apply + Merkle log."""
        from unittest.mock import patch as mock_patch

        root, mgr, merkle = self._build_mgr(tmp_path, "ws1")
        proposal = self._propose_ws_patch(mgr, tmp_path, "ws1")

        with mock_patch("atlas.security.bwrap_jail.BwrapJail"):
            result = mgr.tier1_auto_apply(proposal.id)

        assert result["status"] == "applied"
        assert mgr.get(proposal.id).status == "applied"

        # Merkle contiene entrada tier1_auto_applied
        import json as _json
        actions: list[str] = []
        for log_file in merkle._log_dir.glob("merkle*.jsonl"):
            for line in log_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    actions.append(_json.loads(line).get("action", ""))
        assert "cold_update.tier1_auto_applied" in actions

        # rollback_applied sigue funcionando
        assert mgr.rollback_applied(proposal.id) is True
        assert mgr.get(proposal.id).status == "rolled_back"

    def test_tier1_auto_apply_rejects_non_swarm_origin(self, tmp_path: Path) -> None:
        """origin='manual' → ValueError."""
        from unittest.mock import patch as mock_patch

        _, mgr, _ = self._build_mgr(tmp_path, "ns1")
        patch_file = tmp_path / "manual.patch"
        patch_file.write_text(_whitespace_only_patch(), encoding="utf-8")
        proposal = mgr.propose("manual patch", patch_file, origin="manual", risk="low")

        with mock_patch("atlas.security.bwrap_jail.BwrapJail"):
            with pytest.raises(ValueError, match="origin='swarm'"):
                mgr.tier1_auto_apply(proposal.id)

    def test_tier1_auto_apply_rejects_self_audit_origin(self, tmp_path: Path) -> None:
        """Invariante CVE-HITL (G0.8), verificado explícitamente para el origin
        que usa SelfBuildRunner: origin='self_audit' NUNCA auto-aplica, ni
        siquiera con un diff trivial de whitespace. Cierra un hallazgo real del
        Cónclave (auditoría 2026-07-03): el guard era correcto en código pero
        solo tenía cobertura de test para origin='manual', no para
        'self_audit' específicamente — ahora es invariante con red de
        seguridad, no solo lectura de código."""
        from unittest.mock import patch as mock_patch

        _, mgr, _ = self._build_mgr(tmp_path, "ns1")
        patch_file = tmp_path / "self_audit.patch"
        patch_file.write_text(_whitespace_only_patch(), encoding="utf-8")
        proposal = mgr.propose("self-build patch", patch_file, origin="self_audit", risk="low")

        with mock_patch("atlas.security.bwrap_jail.BwrapJail"):
            with pytest.raises(ValueError, match="origin='swarm'"):
                mgr.tier1_auto_apply(proposal.id)

    def test_tier1_auto_apply_rejects_non_whitespace_diff(self, tmp_path: Path) -> None:
        """Diff con cambios de código → ValueError (no tipo-1)."""
        from unittest.mock import patch as mock_patch

        _, mgr, _ = self._build_mgr(tmp_path, "nws1")
        patch_file = tmp_path / "code.patch"
        patch_file.write_text(_code_change_patch(), encoding="utf-8")
        proposal = mgr.propose("code change", patch_file, origin="swarm", risk="low")

        with mock_patch("atlas.security.bwrap_jail.BwrapJail"):
            with pytest.raises(ValueError, match="no es tipo-1"):
                mgr.tier1_auto_apply(proposal.id)

    def test_tier1_auto_apply_rejects_if_bwrap_unavailable(self, tmp_path: Path) -> None:
        """BwrapJail lanza → RuntimeError (fail-closed)."""
        from unittest.mock import patch as mock_patch
        from atlas.security.bwrap_jail import BwrapUnavailableError

        _, mgr, _ = self._build_mgr(tmp_path, "bwrap1")
        proposal = self._propose_ws_patch(mgr, tmp_path, "bwrap1")

        def _raise_unavailable():
            raise BwrapUnavailableError("bwrap no encontrado en PATH")

        with mock_patch(
            "atlas.security.bwrap_jail.BwrapJail",
            side_effect=_raise_unavailable,
        ):
            with pytest.raises(RuntimeError, match="BwrapJail no disponible"):
                mgr.tier1_auto_apply(proposal.id)


def test_is_tipo1_diff_rejects_evil_plusplus_prefix():
    """'+++codigo()' dentro de un hunk es código, no whitespace — debe rechazarse."""
    from atlas.core.cold_update_manager import _is_tipo1_diff

    evil_add = "--- a/x\n+++ b/x\n@@ -1,0 +1,1 @@\n+++codigo_real()\n"
    evil_rem = "--- a/x\n+++ b/x\n@@ -1,1 +1,0 @@\n---codigo_real ---\n"
    ws_good  = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-x = 1   \n+x = 1\n"
    empty    = ""
    code_chg = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-old = 1\n+new = 2\n"

    assert _is_tipo1_diff(evil_add) is False, "línea '+++...' en hunk es código, no whitespace"
    assert _is_tipo1_diff(evil_rem) is False, "línea '---...' en hunk es código, no whitespace"
    assert _is_tipo1_diff(ws_good)  is True,  "trailing whitespace → tipo-1"
    assert _is_tipo1_diff(empty)    is False,  "diff vacío → fail-closed"
    assert _is_tipo1_diff(code_chg) is False,  "cambio de código → no tipo-1"
