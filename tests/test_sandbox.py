"""Sandbox: timeout parametrizado por llamada + snapshot/restore local real."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import OperationalMode
from atlas.security.sandbox import LayeredIsolationSandbox


@pytest.fixture
def sandbox(tmp_path: Path) -> LayeredIsolationSandbox:
    (tmp_path / "tmp").mkdir()
    return LayeredIsolationSandbox(workspace=tmp_path)


class TestTimeoutThreading:
    def test_per_call_timeout_overrides_default(self, sandbox: LayeredIsolationSandbox) -> None:
        # El default de clase sigue en 60s; el timeout por llamada debe ganar.
        assert sandbox.WALL_TIMEOUT_NORMAL_S == 60
        result = sandbox.execute("import time\ntime.sleep(5)", timeout_s=1)
        assert result.success is False
        assert "1s" in result.stderr or result.exit_code == -1

    def test_command_per_call_timeout(self, sandbox: LayeredIsolationSandbox) -> None:
        result = sandbox.execute_command(["sleep", "5"], timeout_s=1)
        assert result.success is False
        assert result.exit_code == -1

    def test_none_timeout_uses_class_default(self, sandbox: LayeredIsolationSandbox) -> None:
        result = sandbox.execute("print('ok')", timeout_s=None)
        assert result.success is True
        assert "ok" in result.stdout


class TestSnapshotRestore:
    def test_snapshot_archive_created(self, sandbox: LayeredIsolationSandbox, tmp_path: Path) -> None:
        (tmp_path / "data.txt").write_text("v1", encoding="utf-8")
        snap = sandbox._take_snapshot(tmp_path)
        assert snap.startswith("atlas-snap-")
        assert sandbox._archive_path(snap).is_file()

    def test_restore_round_trips_workspace_state(
        self, sandbox: LayeredIsolationSandbox, tmp_path: Path
    ) -> None:
        target = tmp_path / "data.txt"
        target.write_text("original", encoding="utf-8")
        snap = sandbox._take_snapshot(tmp_path)

        target.write_text("mutado", encoding="utf-8")
        assert target.read_text(encoding="utf-8") == "mutado"

        assert sandbox.restore_snapshot(snap) is True
        assert target.read_text(encoding="utf-8") == "original"

    def test_restore_unknown_snapshot_returns_false(self, sandbox: LayeredIsolationSandbox) -> None:
        assert sandbox.restore_snapshot("atlas-snap-nope") is False

    def test_snapshot_excludes_snapshot_dir(
        self, sandbox: LayeredIsolationSandbox, tmp_path: Path
    ) -> None:
        # Un primer snapshot crea .atlas_snapshots; el segundo no debe anidarlo.
        first = sandbox._take_snapshot(tmp_path)
        second = sandbox._take_snapshot(tmp_path)
        import tarfile

        with tarfile.open(sandbox._archive_path(second), "r:gz") as tar:
            names = tar.getnames()
        assert not any(sandbox.SNAPSHOT_DIR_NAME in n for n in names)
        assert first != second


class TestOmegaTakesRealSnapshot:
    def test_omega_execution_attaches_restorable_snapshot(
        self, sandbox: LayeredIsolationSandbox, tmp_path: Path
    ) -> None:
        (tmp_path / "state.txt").write_text("pre", encoding="utf-8")
        result = sandbox.execute(
            "print('omega')",
            operational_mode=OperationalMode.OMEGA,
            take_snapshot=True,
        )
        assert result.operational_mode == OperationalMode.OMEGA
        assert result.snapshot_id is not None
        assert sandbox._archive_path(result.snapshot_id).is_file()
