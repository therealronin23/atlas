"""Triage de docs/inbox/ (scripts/docs_triage.py) — contrato del orden real.

Reglas que fijan estos tests: dedupe por hash (un duplicado jamás re-entra),
reglas deterministas antes que LLM, `hold` cuando nadie decide (el doc NO se
mueve), y `--apply` alta las entradas como `status: propuesto` — el triage
nunca acuña `vigente`. CERO red/LLM real (llm_classify inyectado).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


def _mods():
    repo_root = Path(__file__).resolve().parent.parent
    out = []
    for name in ("docs_index_audit", "docs_triage"):
        spec = importlib.util.spec_from_file_location(
            name, repo_root / "scripts" / f"{name}.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out.append(module)
    return out


def _make_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    for sub in ("design", "inbox", "decisions/adr", "audits"):
        (docs / sub).mkdir(parents=True)
    (docs / "design" / "existente.md").write_text("contenido ya indexado", encoding="utf-8")
    (docs / "inbox" / "README.md").write_text("# inbox", encoding="utf-8")
    return docs


class TestBuildPlan:
    def test_duplicate_detected_by_hash(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "copia.md").write_text("contenido ya indexado", encoding="utf-8")

        plan = triage.build_plan(docs, llm_classify=None)
        assert plan == [{
            "file": "copia.md", "action": "duplicate",
            "target": "docs/inbox/_rejected", "reason": "hash ya indexado",
        }]

    def test_deterministic_rule_beats_llm(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "adr_099_nueva_decision.md").write_text("# ADR 99", encoding="utf-8")

        calls: list[Path] = []
        plan = triage.build_plan(docs, llm_classify=lambda p: calls.append(p))
        assert plan[0]["action"] == "move"
        assert plan[0]["target"] == "docs/decisions/adr"
        assert calls == []  # el LLM no se consultó

    def test_llm_fallback_and_hold(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "cosa_rara.md").write_text("texto ambiguo", encoding="utf-8")

        plan = triage.build_plan(
            docs, llm_classify=lambda p: ("docs/audits", "evidencia", "LLM: es un informe"),
        )
        assert plan[0] == {
            "file": "cosa_rara.md", "action": "move", "target": "docs/audits",
            "type": "evidencia", "reason": "LLM: es un informe",
        }

        plan_hold = triage.build_plan(docs, llm_classify=lambda p: None)
        assert plan_hold[0]["action"] == "hold"


class TestApplyPlan:
    def test_apply_moves_and_indexes_as_propuesto(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "adr_099_nueva.md").write_text("# ADR", encoding="utf-8")

        plan = triage.build_plan(docs, llm_classify=None)
        applied = triage.apply_plan(plan, docs)

        assert applied == 1
        assert (docs / "decisions" / "adr" / "adr_099_nueva.md").is_file()
        assert not (docs / "inbox" / "adr_099_nueva.md").exists()
        entry = idx.load_index(docs)["docs/decisions/adr/adr_099_nueva.md"]
        assert entry["status"] == "propuesto"  # jamás nace 'vigente'
        # y el índice queda consistente con el árbol:
        assert idx.validate(docs) == {
            "missing": [],
            "orphans": [],
            "expired": [],
            "unverified": [],
        }

    def test_hold_stays_in_inbox(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "ambiguo.md").write_text("???", encoding="utf-8")

        plan = triage.build_plan(docs, llm_classify=lambda p: None)
        applied = triage.apply_plan(plan, docs)
        assert applied == 0
        assert (docs / "inbox" / "ambiguo.md").is_file()

    def test_duplicate_goes_to_rejected(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "copia.md").write_text("contenido ya indexado", encoding="utf-8")

        plan = triage.build_plan(docs, llm_classify=None)
        triage.apply_plan(plan, docs)
        assert (docs / "inbox" / "_rejected" / "copia.md").is_file()
        # los rechazados NO entran al índice como docs (inbox/ está excluido)
        assert "docs/inbox/_rejected/copia.md" not in idx.load_index(docs)


class TestResearchRuleAndHeader:
    def test_research_reports_route_to_knowledge_deterministically(
        self, tmp_path: Path
    ) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        (docs / "inbox" / "research_2026-07-09.md").write_text(
            "# Investigación autónoma\n\n## Hallazgos\n- un audit de diseño citado\n",
            encoding="utf-8",
        )

        calls: list[Path] = []
        plan = triage.build_plan(docs, llm_classify=lambda p: calls.append(p))
        assert plan[0]["action"] == "move"
        assert plan[0]["target"] == "docs/knowledge"
        assert plan[0]["type"] == "conocimiento"
        assert calls == []  # ni LLM ni reglas de contenido ('audit') deciden

    def test_apply_preserves_index_header_comments(self, tmp_path: Path) -> None:
        idx, triage = _mods()
        docs = _make_docs(tmp_path)
        idx.write_index(docs)
        index_path = docs / "INDEX.yaml"
        header = "# Índice MÁQUINA — cabecera curada\n# segunda línea\n"
        index_path.write_text(header + index_path.read_text(encoding="utf-8"), encoding="utf-8")
        (docs / "inbox" / "research_x.md").write_text("# informe", encoding="utf-8")

        plan = triage.build_plan(docs, llm_classify=None)
        triage.apply_plan(plan, docs)

        content = index_path.read_text(encoding="utf-8")
        assert content.startswith(header)  # safe_dump no destruyó la cabecera
