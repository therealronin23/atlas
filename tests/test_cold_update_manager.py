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
