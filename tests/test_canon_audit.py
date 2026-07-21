from __future__ import annotations
import copy, importlib.util, shutil
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent.parent

def mod():
    spec=importlib.util.spec_from_file_location('canon_audit',ROOT/'scripts/canon_audit.py'); assert spec and spec.loader
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def copy_repo(tmp_path: Path) -> Path:
    target=tmp_path/'repo'; shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('.git','.venv','.pytest_cache','__pycache__')); return target

def test_rc2_candidate_has_no_structural_errors(): assert mod().validate(ROOT)['errors']==[]

def test_duplicate_authority_rejected(tmp_path: Path):
    root=copy_repo(tmp_path); p=root/'docs/canon/ATLAS_AUTHORITY_LEDGER.yaml'; raw=yaml.safe_load(p.read_text()); raw['states'].append(copy.deepcopy(raw['states'][0])); p.write_text(yaml.safe_dump(raw,sort_keys=False))
    assert any('duplicate authority state id' in x for x in mod().validate(root)['errors'])

def test_unknown_claim_source_rejected(tmp_path: Path):
    root=copy_repo(tmp_path); p=root/'docs/canon/ATLAS_CLAIMS.yaml'; raw=yaml.safe_load(p.read_text()); raw['claims'][0]['sources'].append('NOPE'); p.write_text(yaml.safe_dump(raw,sort_keys=False))
    assert any('unknown source' in x for x in mod().validate(root)['errors'])

def test_missing_component_path_rejected(tmp_path: Path):
    root=copy_repo(tmp_path); p=root/'docs/canon/ATLAS_COMPONENT_REGISTRY.yaml'; raw=yaml.safe_load(p.read_text()); raw['components'][0]['current_paths']=['does/not/exist.py']; p.write_text(yaml.safe_dump(raw,sort_keys=False))
    assert any('current path matches nothing' in x for x in mod().validate(root)['errors'])

def test_roadmap_cycle_rejected(tmp_path: Path):
    root=copy_repo(tmp_path); p=root/'docs/canon/ATLAS_ROADMAP.yaml'; raw=yaml.safe_load(p.read_text()); raw['phases'][0]['depends_on']=['N00']; p.write_text(yaml.safe_dump(raw,sort_keys=False))
    assert any('roadmap dependency cycle' in x for x in mod().validate(root)['errors'])
