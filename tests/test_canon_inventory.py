from __future__ import annotations
import importlib.util
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent.parent

def mod():
    spec=importlib.util.spec_from_file_location('canon_inventory',ROOT/'scripts/canon_inventory.py'); assert spec and spec.loader
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_real_snapshot_has_no_unclassified_document_paths():
    assert mod().build_report(ROOT)['uncovered_documents']==[]

def test_unknown_document_is_reported(tmp_path: Path):
    root=tmp_path/'repo'; (root/'docs/canon').mkdir(parents=True); (root/'docs/design').mkdir()
    (root/'docs/canon/ATLAS_SOURCE_LEDGER.yaml').write_text(yaml.safe_dump({'sources':[{'id':'S','locator':['docs/design/known.md'],'semantic_absorption':'complete'}]}))
    (root/'docs/design/known.md').write_text('x'); (root/'docs/design/mystery.md').write_text('x')
    assert mod().build_report(root)['uncovered_documents']==['docs/design/mystery.md']
