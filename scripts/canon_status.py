#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import yaml
ROOT=Path(__file__).resolve().parent.parent
C=ROOT/'docs/canon'
claims=yaml.safe_load((C/'ATLAS_CLAIMS.yaml').read_text())['claims']
sources=yaml.safe_load((C/'ATLAS_SOURCE_LEDGER.yaml').read_text())['sources']
conflicts=yaml.safe_load((C/'ATLAS_CONFLICT_REGISTER.yaml').read_text())['conflicts']
decisions=yaml.safe_load((C/'ATLAS_DECISION_QUEUE.yaml').read_text())['decisions']
print('claims',dict(Counter(x['status'] for x in claims)))
print('sources',dict(Counter(x['semantic_absorption'] for x in sources)))
print('conflicts',dict(Counter(x['status'] for x in conflicts)))
print('decisions',dict(Counter(x['status'] for x in decisions)))
