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
