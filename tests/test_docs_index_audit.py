"""Contract tests for the machine-readable documentation inventory.

New documents must not acquire authority merely by being created. Historical
handoffs remain history, generated handoffs enter as proposals, and live
entries without verification remain visible as explicit debt.
"""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import yaml


def _module():
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "docs_index_audit", root / "scripts" / "docs_index_audit.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    (docs / "design").mkdir(parents=True)
    (docs / "archive").mkdir()
    (docs / "inbox").mkdir()
    (docs / "design" / "plan.md").write_text("# plan", encoding="utf-8")
    (docs / "archive" / "old.md").write_text("# old", encoding="utf-8")
    (docs / "inbox" / "untriaged.md").write_text("x", encoding="utf-8")
    return docs


def test_write_then_validate_is_structurally_clean(tmp_path: Path) -> None:
    module = _module()
    docs = _make_docs(tmp_path)

    assert module.write_index(docs) == 2
    assert module.validate(docs) == {
        "missing": [],
        "orphans": [],
        "expired": [],
        "unverified": [],
    }


def test_new_design_defaults_to_proposed_and_archive_to_historical(
    tmp_path: Path,
) -> None:
    module = _module()
    docs = _make_docs(tmp_path)
    module.write_index(docs)
    index = module.load_index(docs)

    assert index["docs/design/plan.md"]["type"] == "design"
    assert index["docs/design/plan.md"]["status"] == "propuesto"
    assert index["docs/archive/old.md"]["status"] == "historico"


def test_generated_handoff_is_proposed_but_old_handoff_is_history(
    tmp_path: Path,
) -> None:
    module = _module()
    docs = _make_docs(tmp_path)
    (docs / "handoff" / "old").mkdir(parents=True)
    (docs / "handoff" / "GENERATED").mkdir(parents=True)
    (docs / "handoff" / "old" / "a.md").write_text("a", encoding="utf-8")
    (docs / "handoff" / "GENERATED" / "00.md").write_text("b", encoding="utf-8")

    module.write_index(docs)
    index = module.load_index(docs)

    assert index["docs/handoff/old/a.md"]["status"] == "historico"
    assert index["docs/handoff/GENERATED/00.md"]["status"] == "propuesto"


def test_legacy_default_vigente_migrates_to_historical_for_old_handoffs(
    tmp_path: Path,
) -> None:
    module = _module()
    docs = _make_docs(tmp_path)
    (docs / "handoff" / "pack").mkdir(parents=True)
    (docs / "handoff" / "pack" / "a.md").write_text("a", encoding="utf-8")
    module.write_index(docs)

    index_path = docs / "INDEX.yaml"
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in payload["entries"] if item["path"] == "docs/handoff/pack/a.md"
    )
    entry["status"] = "vigente"
    index_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    module.write_index(docs)
    assert module.load_index(docs)["docs/handoff/pack/a.md"]["status"] == "historico"


def test_new_file_and_orphan_are_reported(tmp_path: Path) -> None:
    module = _module()
    docs = _make_docs(tmp_path)
    module.write_index(docs)

    (docs / "design" / "new.md").write_text("new", encoding="utf-8")
    assert module.validate(docs)["missing"] == ["docs/design/new.md"]

    (docs / "design" / "plan.md").unlink()
    assert module.validate(docs)["orphans"] == ["docs/design/plan.md"]


def test_curated_fields_survive_rewrite(tmp_path: Path) -> None:
    module = _module()
    docs = _make_docs(tmp_path)
    module.write_index(docs)

    index_path = docs / "INDEX.yaml"
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in payload["entries"] if item["path"] == "docs/design/plan.md"
    )
    entry.update(status="vigente", verified="2026-07-21", notes="manual")
    index_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    module.write_index(docs)
    entry = module.load_index(docs)["docs/design/plan.md"]
    assert entry["status"] == "vigente"
    assert entry["verified"] == "2026-07-21"
    assert entry["notes"] == "manual"


def test_live_unverified_and_stale_are_separate(tmp_path: Path) -> None:
    module = _module()
    docs = _make_docs(tmp_path)
    module.write_index(docs)

    index_path = docs / "INDEX.yaml"
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in payload["entries"] if item["path"] == "docs/design/plan.md"
    )
    entry["status"] = "vigente"
    index_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert module.validate(docs)["unverified"] == ["docs/design/plan.md"]

    payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in payload["entries"] if item["path"] == "docs/design/plan.md"
    )
    entry["verified"] = (
        date.today() - timedelta(days=module.VERIFY_MAX_DAYS + 1)
    ).isoformat()
    index_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    expired = module.validate(docs)["expired"]
    assert len(expired) == 1
    assert "docs/design/plan.md" in expired[0]
