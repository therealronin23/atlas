#!/usr/bin/env python3
"""Inventory the documentary source corpus and classify every path."""
from __future__ import annotations
import argparse, fnmatch
from pathlib import Path
from typing import Any
import yaml

ROOT=Path(__file__).resolve().parent.parent
DOC_SUFFIXES={".md",".mdx",".rst",".txt",".adoc",".yaml",".yml",".json",".jsonl",".html",".bib",".bbl",".tex",".pdf",".docx",".py"}
EXCLUDED_PARTS={".git",".venv","node_modules","__pycache__",".pytest_cache","graphify-out","graphify-vault"}
GENERATED={
    "ATLAS.md",
    "docs/architecture/ATLAS_HOSTED_REFERENCE_ARCHITECTURE.md",
    "docs/roadmap/ATLAS_HOSTED_1_0.md",
    "docs/decisions/adr/adr_072_canonical_governance_and_hosted_convergence.md",
}

def load_sources(root: Path)->list[dict[str,Any]]:
    raw=yaml.safe_load((root/'docs/canon/ATLAS_SOURCE_LEDGER.yaml').read_text(encoding='utf-8')) or {}
    return list(raw.get('sources') or [])

def candidate(path: Path, root: Path)->bool:
    rel=path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in rel.parts): return False
    s=rel.as_posix()
    if s in GENERATED or s.startswith('docs/canon/'): return False
    if s.startswith('docs/'):
        return path.suffix.lower() in DOC_SUFFIXES
    if len(rel.parts)==1:
        return s in {'README.md','AGENTS.md','agents.md','WORK_LEDGER.md','MEMORY.md'} or s.startswith('feedback-')
    if s.startswith(('memory/system_context/','knowledge-src/')):
        return path.suffix.lower() in {'.md','.txt','.yaml','.yml','.json'}
    if s.startswith('scripts/'):
        return path.suffix.lower() in {'.md','.rst','.txt'}
    if s=='ui/atlas-shell/README.md' or s=='atlas-experiments/README.md':
        return True
    if s.startswith('workspace/lessons/'):
        return path.suffix.lower() in {'.yaml','.yml','.json','.md'}
    return False

def scan(root: Path)->list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and candidate(p,root))

def matches(path: str, locator: str)->bool:
    if locator.startswith('external:'): return False
    if locator.endswith('/**/*'):
        return path.startswith(locator[:-4])
    return fnmatch.fnmatch(path,locator)

def build_report(root: Path)->dict[str,Any]:
    sources=load_sources(root); paths=scan(root)
    classification={p:[s['id'] for s in sources for loc in (s.get('locator') or []) if matches(p,str(loc))] for p in paths}
    uncovered=[p for p,ids in classification.items() if not ids]
    multiply={p:ids for p,ids in classification.items() if len(ids)>1}
    incomplete=[s['id'] for s in sources if s.get('semantic_absorption')!='complete']
    return {
        'document_count':len(paths),
        'source_entry_count':len(sources),
        'uncovered_count':len(uncovered),
        'uncovered_documents':uncovered,
        'multiply_classified_count':len(multiply),
        'multiply_classified_documents':multiply,
        'semantic_absorption_incomplete_count':len(incomplete),
        'semantic_absorption_incomplete_sources':incomplete,
    }

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--root',type=Path,default=ROOT); ap.add_argument('--strict',action='store_true'); ap.add_argument('--write-report',type=Path)
    a=ap.parse_args(); report=build_report(a.root); text=yaml.safe_dump(report,allow_unicode=True,sort_keys=False); print(text,end='')
    if a.write_report: a.write_report.parent.mkdir(parents=True,exist_ok=True); a.write_report.write_text(text,encoding='utf-8')
    return 1 if a.strict and report['uncovered_count'] else 0
if __name__=='__main__': raise SystemExit(main())
