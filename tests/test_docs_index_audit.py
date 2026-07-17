"""Validador del índice máquina de docs/ (scripts/docs_index_audit.py).

Contrato que fija el orden real de docs (REPO_STANDARD §1): el árbol y el
índice no pueden divergir en silencio — doc sin entrada, entrada sin doc y
"vigente" con verificación caducada gritan en el radar.
"""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import yaml


def _mod():
    repo_root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "docs_index_audit", repo_root / "scripts" / "docs_index_audit.py"
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
    (docs / "inbox" / "sin_triage.md").write_text("x", encoding="utf-8")  # excluido
    return docs


class TestWriteAndValidate:
    def test_write_then_validate_clean(self, tmp_path: Path) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        n = m.write_index(docs)
        assert n == 2  # inbox/ excluido
        report = m.validate(docs)
        assert report == {"missing": [], "orphans": [], "expired": []}

    def test_types_and_status_inferred_by_dir(self, tmp_path: Path) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        m.write_index(docs)
        index = m.load_index(docs)
        assert index["docs/design/plan.md"]["type"] == "design"
        assert index["docs/design/plan.md"]["status"] == "vigente"
        assert index["docs/archive/old.md"]["status"] == "historico"

    def test_new_file_reported_missing(self, tmp_path: Path) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        m.write_index(docs)
        (docs / "design" / "nuevo.md").write_text("n", encoding="utf-8")
        assert m.validate(docs)["missing"] == ["docs/design/nuevo.md"]

    def test_deleted_file_reported_orphan(self, tmp_path: Path) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        m.write_index(docs)
        (docs / "design" / "plan.md").unlink()
        assert m.validate(docs)["orphans"] == ["docs/design/plan.md"]

    def test_rewrite_preserves_hand_curated_fields(self, tmp_path: Path) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        m.write_index(docs)
        index_path = docs / "INDEX.yaml"
        raw = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        for entry in raw["entries"]:
            if entry["path"] == "docs/design/plan.md":
                entry["status"] = "superseded"
                entry["verified"] = "2026-07-01"
                entry["notes"] = "curado a mano"
        index_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        m.write_index(docs)  # regenerar NO pisa lo curado
        entry = m.load_index(docs)["docs/design/plan.md"]
        assert entry["status"] == "superseded"
        assert entry["verified"] == "2026-07-01"
        assert entry["notes"] == "curado a mano"

    def test_stale_verification_expires(self, tmp_path: Path) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        m.write_index(docs)
        raw = yaml.safe_load((docs / "INDEX.yaml").read_text(encoding="utf-8"))
        old = (date.today() - timedelta(days=m.VERIFY_MAX_DAYS + 1)).isoformat()
        for entry in raw["entries"]:
            if entry["path"] == "docs/design/plan.md":
                entry["verified"] = old
        (docs / "INDEX.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        expired = m.validate(docs)["expired"]
        assert len(expired) == 1 and "docs/design/plan.md" in expired[0]


class TestHandoffHygiene:
    """docs/handoff = packs de sucesión: snapshots HISTÓRICOS salvo el pack
    vivo GENERATED (regenerable con `atlas handoff`). Sin esto, ~555 entradas
    heredaban el default 'vigente' y caducarían en masa bajo --strict
    (hallazgo de campaña 2026-07-16, decidido en la ola bootstrap 2026-07-17)."""

    def test_handoff_packs_infer_historico_but_generated_is_vigente(
        self, tmp_path: Path
    ) -> None:
        m = _mod()
        docs = _make_docs(tmp_path)
        (docs / "handoff" / "viejo_pack").mkdir(parents=True)
        (docs / "handoff" / "viejo_pack" / "estado.md").write_text("x", encoding="utf-8")
        (docs / "handoff" / "GENERATED").mkdir()
        (docs / "handoff" / "GENERATED" / "00_ESTADO.md").write_text("y", encoding="utf-8")
        m.write_index(docs)
        index = m.load_index(docs)
        assert index["docs/handoff/viejo_pack/estado.md"]["status"] == "historico"
        assert index["docs/handoff/GENERATED/00_ESTADO.md"]["status"] == "vigente"

    def test_rewrite_upgrades_defaulted_vigente_to_historico_under_handoff(
        self, tmp_path: Path
    ) -> None:
        """Migración: el 'vigente' que era default del generador cede ante la
        nueva inferencia 'historico'; los status curados a mano (propuesto,
        superseded…) se conservan SIEMPRE."""
        m = _mod()
        docs = _make_docs(tmp_path)
        (docs / "handoff" / "pack").mkdir(parents=True)
        (docs / "handoff" / "pack" / "a.md").write_text("a", encoding="utf-8")
        (docs / "handoff" / "pack" / "b.md").write_text("b", encoding="utf-8")
        m.write_index(docs)
        index = m.load_index(docs)
        # Simula el estado legado editando el YAML directo (no hay save_index):
        # default viejo 'vigente' + una curada a mano 'propuesto'
        index_path = docs / "INDEX.yaml"
        raw = index_path.read_text(encoding="utf-8")
        raw = raw.replace(
            "- path: docs/handoff/pack/a.md\n  type: conocimiento\n  status: historico",
            "- path: docs/handoff/pack/a.md\n  type: conocimiento\n  status: vigente",
        ).replace(
            "- path: docs/handoff/pack/b.md\n  type: conocimiento\n  status: historico",
            "- path: docs/handoff/pack/b.md\n  type: conocimiento\n  status: propuesto",
        )
        index_path.write_text(raw, encoding="utf-8")
        assert m.load_index(docs)["docs/handoff/pack/a.md"]["status"] == "vigente"
        m.write_index(docs)
        index2 = m.load_index(docs)
        assert index2["docs/handoff/pack/a.md"]["status"] == "historico"
        assert index2["docs/handoff/pack/b.md"]["status"] == "propuesto"
