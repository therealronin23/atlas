"""
ADR-048 fase E — RepoMaintenanceScout. Detección + dedup contra propuestas
abiertas (la disciplina anti-acumulación). Puro, sin git.
"""

from __future__ import annotations

from atlas.core.maintenance_scout import MaintenanceTask, RepoMaintenanceScout


def test_detects_per_file_issues() -> None:
    tasks = RepoMaintenanceScout().scan([("a.py", "x = 1   \n"), ("b.py", "y = 2\n")])
    sigs = {t.signature for t in tasks}
    assert "strip_trailing_whitespace:a.py" in sigs
    # b.py está limpio → sin tareas
    assert not any(t.path == "b.py" for t in tasks)


def test_clean_repo_yields_no_tasks() -> None:
    assert RepoMaintenanceScout().scan([("clean.py", "x = 1\n")]) == []


class TestDedup:
    def test_skips_open_signatures(self) -> None:
        files = [("a.py", "x = 1   \n")]
        open_sig = frozenset({"strip_trailing_whitespace:a.py"})
        tasks = RepoMaintenanceScout().scan(files, open_signatures=open_sig)
        assert tasks == []  # ya había una propuesta abierta → no se re-propone

    def test_dedups_within_a_single_scan(self) -> None:
        # El mismo fichero presentado dos veces no genera tareas duplicadas.
        files = [("a.py", "x = 1   \n"), ("a.py", "x = 1   \n")]
        tasks = RepoMaintenanceScout().scan(files)
        sigs = [t.signature for t in tasks]
        assert len(sigs) == len(set(sigs))

    def test_partial_open_still_emits_other_transforms(self) -> None:
        files = [("a.py", "x = 1   ")]  # whitespace + falta newline final
        open_sig = frozenset({"strip_trailing_whitespace:a.py"})
        tasks = RepoMaintenanceScout().scan(files, open_signatures=open_sig)
        sigs = {t.signature for t in tasks}
        assert "strip_trailing_whitespace:a.py" not in sigs
        assert "ensure_final_newline:a.py" in sigs


class TestTaskSpec:
    def test_to_spec_carries_source_and_paths(self) -> None:
        task = MaintenanceTask("a.py", "strip_trailing_whitespace", "x = 1   \n")
        spec = task.to_spec()
        assert spec.metadata["target_path"] == "a.py"
        assert spec.metadata["source"] == "x = 1   \n"
        assert spec.metadata["allowed_paths"] == ["a.py"]
        assert spec.metadata["risk"] == "low"

    def test_signature_stable(self) -> None:
        t = MaintenanceTask("pkg/x.py", "ensure_final_newline")
        assert t.signature == "ensure_final_newline:pkg/x.py"
