from __future__ import annotations

import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parent.parent / "scripts" / "mcp_catalog_reset_candidates.py"
_spec = importlib.util.spec_from_file_location("mcp_catalog_reset_candidates", _path)
assert _spec and _spec.loader
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


def test_filter_out_candidates_removes_only_candidato_status() -> None:
    data = {"sectors": {"s": {"entries": [{"name": "a", "status": "instalado"}, {"name": "b", "status": "candidato"}, {"name": "c", "status": "verificado"}]}}}
    filtered, removed = module.filter_out_candidates(data)
    assert [entry["name"] for entry in filtered["sectors"]["s"]["entries"]] == ["a", "c"]
    assert removed == 1


def test_filter_does_not_mutate_input() -> None:
    data = {"sectors": {"s": {"entries": [{"name": "a", "status": "instalado"}]}}}
    filtered, removed = module.filter_out_candidates(data)
    assert filtered == data and removed == 0
