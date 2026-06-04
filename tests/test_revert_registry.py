"""ADR-040 slice 6 — RevertRegistry + Orchestrator.revert(action_hash)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.decider import MCP_SERVER, SNAPSHOT, RevertRegistry, UndoHandle


class TestRevertRegistry:
    def test_register_and_get_roundtrip(self, tmp_path: Path) -> None:
        reg = RevertRegistry(tmp_path / "r.json")
        reg.register("hash-a", SNAPSHOT, "atlas-snap-1")
        assert reg.get("hash-a") == UndoHandle(kind=SNAPSHOT, ref="atlas-snap-1")

    def test_get_missing_is_none(self, tmp_path: Path) -> None:
        assert RevertRegistry(tmp_path / "r.json").get("nope") is None

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "r.json"
        RevertRegistry(path).register("h", MCP_SERVER, "srv")
        assert RevertRegistry(path).get("h") == UndoHandle(kind=MCP_SERVER, ref="srv")

    def test_forget_removes(self, tmp_path: Path) -> None:
        reg = RevertRegistry(tmp_path / "r.json")
        reg.register("h", SNAPSHOT, "s")
        reg.forget("h")
        assert reg.get("h") is None
        assert "h" not in reg

    def test_forget_missing_is_noop(self, tmp_path: Path) -> None:
        RevertRegistry(tmp_path / "r.json").forget("ghost")  # no raise

    def test_unknown_kind_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            RevertRegistry(tmp_path / "r.json").register("h", "rollback", "x")

    def test_corrupt_file_loads_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "r.json"
        path.write_text("{not json", encoding="utf-8")
        assert RevertRegistry(path).get("h") is None


@pytest.fixture
def orch(tmp_path: Path):
    from atlas.core.orchestrator import Orchestrator
    import atlas.governance.governance_l0 as g

    g.GovernanceL0._instance = None
    ws = tmp_path / "atlas"
    ws.mkdir()
    o = Orchestrator(workspace=ws)
    yield o
    g.GovernanceL0._instance = None


class TestOrchestratorRevert:
    def test_revert_missing_handle_returns_false(self, orch) -> None:
        assert orch.revert("unknown-hash") is False

    def test_revert_snapshot_restores_and_forgets(self, orch) -> None:
        # Snapshot real del workspace → revert lo restaura vía sandbox.
        target = orch._workspace
        snap_id = orch._sandbox._take_snapshot(target)
        orch.register_undo("h-snap", SNAPSHOT, snap_id)
        assert orch.revert("h-snap") is True
        assert orch._revert_registry.get("h-snap") is None

    def test_revert_snapshot_missing_archive_returns_false(self, orch) -> None:
        orch.register_undo("h-bad", SNAPSHOT, "atlas-snap-inexistente")
        assert orch.revert("h-bad") is False
        # No se consumió el handle: el undo no llegó a ocurrir.
        assert orch._revert_registry.get("h-bad") is not None

    def test_revert_mcp_server_removes(self, orch, monkeypatch) -> None:
        removed: list[str] = []

        def _remove(name: str) -> bool:
            removed.append(name)
            return True

        monkeypatch.setattr(orch._mcp, "remove_server", _remove)
        orch.register_undo("h-srv", MCP_SERVER, "weather")
        assert orch.revert("h-srv") is True
        assert removed == ["weather"]
        assert orch._revert_registry.get("h-srv") is None

    def test_revert_logged_in_merkle(self, orch) -> None:
        snap_id = orch._sandbox._take_snapshot(orch._workspace)
        orch.register_undo("h-log", SNAPSHOT, snap_id)
        orch.revert("h-log")
        records = [r.to_dict() for r in orch._merkle.tail(50)]
        reverts = [r for r in records if r["action"] == "decider.revert"]
        assert reverts and reverts[-1]["payload"]["action_hash"] == "h-log"
